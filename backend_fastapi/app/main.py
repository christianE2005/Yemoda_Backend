import logging
import sys

from fastapi import FastAPI

from app.core.database import Base, engine
from app.routers import webhook, ml

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
