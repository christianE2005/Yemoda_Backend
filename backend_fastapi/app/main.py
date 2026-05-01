import logging
import sys

from fastapi import FastAPI

from app.core.database import Base, engine
from app.routers import branches, ml, webhook

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ABCDH FastAPI",
    description="Backend de análisis e IA — agente de user stories",
    version="1.0.0",
)

app.include_router(webhook.router)
app.include_router(ml.router)
app.include_router(branches.router)


@app.on_event("startup")
def on_startup() -> None:
    routes = [f"{list(r.methods)} {r.path}" for r in app.routes if hasattr(r, "methods")]
    logger.info("FastAPI startup — registered routes: %s", routes)
    try:
        # Auto-create FastAPI-managed tables (e.g. branch_story_link)
        from app.models.models import BranchStoryLink  # noqa: F401
        BranchStoryLink.__table__.create(engine, checkfirst=True)
        logger.info("branch_story_link table ensured")
    except Exception as exc:
        logger.warning("Could not create branch_story_link table: %s", exc)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("DB tables verified OK")
    except Exception as exc:
        logger.warning("Could not connect to DB on startup: %s", exc)
    # Preload embedding model to reduce cold-start latency on first request
    try:
        from app.services.ml_service import _get_model

        _get_model()
        logger.info("Embedding model preloaded on startup")
    except Exception as exc:
        logger.warning("Could not preload embedding model on startup: %s", exc)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
