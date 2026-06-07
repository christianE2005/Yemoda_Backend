"""
Hackathon Robustness Score — internal audit router.

Server-to-server only: the Django backend calls POST /audit/submission/ with the shared
internal token. We return 202 immediately and run the analysis in a BackgroundTask, writing
the result DIRECTLY into the hackathon_submission row on the shared Postgres (no callback).
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.deps import require_internal_token
from app.models.models import HackathonSubmission
from app.services.audit_service import fetch_repo_source, score_submission

logger = logging.getLogger(__name__)

# Internet-exposed FastAPI host: only the Django backend should reach this. The shared internal
# token (require_internal_token) blocks anonymous callers from spending the owner's Anthropic budget.
router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_internal_token)])


class SubmissionAuditRequest(BaseModel):
    submission_id: int
    repo_url: str = Field(..., max_length=500)
    ref: str = Field(default="main", max_length=255)
    rubric: dict[str, int] = Field(default_factory=dict)


def _run_audit(submission_id: int, repo_url: str, ref: str, rubric: dict[str, int]) -> None:
    """Background worker: fetch the repo, score it, and persist the result.

    IMPORTANT: this is a plain `def`, so Starlette runs it in a threadpool (off the event loop).
    fetch_repo_source + score_submission do BLOCKING network + Anthropic SDK + synchronous DB I/O;
    running it on the main event loop would freeze the whole FastAPI process during the model call.
    Mirrors webhook.py's _process_push.
    """
    db: Session = SessionLocal()
    try:
        submission = (
            db.query(HackathonSubmission)
            .filter(HackathonSubmission.id_submission == submission_id)
            .first()
        )
        if submission is None:
            logger.warning("Audit: submission %s not found — skipping", submission_id)
            return

        submission.status = "running"
        db.commit()

        try:
            files = fetch_repo_source(repo_url, ref)
            logger.info("Audit: submission %s fetched %d source file(s)", submission_id, len(files))
            result = score_submission(files, rubric or {})

            submission.status = "done"
            submission.score = result["score"]
            submission.score_breakdown = result["score_breakdown"]
            submission.findings = result["findings"]
            submission.summary = result["summary"]
            submission.error = None
            submission.analyzed_at = func.now()
            db.commit()
            logger.info("Audit: submission %s scored %s", submission_id, result["score"])
        except Exception as exc:
            logger.error("Audit: submission %s failed: %s", submission_id, exc)
            db.rollback()
            submission.status = "failed"
            submission.error = str(exc)[:1000]
            submission.analyzed_at = func.now()
            db.commit()
    finally:
        db.close()


@router.post("/submission/", status_code=status.HTTP_202_ACCEPTED)
def audit_submission(body: SubmissionAuditRequest, background_tasks: BackgroundTasks):
    """Queue a hackathon submission for robustness scoring.

    Called server-to-server by the Django API. Returns 202 immediately; the BackgroundTask
    runs the analysis in a threadpool and writes the result into the hackathon_submission row.
    """
    if not body.repo_url.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo_url es requerido.")

    background_tasks.add_task(
        _run_audit,
        body.submission_id,
        body.repo_url,
        body.ref or "main",
        body.rubric or {},
    )

    return {"detail": "queued", "submission_id": body.submission_id}
