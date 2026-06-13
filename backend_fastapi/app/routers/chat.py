"""
AI Chat Router — server-side Anthropic (Claude) only.

Uses the server's ANTHROPIC_API_KEY for every request. (The previous GitHub Copilot
provider was removed; all chat now runs on Claude by default.)
"""
import json
import logging
import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.ai_cost import log_usage
from app.core.deps import get_db, require_internal_token
from app.services import metering
from app.services.metering import current_period, resolve_project_id

logger = logging.getLogger(__name__)

# Server-to-server only: the Django backend proxies chat here and attaches X-Internal-Token.
# This prevents anonymous internet callers from spending the owner's Anthropic budget directly.
router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_internal_token)])
limiter = Limiter(key_func=get_remote_address)

# Anthropic models available server-side. Haiku 4.5 only, by deliberate choice: every AI
# surface of the product (push reviews, hackathon audit, chat, ai-fix) runs on the same
# cheap, fast model so cost stays predictable. The previous list also offered
# claude-3-5-sonnet-20241022 and claude-3-7-sonnet-20250219, both RETIRED by the API
# (calls 404) — selecting them surfaced as a 502 to the user.
_ANTHROPIC_MODELS = {
    "claude-haiku-4-5",
}
_ANTHROPIC_DEFAULT_MODEL = "claude-haiku-4-5"


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    # Per-message length cap so up to 50 messages can't exhaust memory/context.
    content: str = Field(..., max_length=50_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=50)
    model: str | None = Field(
        default=None,
        description=(
            "Modelo de Anthropic a usar (claude-haiku-4-5, claude-3-5-sonnet-20241022, etc.). "
            "Si se omite se usa el modelo por defecto."
        ),
    )
    max_tokens: int = Field(default=4096, ge=1, le=16384)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    context_type: Literal["general", "code_review", "ai_fix"] | None = Field(
        default=None,
        description=(
            "Tipo de contexto para ajustar el system prompt automáticamente. "
            "'code_review' → asistente de revisión de código; "
            "'ai_fix' → asistente de corrección de bugs/warnings."
        ),
    )
    context_data: dict | None = Field(
        default=None,
        description="Datos extra según context_type (task_title, warnings, diff, etc.)",
    )


class ModelInfo(BaseModel):
    id: str
    provider: str


class ModelsResponse(BaseModel):
    yemoda: list[ModelInfo]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPTS: dict[str, str] = {
    "general": (
        "Eres un asistente de desarrollo de software experto. "
        "Responde de forma concisa y precisa. "
        "Cuando muestres código, usa bloques de código con el lenguaje apropiado."
    ),
    "code_review": (
        "Eres un revisor de código experto. Tu objetivo es analizar el código que te muestren, "
        "identificar problemas de calidad, seguridad, rendimiento y mantenibilidad, "
        "y sugerir mejoras concretas con ejemplos de código cuando sea necesario. "
        "Sé directo y constructivo."
    ),
    "ai_fix": (
        "Eres un asistente de desarrollo que resuelve tareas y advertencias de código. "
        "Puedes MODIFICAR archivos existentes y CREAR archivos nuevos cuando la solución lo requiera "
        "(por ejemplo, generar un frontend que aún no existe en el repositorio). "
        "Responde SIEMPRE con un único objeto JSON válido, sin texto fuera del JSON y sin fences de markdown, "
        "con esta forma exacta:\n"
        '{"files":[{"path":"ruta/relativa","action":"create|modify|delete","content":"contenido COMPLETO del archivo"}]}\n'
        "Reglas: 'content' debe ser el contenido final completo del archivo (NO un diff ni fragmentos). "
        "Para 'action':'delete' puedes omitir 'content'. Usa siempre rutas relativas a la raíz del repositorio. "
        'Si no hay cambios necesarios, responde exactamente: {"files":[]}.'
    ),
}

# Notebooks and large files must be trimmed before they reach the model: a .ipynb is JSON with
# base64 cell outputs that can be many MB, which blows past the model context window (Anthropic
# then returns a 4xx that surfaces to the user as a 502). Cap each context field and strip
# notebook outputs so only the source cells remain.
_MAX_CONTEXT_FIELD_CHARS = 60_000


