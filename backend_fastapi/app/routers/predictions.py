import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.services import ml_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["predictions"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    project_id: int


class PredictionResponse(BaseModel):
    project_id: int
    at_risk: bool
    confidence: float | None
    predicted_end_date: str | None
    days_delay_estimate: int | None
    model_used: str
    features: dict


class TrainResponse(BaseModel):
    status: str
    reason: str | None = None
    samples: int | None = None
    r2_score: float | None = None
    alpha: float | None = None
    l1_ratio: float | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/project-risk/", response_model=PredictionResponse, status_code=status.HTTP_200_OK)
def predict_project_risk(body: PredictRequest, db: Session = Depends(get_db)) -> PredictionResponse:
    """
    Predict whether a project is at risk of missing its deadline.

    Uses a trained ElasticNet model when available; falls back to a
    deterministic burndown calculation when there is not enough historical
    data to train.

    Requires the project to have at least one task and an end_date set.
    """
    result = ml_service.predict_risk(db, body.project_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or has no tasks / end_date configured.",
        )

    return PredictionResponse(project_id=body.project_id, **result)


@router.post("/train/", response_model=TrainResponse, status_code=status.HTTP_200_OK)
def trigger_training(db: Session = Depends(get_db)) -> TrainResponse:
    """
    Trigger a model (re)training run using all completed projects in the DB.

    Safe to call repeatedly — overwrites the previous model file.
    Returns 'skipped' if there are not enough completed projects yet.
    """
    result = ml_service.train_model(db)
    logger.info("Training triggered manually: %s", result)
    return TrainResponse(**result)
