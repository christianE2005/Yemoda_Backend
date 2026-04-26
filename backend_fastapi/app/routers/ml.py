from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ml_service import match_stories, invalidate_story_embedding

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


@router.post("/cache/invalidate/{story_id}")
def invalidate_cache_endpoint(story_id: int):
    try:
        invalidate_story_embedding(story_id)
        return JSONResponse({"invalidated": story_id})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