def _truncate(text: str, limit: int = _MAX_CONTEXT_FIELD_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n... [truncado: contenido demasiado largo] ..."


def _strip_notebook(content: str) -> str:
    """Keep only the source of each cell, dropping outputs/metadata. Returns the input unchanged
    if it is not parseable as a Jupyter notebook."""
    try:
        nb = json.loads(content)
    except (ValueError, TypeError):
        return content
    if not isinstance(nb, dict) or not isinstance(nb.get("cells"), list):
        return content
    parts: list[str] = []
    for cell in nb["cells"]:
        if not isinstance(cell, dict):
            continue
        src = cell.get("source")
        if isinstance(src, list):
            src = "".join(str(s) for s in src)
        elif not isinstance(src, str):
            src = ""
        if not src.strip():
            continue
        cell_type = cell.get("cell_type", "code")
        parts.append(f"# ===== {cell_type} cell =====\n{src}")
    return "\n\n".join(parts)


def _build_system_message(context_type: str | None, context_data: dict | None) -> str:
    base = _SYSTEM_PROMPTS.get(context_type or "general", _SYSTEM_PROMPTS["general"])
    # Malformed context_data (non-dict) must not raise AttributeError on the .get() calls below.
    if not isinstance(context_data, dict):
        context_data = {}
    if not context_data:
        return base

    extras: list[str] = []
    if context_data.get("task_title"):
        extras.append(f"Tarea actual: {context_data['task_title']}")
    if context_data.get("task_description"):
        extras.append(f"Descripción: {context_data['task_description']}")
    if context_data.get("repo"):
        extras.append(f"Repositorio: {context_data['repo']}")
    if context_data.get("branch"):
        extras.append(f"Branch: {context_data['branch']}")
    if context_data.get("repo_file_index") and isinstance(context_data["repo_file_index"], list):
        indexed_files = [str(path) for path in context_data["repo_file_index"] if isinstance(path, str)]
        if indexed_files:
            preview = "\n".join(f"- {path}" for path in indexed_files[:200])
            suffix = "\n- ... (truncado)" if len(indexed_files) > 200 else ""
            extras.append(f"Índice de archivos del repositorio:\n{preview}{suffix}")
    if context_data.get("warnings") and isinstance(context_data["warnings"], list):
        warnings_text = "\n".join(
            f"- [{w.get('type', 'warning')}] {w.get('message', '')}"
            for w in context_data["warnings"]
            if isinstance(w, dict)
        )
        if warnings_text:
            extras.append(f"Advertencias activas:\n{warnings_text}")
    if context_data.get("diff"):
        extras.append(f"Diff:\n```diff\n{_truncate(str(context_data['diff']))}\n```")
    if context_data.get("file_content"):
        lang = context_data.get("language", "")
        file_content = str(context_data["file_content"])
        file_path = context_data.get("file_path")
        # A notebook (.ipynb) is huge JSON with base64 outputs; keep only the source cells so the
        # request fits the model context instead of failing upstream as a 502.
        if isinstance(file_path, str) and file_path.lower().endswith(".ipynb"):
            file_content = _strip_notebook(file_content)
        extras.append(f"Contenido del archivo:\n```{lang}\n{_truncate(file_content)}\n```")

    if extras:
        return base + "\n\n### Contexto\n" + "\n".join(extras)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Provider implementation (Anthropic / Yemoda)
# ─────────────────────────────────────────────────────────────────────────────

async def _call_yemoda(body: ChatRequest) -> dict:
    """Call Anthropic using the server-side API key."""
    import anthropic as anthropic_sdk

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de IA de Yemoda no está configurado en este momento.",
        )

    model = body.model or _ANTHROPIC_DEFAULT_MODEL
    if model not in _ANTHROPIC_MODELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Modelo '{model}' no disponible. Opciones: {sorted(_ANTHROPIC_MODELS)}",
        )

    # ai_fix can return several full files (e.g. scaffolding a frontend from scratch), so give it
    # room: the request default of 4096 truncates the JSON file-list and makes it unparseable.
    max_tokens = body.max_tokens
    if body.context_type == "ai_fix":
        max_tokens = max(max_tokens, 16384)

    messages = [m.model_dump() for m in body.messages]

    # Anthropic separates the system prompt from the messages array
    system_content = _build_system_message(body.context_type, body.context_data)
    anthropic_messages = [m for m in messages if m["role"] != "system"]

    # If the user explicitly put a system message, prepend its content to ours
    user_system = next((m["content"] for m in messages if m["role"] == "system"), None)
    if user_system:
        system_content = f"{user_system}\n\n{system_content}"

    client = anthropic_sdk.AsyncAnthropic(api_key=api_key)
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_content,
            messages=anthropic_messages,
            temperature=temperature,
        )
    except anthropic_sdk.AuthenticationError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error de autenticación con la IA de Yemoda.")
    except anthropic_sdk.RateLimitError:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Límite de uso del servicio de IA alcanzado. Intenta de nuevo en un momento.")
    except anthropic_sdk.BadRequestError as exc:
        # Almost always a too-long prompt: the ai_fix/code_review context (diff + file content)
        # overflowed the model's context window. Surface a clear, actionable 413 instead of a
        # blanket 502 so the client can tell the user to trim the file/selection.
        request_id = getattr(exc, "request_id", None)
        logger.error("Anthropic bad request: type=%s request_id=%s", type(exc).__name__, request_id)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El contenido enviado a la IA es demasiado grande (archivo o diff). Reduce la selección e inténtalo de nuevo.",
        )
    except anthropic_sdk.OverloadedError:
        # 529: Anthropic is temporarily overloaded. This is transient and retriable — return 503
        # (not a scary 502) so the client can retry/back off instead of treating it as a hard error.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de IA está saturado en este momento. Espera unos segundos e inténtalo de nuevo.",
        )
    except anthropic_sdk.APIStatusError as exc:
        # Any other upstream status. Log a sanitized summary (HTTP status + error class + request id
        # for tracing with Anthropic) — never the full exception, which can carry sensitive bodies.
        logger.error(
            "Anthropic API error: status=%s type=%s request_id=%s",
            getattr(exc, "status_code", "?"), type(exc).__name__, getattr(exc, "request_id", None),
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error en el servicio de IA de Yemoda.")
    except anthropic_sdk.APIConnectionError:
        # Couldn't reach Anthropic at all (network/DNS/timeout). Distinct from an upstream error response.
        logger.error("Anthropic connection error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo conectar con el proveedor de IA. Inténtalo de nuevo en un momento.",
        )

    # Distinguish the chat surfaces (general / code_review / ai_fix) so each can be costed separately.
    log_usage(f"chat:{getattr(body, 'context_type', None) or 'general'}", model, response.usage.input_tokens, response.usage.output_tokens)

    # The first content block isn't guaranteed to be text (e.g. tool_use); concatenate all
    # text blocks and tolerate empty content.
    content = "".join(getattr(block, "text", "") or "" for block in (response.content or []))

    return {
        "provider": "yemoda",
        "model": model,
        "content": content,
        "finish_reason": response.stop_reason,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/models", response_model=ModelsResponse, summary="Listar modelos de IA disponibles")
def list_models():
    """Returns the available Anthropic (Yemoda) models."""
    return {"yemoda": [{"id": m, "provider": "yemoda"} for m in sorted(_ANTHROPIC_MODELS)]}


@router.post(
    "/",
    summary="Chat con la IA de Yemoda (Claude)",
    description="Envía mensajes a Claude usando la API de Anthropic del servidor.",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("30/minute")
async def chat(request: Request, body: ChatRequest, db: Session = Depends(get_db)):
    # Quota: chat questions and AI-fix calls count against the project's monthly allowance.
    # 'ai_fix' (resolve warnings) is the costliest, so it has its own category.
    # Pre-check before calling the model, but only consume AFTER a successful response so a
    # model failure doesn't burn a unit. Pin the period so the check and the later consume
    # land on the same monthly usage row even across a rollover.
    category = "aifix" if body.context_type == "ai_fix" else "chat"
    project_id = resolve_project_id(db, body.context_data)
    period = current_period()
    if project_id is not None:
        # Atomic check+consume closes the TOCTOU race: two concurrent calls can't both pass the last
        # available unit (has_quota+consume could). We reserve the unit BEFORE the model call and
        # refund it if the call fails, so a model error still doesn't burn quota.
        allowed, used, quota = metering.check_and_consume(db, project_id, category)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"AI quota reached for this project ({used}/{quota} {category} this month). Upgrade your plan or wait for the next cycle.",
            )
        try:
            result = await _call_yemoda(body)
        except Exception:
            metering.refund(db, project_id, category, period=period)
            raise
    else:
        result = await _call_yemoda(body)
    return result
