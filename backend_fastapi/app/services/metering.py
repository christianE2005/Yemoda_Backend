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

from sqlalchemy import func
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
        # Concurrent create — fall back to the existing row.
        db.rollback()
        row = db.query(ProjectAiUsage).filter_by(id_project=project_id, period=period).first()
    return row


def has_quota(db: Session, project_id: int, category: str) -> tuple[bool, int, int]:
    """Whether the project can make one more call of this category (no mutation)."""
    q = quota(db, project_id, category)
    row = db.query(ProjectAiUsage).filter_by(id_project=project_id, period=current_period()).first()
    used = getattr(row, _COLUMN[category]) if row else 0
    if ENFORCE and used >= q:
        return False, used, q
    return True, used, q


def consume(db: Session, project_id: int, category: str) -> int:
    """Record one used call of this category. Returns the new used count."""
    row = _get_or_create_usage(db, project_id, current_period())
    col = _COLUMN[category]
    setattr(row, col, (getattr(row, col) or 0) + 1)
    db.commit()
    return getattr(row, col)


def check_and_consume(db: Session, project_id: int, category: str) -> tuple[bool, int, int]:
    """If under quota (or enforcement off), record the call and allow it. Returns (allowed, used, quota)."""
    allowed, used, q = has_quota(db, project_id, category)
    if not allowed:
        return False, used, q
    new_used = consume(db, project_id, category)
    return True, new_used, q
