from fastapi import FastAPI

from app.core.database import Base, engine

app = FastAPI(
    title="ABCDH FastAPI",
    description="Backend base en FastAPI",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
