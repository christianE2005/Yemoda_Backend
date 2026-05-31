"""
AI Chat Router — two providers:
  • "copilot"  → user's GitHub token → api.githubcopilot.com  (requires Copilot subscription)
  • "yemoda"   → server-side Anthropic API key               (always available)
"""
import logging
import os
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])
limiter = Limiter(key_func=get_remote_address)

_COPILOT_URL = "https://api.githubcopilot.com/chat/completions"
_GITHUB_API_URL = "https://api.github.com"
# Copilot uses OpenAI-compatible models identifiers
_COPILOT_MODELS = {
    "gpt-4o",
    "gpt-4o-mini",
    "o1",
    "o1-mini",
    "o3-mini",
    "claude-3-5-sonnet",
    "claude-3-7-sonnet",
}
_COPILOT_DEFAULT_MODEL = "gpt-4o"

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
    content: str


class ChatRequest(BaseModel):
    provider: Literal["copilot", "yemoda"] = Field(
        default="yemoda",
        description=(
            "'copilot' → usa el token GitHub del usuario con la API de GitHub Copilot "
            "(requiere suscripción activa de Copilot). "
            "'yemoda' → usa la API key de Anthropic del servidor (siempre disponible)."
        ),
    )
    github_token: str | None = Field(
        default=None,
        description="Token OAuth del usuario. Requerido cuando provider='copilot'.",
    )
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=50)
    model: str | None = Field(
        default=None,
        description=(
            "Modelo a usar. Para 'copilot': gpt-4o, o1, claude-3-7-sonnet, etc. "
            "Para 'yemoda': claude-haiku-4-5, claude-3-5-sonnet-20241022, etc. "
            "Si se omite se usa el modelo por defecto del provider."
        ),
    )
    stream: bool = Field(default=False, description="Si es true, devuelve Server-Sent Events (solo para provider='copilot')")
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
    copilot: list[ModelInfo]
    yemoda: list[ModelInfo]


class CopilotStatusRequest(BaseModel):
    github_token: str = Field(..., min_length=10, description="Token OAuth del usuario de GitHub")


class CopilotStatusResponse(BaseModel):
    github_token_valid: bool
    copilot_access: bool
    github_login: str | None = None
    detail: str


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
        "Tu tarea es explicar la causa del problema y proporcionar el código corregido. "
        "Siempre muestra el código completo de los archivos que modifiques."
    ),
}


def _build_system_message(context_type: str | None, context_data: dict | None) -> str:
    base = _SYSTEM_PROMPTS.get(context_type or "general", _SYSTEM_PROMPTS["general"])
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
    if context_data.get("warnings"):
        warnings_text = "\n".join(
            f"- [{w.get('type', 'warning')}] {w.get('message', '')}" for w in context_data["warnings"]
        )
        extras.append(f"Advertencias activas:\n{warnings_text}")
    if context_data.get("diff"):
        extras.append(f"Diff:\n```diff\n{context_data['diff']}\n```")
    if context_data.get("file_content"):
        lang = context_data.get("language", "")
        extras.append(f"Contenido del archivo:\n```{lang}\n{context_data['file_content']}\n```")

    if extras:
        return base + "\n\n### Contexto\n" + "\n".join(extras)
    return base


def _inject_system(messages: list[dict], context_type: str | None, context_data: dict | None) -> list[dict]:
    """Return messages list with a system message prepended if none exists."""
    if any(m["role"] == "system" for m in messages):
        return messages
    system_content = _build_system_message(context_type, context_data)
    return [{"role": "system", "content": system_content}] + messages


# ─────────────────────────────────────────────────────────────────────────────
# Provider implementations
# ─────────────────────────────────────────────────────────────────────────────

async def _call_copilot(body: ChatRequest) -> dict:
    """Forward the request to the GitHub Copilot chat endpoint."""
    if not body.github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="github_token es requerido cuando provider='copilot'.",
        )

    model = body.model or _COPILOT_DEFAULT_MODEL
    if model not in _COPILOT_MODELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Modelo '{model}' no disponible para Copilot. Opciones: {sorted(_COPILOT_MODELS)}",
        )

    messages = _inject_system(
        [m.model_dump() for m in body.messages], body.context_type, body.context_data
    )
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": body.max_tokens,
        "temperature": body.temperature,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {body.github_token}",
        "Content-Type": "application/json",
        "Copilot-Integration-Id": "vscode-chat",
        "Editor-Version": "vscode/1.90.0",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(_COPILOT_URL, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="GitHub Copilot no respondió a tiempo.")
        except httpx.RequestError as exc:
            logger.error("Copilot request error: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No se pudo conectar con GitHub Copilot.")

    if resp.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de GitHub inválido o sin acceso a Copilot. Verifica que tu cuenta tenga una suscripción activa.",
        )
    if resp.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin acceso a GitHub Copilot. Se requiere una suscripción de Copilot Individual, Business o Enterprise.",
        )
    if resp.status_code == 429:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Límite de uso de Copilot alcanzado.")
    if resp.status_code >= 400:
        logger.warning("Copilot error %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error de GitHub Copilot: {resp.text[:300]}")

    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    return {
        "provider": "copilot",
        "model": data.get("model", model),
        "content": (choice.get("message") or {}).get("content", ""),
        "finish_reason": choice.get("finish_reason"),
        "usage": data.get("usage"),
    }


