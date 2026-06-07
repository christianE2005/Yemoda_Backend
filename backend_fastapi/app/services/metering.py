"""
AI usage metering + quota enforcement.

Quotas are per-seat, pooled across a project's members, and reset each calendar month:

    quota(category) = AI_QUOTA_<CAT>_PER_SEAT * seat_count(project)

Categories: 'reviews' (push + on-demand reviews), 'aifix' (the "resolve warnings" AI fix),
'chat' (general + code-review chat). Usage is tracked in `project_ai_usage` (one row per
project per month). When AI_METERING_ENFORCE is on and a category is exhausted, callers
should block (402 for manual chat/AI-fix; queue for automatic push reviews).

The per-seat values MUST match the Django service's AI_QUOTA_* settings (Django reports
usage; this service enforces it).
"""
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import Project, ProjectAiUsage, ProjectMember, Task

logger = logging.getLogger(__name__)

ENFORCE = os.getenv("AI_METERING_ENFORCE", "true").lower() == "true"

# Pro plan: per-seat allowance, pooled across members.
_PER_SEAT = {
    "reviews": int(os.getenv("AI_QUOTA_REVIEWS_PER_SEAT", "50")),
    "chat": int(os.getenv("AI_QUOTA_CHAT_PER_SEAT", "50")),
    "aifix": int(os.getenv("AI_QUOTA_AIFIX_PER_SEAT", "10")),
}
# Free plan: a flat cap for the whole project (not multiplied by seats).
_FREE_FLAT = {
    "reviews": int(os.getenv("AI_FREE_QUOTA_REVIEWS", "10")),
    "chat": int(os.getenv("AI_FREE_QUOTA_CHAT", "10")),
    "aifix": int(os.getenv("AI_FREE_QUOTA_AIFIX", "1")),
}
_COLUMN = {"reviews": "reviews_used", "chat": "chat_used", "aifix": "aifix_used"}


def current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def seat_count(db: Session, project_id: int) -> int:
    n = (
        db.query(func.count())
        .select_from(ProjectMember)
        .filter(ProjectMember.id_project == project_id)
        .scalar()
    ) or 0
    return max(int(n), 1)


def _project_plan(db: Session, project_id: int) -> str:
    plan = db.query(Project.plan).filter(Project.id_project == project_id).scalar()
    return plan or "free"


def quota(db: Session, project_id: int, category: str) -> int:
    """Monthly quota by plan: Pro = per-seat × seats; Free = flat project cap."""
    if _project_plan(db, project_id) == "pro":
        return _PER_SEAT[category] * seat_count(db, project_id)
    return _FREE_FLAT[category]


def resolve_project_id(db: Session, context_data: dict | None) -> int | None:
    """Best-effort: figure out which project a chat call should be billed to."""
    if not context_data:
        return None
    pid = context_data.get("project_id")
    if pid:
        return int(pid)
    task_id = context_data.get("task_id")
    if task_id:
        task = db.query(Task).filter(Task.id_task == int(task_id)).first()
        if task and task.id_project:
            return int(task.id_project)
    return None


def _get_or_create_usage(db: Session, project_id: int, period: str) -> ProjectAiUsage:
    row = db.query(ProjectAiUsage).filter_by(id_project=project_id, period=period).first()
    if row is not None:
        return row
    row = ProjectAiUsage(id_project=project_id, period=period, reviews_used=0, chat_used=0, aifix_used=0)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        # Concurrent create — fall back to the existing row. Re-SELECT after the rollback;
        # a racing transaction may not be visible until its commit, so retry once more if
        # needed rather than returning None (which would break the caller).
        db.rollback()
        row = db.query(ProjectAiUsage).filter_by(id_project=project_id, period=period).first()
        if row is None:
            row = db.query(ProjectAiUsage).filter_by(id_project=project_id, period=period).first()
    return row


def has_quota(
    db: Session, project_id: int, category: str, period: str | None = None
) -> tuple[bool, int, int]:
    """Whether the project can make one more call of this category (no mutation)."""
    period = period or current_period()
    q = quota(db, project_id, category)
    row = db.query(ProjectAiUsage).filter_by(id_project=project_id, period=period).first()
    used = getattr(row, _COLUMN[category]) if row else 0
    if ENFORCE and used >= q:
        return False, used, q
    return True, used, q


def _atomic_consume(
    db: Session, project_id: int, category: str, period: str, quota_limit: int | None = None
) -> int | None:
    """Atomically increment the period counter in a single SQL statement.

    The increment runs as `UPDATE ... SET col = col + 1 [AND col < :limit] RETURNING col`, so
    Postgres row-locks serialize concurrent callers — no lost updates, no TOCTOU overshoot. When
    `quota_limit` is given, the row matches only while still under quota; a 0-row result (None)
    means the quota is exhausted. `category` maps through the fixed `_COLUMN` whitelist, so the
    inlined column name is never user-controlled.
    """
    col = _COLUMN[category]
    _get_or_create_usage(db, project_id, period)  # ensure the row exists so the UPDATE can match
    cond = f" AND {col} < :limit" if quota_limit is not None else ""
    stmt = text(
        f"UPDATE project_ai_usage SET {col} = {col} + 1, updated_at = CURRENT_TIMESTAMP "
        f"WHERE id_project = :pid AND period = :period{cond} "
        f"RETURNING {col}"
    )
    params: dict = {"pid": project_id, "period": period}
    if quota_limit is not None:
        params["limit"] = quota_limit
    row = db.execute(stmt, params).first()
    db.commit()
    return row[0] if row else None


def consume(db: Session, project_id: int, category: str, period: str | None = None) -> int:
    """Record one used call of this category (unconditional). Returns the new used count.

    Pass the same `period` used by the preceding has_quota() pre-check so a month rollover
    between the check and the consume can't split them across two usage rows.
    """
    new_used = _atomic_consume(db, project_id, category, period or current_period())
    return new_used if new_used is not None else 0


def check_and_consume(db: Session, project_id: int, category: str) -> tuple[bool, int, int]:
    """Atomically gate AND record one call. Returns (allowed, used, quota).

    The check and the increment are a single atomic SQL statement, so two concurrent calls can
    never both pass at the last available unit.
    """
    period = current_period()  # computed once so a month rollover can't split check vs increment
    q = quota(db, project_id, category)
    if not ENFORCE:
        new_used = _atomic_consume(db, project_id, category, period)
        return True, (new_used if new_used is not None else 0), q
    new_used = _atomic_consume(db, project_id, category, period, quota_limit=q)
    if new_used is None:
        row = db.query(ProjectAiUsage).filter_by(id_project=project_id, period=period).first()
        used = getattr(row, _COLUMN[category]) if row else q
        return False, used, q
    return True, new_used, q
