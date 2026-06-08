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
from app.services.audit_service import (
    fetch_repo_source,
    finalize_batch,
    score_submission_normal,
    submit_batch,
    verify_findings_pass,
)

logger = logging.getLogger(__name__)

# Internet-exposed FastAPI host: only the Django backend should reach this. The shared internal
# token (require_internal_token) blocks anonymous callers from spending the owner's Anthropic budget.
router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_internal_token)])


class SubmissionAuditRequest(BaseModel):
    submission_id: int
    repo_url: str = Field(..., max_length=500)
    ref: str = Field(default="main", max_length=255)
    rubric: dict[str, int] = Field(default_factory=dict)
    processing_mode: str = Field(default="normal", max_length=10)  # 'normal' | 'batch'
    verify_findings: bool = False  # high-fidelity: adversarially re-judge critical/high findings


def _run_audit(
    submission_id: int,
    repo_url: str,
    ref: str,
    rubric: dict[str, int],
    processing_mode: str,
    verify: bool,
) -> None:
    """Background worker: fetch the repo, then either score it now (normal) or submit a batch.

    IMPORTANT: this is a plain `def`, so Starlette runs it in a threadpool (off the event loop).
    fetch_repo_source + score_submission_normal + submit_batch do BLOCKING network + Anthropic SDK
    + synchronous DB I/O; running it on the main event loop would freeze the whole FastAPI process
    during the model call. Mirrors webhook.py's _process_push.

    - normal: chunk + score every chunk synchronously, write status='done' + results.
    - batch:  submit one Message Batch request per chunk, store batch_id + batch_meta, set
              status='batch_pending' (NOT scored yet — the /drain-batches/ poller finalizes it).
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

            if processing_mode == "batch":
                batch_id, batch_meta = submit_batch(
                    files, rubric or {}, verify=verify, repo_url=repo_url, ref=ref
                )
                if batch_id is None:
                    # No analyzable files -> nothing to batch; finish now with a deterministic
                    # empty result so the row never gets stuck in batch_pending.
                    result = score_submission_normal(files, rubric or {})
                    submission.batch_meta = batch_meta
                    submission.status = "done"
                    submission.score = result["score"]
                    submission.score_breakdown = result["score_breakdown"]
                    submission.findings = result["findings"]
                    submission.summary = result["summary"]
                    submission.error = None
                    submission.analyzed_at = func.now()
                    db.commit()
                    logger.info("Audit: submission %s batch had no files — scored empty", submission_id)
                    return

                submission.batch_id = batch_id
                submission.batch_meta = batch_meta
                submission.status = "batch_pending"
                submission.error = None
                db.commit()
                logger.info(
                    "Audit: submission %s submitted batch %s (%s chunks) — pending",
                    submission_id, batch_id, (batch_meta or {}).get("n_chunks"),
                )
                return

            result = score_submission_normal(files, rubric or {})
            if verify:
                # High-fidelity: adversarially re-judge critical/high findings against their
                # cited source. Scores are untouched; on failure keep the result as-is.
                try:
                    result["findings"] = verify_findings_pass(files, result["findings"])
                except Exception as exc:
                    logger.info("Audit: submission %s verify skipped: %s", submission_id, exc)
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

    mode = body.processing_mode if body.processing_mode in ("normal", "batch") else "normal"

    background_tasks.add_task(
        _run_audit,
        body.submission_id,
        body.repo_url,
        body.ref or "main",
        body.rubric or {},
        mode,
        body.verify_findings,
    )

    return {"detail": "queued", "submission_id": body.submission_id, "processing_mode": mode}


_DRAIN_BATCH_LIMIT = 50  # max batch_pending submissions finalized per drain call


@router.post("/drain-batches/")
def drain_batches():
    """Finalize batch-mode submissions whose Message Batch has finished.

    Polled server-to-server (e.g. by a cron in the Django backend). For each batch_pending
    submission with a batch_id, retrieve the batch: if it has ended, reduce its chunk results
    and write status='done' + scores; if a batch can't be finalized it's left pending for the
    next poll, and an errored batch marks the submission 'failed'. Best-effort per row.

    Runs as a plain sync `def` so Starlette executes it in a threadpool — finalize_batch does
    BLOCKING Anthropic SDK + synchronous DB I/O. Returns a small count summary.
    """
    import anthropic

    db: Session = SessionLocal()
    finalized = 0
    failed = 0
    still_pending = 0
    try:
        rows = (
            db.query(HackathonSubmission)
            .filter(
                HackathonSubmission.status == "batch_pending",
                HackathonSubmission.batch_id.isnot(None),
            )
            .limit(_DRAIN_BATCH_LIMIT)
            .all()
        )

        if not rows:
            return {"checked": 0, "finalized": 0, "failed": 0, "pending": 0}

        client = anthropic.Anthropic()
        for submission in rows:
            try:
                rubric = (submission.batch_meta or {}).get("rubric") or {}
                result = finalize_batch(
                    client, submission.batch_id, submission.batch_meta or {}, rubric
                )
                if result is None:
                    still_pending += 1
                    continue  # batch not ended yet — try again next drain.

                submission.status = "done"
                submission.score = result["score"]
                submission.score_breakdown = result["score_breakdown"]
                submission.findings = result["findings"]
                submission.summary = result["summary"]
                submission.error = None
                submission.analyzed_at = func.now()
                db.commit()
                finalized += 1
                logger.info(
                    "Drain: submission %s finalized batch %s -> score %s",
                    submission.id_submission, submission.batch_id, result["score"],
                )
            except Exception as exc:
                logger.error(
                    "Drain: submission %s batch %s failed: %s",
                    submission.id_submission, submission.batch_id, exc,
                )
                db.rollback()
                try:
                    submission.status = "failed"
                    submission.error = str(exc)[:1000]
                    submission.analyzed_at = func.now()
                    db.commit()
                    failed += 1
                except Exception:
                    db.rollback()

        return {
            "checked": len(rows),
            "finalized": finalized,
            "failed": failed,
            "pending": still_pending,
        }
    finally:
        db.close()
