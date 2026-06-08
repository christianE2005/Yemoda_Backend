import hmac
import logging
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
# Dedicated, REQUIRED secret — no silent fallback. If it's unset, require_internal_token rejects
# every call (fail-closed); the warning below surfaces the misconfiguration instead of a mystery 401.
_INTERNAL_TOKEN = os.getenv("FASTAPI_INTERNAL_TOKEN", "")
if not _INTERNAL_TOKEN:
    logging.getLogger(__name__).warning(
        "FASTAPI_INTERNAL_TOKEN is not set — internal endpoints will reject every call (401). "
        "Set it to the same value configured on the Django backend."
    )


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    if not _INTERNAL_TOKEN or not hmac.compare_digest(x_internal_token, _INTERNAL_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado.")
