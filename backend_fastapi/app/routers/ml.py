from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.ml_service import match_stories

router = APIRouter(prefix="/ml", tags=["ml"])


class MatchRequest(BaseModel):
    repo_full_name: str
    diff: str
    top_k: int = 3
    min_sim: float = 0.55


@router.post("/match/")
def match_endpoint(payload: MatchRequest):
    db: Session = SessionLocal()
    try:
        matches = match_stories(db, payload.repo_full_name, payload.diff, payload.top_k, payload.min_sim)
    finally:
        db.close()

    return {"matches": matches}
