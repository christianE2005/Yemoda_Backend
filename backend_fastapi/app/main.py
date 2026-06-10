import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.database import Base, SessionLocal, engine
from app.routers import audit, predictions, webhook, chat

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])


def _ensure_ml_model() -> None:
    """Retrain the risk model if its files are missing (e.g. after a redeploy).

    The model is persisted on local disk, which is ephemeral on Railway — every deploy or
    restart wiped it and silently degraded predictions to the rule-based fallback until
    someone called /predictions/train/ by hand. Training is cheap (a few completed projects),
    so recover it at startup. Concurrent workers may race here; _dump_model_atomic makes the
    file swap safe regardless of who wins.
    """
    from app.services import ml_service

    if ml_service.MODEL_PATH.exists() and ml_service.SCALER_PATH.exists():
        return
    db = SessionLocal()
    try:
        result = ml_service.train_model(db)
        logger.info("Startup ML training: %s", result)
    except Exception as exc:
        logger.warning("Startup ML training failed (predictions fall back to burndown): %s", exc)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    routes = [f"{list(r.methods)} {r.path}" for r in app.routes if hasattr(r, "methods")]
    logger.info("FastAPI startup — registered routes: %s", routes)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("DB tables verified OK")
    except Exception as exc:
        logger.warning("Could not connect to DB on startup: %s", exc)
    _ensure_ml_model()
    yield


app = FastAPI(
    title="ABCDH FastAPI",
    description="Backend de análisis e IA — agente de user stories",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(webhook.router)
app.include_router(predictions.router)
app.include_router(chat.router)
app.include_router(chat.router, prefix="/api")
app.include_router(audit.router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
