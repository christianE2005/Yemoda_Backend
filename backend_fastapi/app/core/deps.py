import hmac
import os
from collections.abc import Generator

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Shared service-to-service token. These FastAPI endpoints are NOT meant to be reachable from
# the browser — only the Django backend calls them — so we require a secret header. Without this,
# the directly-exposed FastAPI host can be hit anonymously (unlimited paid-model abuse).
_INTERNAL_TOKEN = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    if not _INTERNAL_TOKEN or not hmac.compare_digest(x_internal_token, _INTERNAL_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado.")
