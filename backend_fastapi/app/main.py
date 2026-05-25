import logging
import sys

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.database import Base, engine
from app.routers import predictions, webhook

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])

app = FastAPI(
    title="ABCDH FastAPI",
    description="Backend de análisis e IA — agente de user stories",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(webhook.router)
app.include_router(predictions.router)


@app.on_event("startup")
def on_startup() -> None:
    routes = [f"{list(r.methods)} {r.path}" for r in app.routes if hasattr(r, "methods")]
    logger.info("FastAPI startup — registered routes: %s", routes)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("DB tables verified OK")
    except Exception as exc:
        logger.warning("Could not connect to DB on startup: %s", exc)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/debug/")
def debug() -> dict:
    import os, time
    import jwt as pyjwt
    from app.services.github_service import _GITHUB_APP_ID, _GITHUB_APP_PRIVATE_KEY

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    pk = _GITHUB_APP_PRIVATE_KEY
    pk_lines = pk.splitlines()
    jwt_ok = False
    jwt_error = None
    try:
        now = int(time.time())
        pyjwt.encode({"iat": now - 60, "exp": now + 600, "iss": _GITHUB_APP_ID}, pk, algorithm="RS256")
        jwt_ok = True
    except Exception as exc:
        jwt_error = str(exc)

    return {
        "anthropic_api_key_set": bool(anthropic_key),
        "github_app_id": _GITHUB_APP_ID or "(not set)",
        "private_key_line_count": len(pk_lines),
        "private_key_first_line": pk_lines[0] if pk_lines else "(empty)",
        "private_key_last_line": pk_lines[-1] if pk_lines else "(empty)",
        "has_begin_header": "BEGIN" in pk,
        "has_end_footer": "END" in pk,
        "jwt_ok": jwt_ok,
        "jwt_error": jwt_error,
    }
