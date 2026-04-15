import logging

from fastapi import FastAPI

from app.core.database import Base, engine
from app.routers import webhook

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ABCDH FastAPI",
    description="Backend de análisis e IA — agente de user stories",
    version="1.0.0",
)

app.include_router(webhook.router)


@app.on_event("startup")
def on_startup() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.warning("Could not create DB tables on startup (may already exist): %s", exc)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
