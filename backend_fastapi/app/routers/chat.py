"""
AI Chat Router — server-side Anthropic (Claude) only.

Uses the server's ANTHROPIC_API_KEY for every request. (The previous GitHub Copilot
provider was removed; all chat now runs on Claude by default.)
"""
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

# Anthropic models available server-side
_ANTHROPIC_MODELS = {
    "claude-haiku-4-5",
    "claude-3-5-sonnet-20241022",
    "claude-3-7-sonnet-20250219",
    "claude-opus-4-5",
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
        "Eres un asistente de corrección de bugs y advertencias de código. "
        "El usuario te proporcionará advertencias o errores detectados en su código. "
        "Tu tarea es corregir el código y responder SIEMPRE en formato unified diff (git patch), "
        "sin texto adicional fuera del diff. "
        "Debes incluir encabezados 'diff --git', rutas a/b, y bloques '@@'. "
        "Si no hay cambios necesarios, responde exactamente: NO_CHANGES."
    ),
}


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
        extras.append(f"Diff:\n```diff\n{context_data['diff']}\n```")
    if context_data.get("file_content"):
        lang = context_data.get("language", "")
        extras.append(f"Contenido del archivo:\n```{lang}\n{context_data['file_content']}\n```")

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
            max_tokens=body.max_tokens,
            system=system_content,
            messages=anthropic_messages,
            temperature=body.temperature,
        )
    except anthropic_sdk.AuthenticationError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Error de autenticación con la IA de Yemoda.")
    except anthropic_sdk.RateLimitError:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Límite de uso del servicio de IA alcanzado. Intenta de nuevo en un momento.")
    except anthropic_sdk.APIStatusError as exc:
        # Log only a sanitized summary (HTTP status + error class). The full exception can carry
        # request/response bodies with sensitive detail, so it must not hit the logs.
        logger.error("Anthropic API error: status=%s type=%s", getattr(exc, "status_code", "?"), type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error en el servicio de IA de Yemoda.")

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