async def _stream_copilot(body: ChatRequest) -> StreamingResponse:
    """Stream Copilot SSE response to the client."""
    if not body.github_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="github_token requerido para streaming con Copilot.")

    model = body.model or _COPILOT_DEFAULT_MODEL
    messages = _inject_system(
        [m.model_dump() for m in body.messages], body.context_type, body.context_data
    )
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": body.max_tokens,
        "temperature": body.temperature,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {body.github_token}",
        "Content-Type": "application/json",
        "Copilot-Integration-Id": "vscode-chat",
        "Editor-Version": "vscode/1.90.0",
    }

    async def generate():
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                async with client.stream("POST", _COPILOT_URL, json=payload, headers=headers) as resp:
                    if resp.status_code >= 400:
                        body_bytes = await resp.aread()
                        yield f"data: {{\"error\": \"{resp.status_code}\", \"detail\": \"{body_bytes.decode()[:200]}\"}}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"{line}\n\n"
            except httpx.TimeoutException:
                yield 'data: {"error": "timeout"}\n\n'
            except httpx.RequestError as exc:
                logger.error("Copilot stream error: %s", exc)
                yield 'data: {"error": "connection_error"}\n\n'

    return StreamingResponse(generate(), media_type="text/event-stream")


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
            detail=f"Modelo '{model}' no disponible para Yemoda. Opciones: {sorted(_ANTHROPIC_MODELS)}",
        )

    messages = [m.model_dump() for m in body.messages]

    # Anthropic separates the system prompt from the messages array
    system_content = _build_system_message(body.context_type, body.context_data)
    # Remove any system messages from the list — Anthropic requires them in the `system` param
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
        logger.error("Anthropic API error: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error en el servicio de IA de Yemoda.")

    return {
        "provider": "yemoda",
        "model": model,
        "content": response.content[0].text if response.content else "",
        "finish_reason": response.stop_reason,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/models", response_model=ModelsResponse, summary="Listar modelos disponibles por provider")
def list_models():
    """Returns the models available for each provider."""
    return {
        "copilot": [{"id": m, "provider": "copilot"} for m in sorted(_COPILOT_MODELS)],
        "yemoda": [{"id": m, "provider": "yemoda"} for m in sorted(_ANTHROPIC_MODELS)],
    }


@router.post(
    "/copilot/status",
    response_model=CopilotStatusResponse,
    summary="Verificar si un token GitHub tiene acceso a Copilot",
)
@limiter.limit("30/minute")
async def copilot_status(request: Request, body: CopilotStatusRequest):
    """
    Verifica dos cosas:
    1) si el token OAuth del usuario de GitHub es válido;
    2) si ese token realmente tiene acceso a GitHub Copilot.
    """
    headers = {
        "Authorization": f"Bearer {body.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        # Step 1: validate token against GitHub user API
        try:
            user_resp = await client.get(f"{_GITHUB_API_URL}/user", headers=headers)
        except httpx.RequestError:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No se pudo conectar con GitHub API.")

        if user_resp.status_code == 401:
            return {
                "github_token_valid": False,
                "copilot_access": False,
                "github_login": None,
                "detail": "Token de GitHub inválido o expirado.",
            }
        if user_resp.status_code >= 400:
            return {
                "github_token_valid": False,
                "copilot_access": False,
                "github_login": None,
                "detail": f"GitHub devolvió error al validar token: {user_resp.status_code}.",
            }

        github_login = (user_resp.json() or {}).get("login")

        # Step 2: verify Copilot entitlement with a minimal completion
        copilot_headers = {
            "Authorization": f"Bearer {body.github_token}",
            "Content-Type": "application/json",
            "Copilot-Integration-Id": "vscode-chat",
            "Editor-Version": "vscode/1.90.0",
        }
        copilot_payload = {
            "model": _COPILOT_DEFAULT_MODEL,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
            "stream": False,
        }

        try:
            copilot_resp = await client.post(_COPILOT_URL, json=copilot_payload, headers=copilot_headers)
        except httpx.RequestError:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No se pudo conectar con GitHub Copilot API.")

        if copilot_resp.status_code == 401:
            return {
                "github_token_valid": True,
                "copilot_access": False,
                "github_login": github_login,
                "detail": "Token válido, pero Copilot rechazó autenticación (401).",
            }
        if copilot_resp.status_code == 403:
            return {
                "github_token_valid": True,
                "copilot_access": False,
                "github_login": github_login,
                "detail": "Token válido, pero la cuenta no tiene suscripción activa a Copilot.",
            }
        if copilot_resp.status_code == 429:
            return {
                "github_token_valid": True,
                "copilot_access": True,
                "github_login": github_login,
                "detail": "Cuenta con Copilot, pero alcanzó límite temporal (429).",
            }
        if copilot_resp.status_code >= 400:
            return {
                "github_token_valid": True,
                "copilot_access": False,
                "github_login": github_login,
                "detail": f"Copilot devolvió error {copilot_resp.status_code}: {copilot_resp.text[:180]}",
            }

    return {
        "github_token_valid": True,
        "copilot_access": True,
        "github_login": github_login,
        "detail": "Token válido y acceso a Copilot confirmado.",
    }


@router.post(
    "/",
    summary="Chat con IA (Copilot o Yemoda)",
    description=(
        "Envía mensajes al modelo elegido. "
        "Con **provider='copilot'** usa el GitHub Copilot del usuario (requiere suscripción). "
        "Con **provider='yemoda'** usa la API de Anthropic del servidor (siempre disponible)."
    ),
    status_code=status.HTTP_200_OK,
)
@limiter.limit("30/minute")
async def chat(request: Request, body: ChatRequest):
    if body.provider == "copilot":
        if body.stream:
            return await _stream_copilot(body)
        return await _call_copilot(body)

    # provider == "yemoda"
    return await _call_yemoda(body)

