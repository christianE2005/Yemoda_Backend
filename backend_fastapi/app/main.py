import logging
import sys

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.database import Base, engine
from app.routers import audit, predictions, webhook, chat

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
app.include_router(chat.router)
app.include_router(chat.router, prefix="/api")
app.include_router(audit.router, prefix="/api")


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
