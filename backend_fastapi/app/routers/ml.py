from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ml_service import match_stories

router = APIRouter(prefix="/ml", tags=["ml"])


class MatchRequest(BaseModel):
    repo_full_name: str
    diff: str
    top_k: int = 3
    min_sim: float = 0.55


@router.post("/match/")
def match_endpoint(payload: MatchRequest, db: Session = Depends(get_db)):
    matches = match_stories(db, payload.repo_full_name, payload.diff, top_k=payload.top_k, min_sim=payload.min_sim)
    return {"matches": matches}
