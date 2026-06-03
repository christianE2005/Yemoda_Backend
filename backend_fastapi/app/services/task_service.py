import logging

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Board, BoardColumn, GithubPushEvent, Project, ProjectRepo, Task, TaskComment, TaskPushMatch, TaskWarning

logger = logging.getLogger(__name__)


def get_project_by_repo(db: Session, repo_full_name: str) -> Project | None:
    # Try project_repo table first
    project_repo = (
        db.query(ProjectRepo)
        .filter(func.lower(ProjectRepo.repo_full_name) == repo_full_name.lower())
        .first()
    )
    if project_repo:
        return db.query(Project).filter(Project.id_project == project_repo.id_project).first()
    # Fallback: check Project.github_repo_full_name directly
    return (
        db.query(Project)
        .filter(func.lower(Project.github_repo_full_name) == repo_full_name.lower())
        .first()
    )


def get_board_coding_style(db: Session, project_id: int) -> str:
    """Return the coding_style of the board that has the review column, or 'standard'."""
    board = (
        db.query(Board)
        .join(BoardColumn, BoardColumn.id_board == Board.id_board)
        .filter(
            Board.id_project == project_id,
            BoardColumn.is_review.is_(True),
        )
        .first()
    )
    if board:
        return board.coding_style or "standard"
    # Fallback: first board of the project
    board = db.query(Board).filter(Board.id_project == project_id).first()
    return board.coding_style if board else "standard"


def get_board_review_settings(db: Session, project_id: int) -> tuple[str, str, str, str, str, str | None]:
    """Return (coding_style, review_focus, tech_stack, naming_convention, response_language, custom_instructions) for the board with the review column."""
    board = (
        db.query(Board)
        .join(BoardColumn, BoardColumn.id_board == Board.id_board)
        .filter(
            Board.id_project == project_id,
            BoardColumn.is_review.is_(True),
        )
        .first()
    )
    if not board:
        board = db.query(Board).filter(Board.id_project == project_id).first()
    if not board:
        return "standard", "general", "mixed", "default", "es", None
    return (
        board.coding_style or "standard",
        board.review_focus or "general",
        board.tech_stack or "mixed",
        board.naming_convention or "default",
        board.response_language or "es",
        board.custom_instructions or None,
    )


def get_active_tasks(db: Session, project_id: int) -> list[Task]:
    """Return all incomplete tasks for a project."""
    return (
        db.query(Task)
        .filter(
            Task.id_project == project_id,
            Task.completed_at.is_(None),
        )
        .all()
    )


def filter_task_subtree(tasks: list[Task], root_id: int) -> list[Task]:
    """Return the task with id root_id plus all of its descendants found in tasks.

    Used for task-targeted branches ({task_id}-...): when the branch targets a
    parent task we also pull its active subtasks so the agent sees the breakdown.
    """
    by_id = {t.id_task: t for t in tasks}
    children: dict[int, list[Task]] = {}
    for t in tasks:
        parent_id = getattr(t, "id_parent_task", None)
        if parent_id is not None:
            children.setdefault(parent_id, []).append(t)

    result: list[Task] = []
    seen: set[int] = set()
    stack = [root_id]
    while stack:
        tid = stack.pop()
        if tid in seen:
            continue
        seen.add(tid)
        task = by_id.get(tid)
        if task is not None:
            result.append(task)
        for child in children.get(tid, []):
            stack.append(child.id_task)
    return result


def build_story_tree(tasks: list[Task]) -> list[dict]:
    """Build a nested story structure from a flat list of active tasks.

    Each node is {id, title, description, subtasks: [...]}. A subtask is nested
    under its parent when the parent is also in the list; otherwise it becomes a
    root. This lets the agent reason about a parent task together with its subtasks.
    """
    nodes = {
        t.id_task: {
            "id": t.id_task,
            "title": t.title,
            "description": t.description,
            "subtasks": [],
        }
        for t in tasks
    }
    roots: list[dict] = []
    for t in tasks:
        parent_id = getattr(t, "id_parent_task", None)
        if parent_id is not None and parent_id in nodes:
            nodes[parent_id]["subtasks"].append(nodes[t.id_task])
        else:
            roots.append(nodes[t.id_task])
    return roots


def get_review_column(db: Session, project_id: int) -> BoardColumn | None:
    """Find the board column marked as is_review in any board of the project."""
    return (
        db.query(BoardColumn)
        .join(Board, BoardColumn.id_board == Board.id_board)
        .filter(
            Board.id_project == project_id,
            BoardColumn.is_review.is_(True),
        )
        .first()
    )


def move_task_to_review(db: Session, task: Task, review_column_id: int) -> None:
    task.id_column = review_column_id
    db.commit()
    db.refresh(task)


def add_agent_comment(db: Session, task_id: int, content: str) -> TaskComment:
    comment = TaskComment(id_task=task_id, id_user=None, content=content)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def get_active_warnings(db: Session, task_id: int) -> list[TaskWarning]:
    return (
        db.query(TaskWarning)
        .filter(TaskWarning.id_task == task_id, TaskWarning.status == "active")
        .all()
    )


def create_warning(db: Session, task_id: int, message: str, push_id: int | None = None, severity: str = "warning") -> TaskWarning:
    normalized_message = " ".join((message or "").split()).strip().lower()
    existing = (
        db.query(TaskWarning)
        .filter(
            TaskWarning.id_task == task_id,
            TaskWarning.status == "active",
            TaskWarning.severity == severity,
        )
        .all()
    )
    for warning in existing:
        current_message = " ".join((warning.message or "").split()).strip().lower()
        if current_message == normalized_message:
            if push_id is not None and warning.id_push_created != push_id:
                warning.id_push_created = push_id
                db.commit()
                db.refresh(warning)
            return warning

    warning = TaskWarning(
        id_task=task_id,
        message=message,
        severity=severity,
        status="active",
        id_push_created=push_id,
    )
    db.add(warning)
    db.commit()
    db.refresh(warning)
    return warning


def resolve_warning(db: Session, warning: TaskWarning) -> None:
    warning.status = "resolved"
    warning.resolved_at = datetime.now(timezone.utc)
    db.commit()


def create_push_match(
    db: Session,
    task_id: int,
    push_id: int,
    coverage: str,
    reason: str | None,
    code_snippet: str | None,
) -> TaskPushMatch:
    """Create or update a TaskPushMatch record linking a task to a push event."""
    existing = (
        db.query(TaskPushMatch)
        .filter(TaskPushMatch.id_task == task_id, TaskPushMatch.id_push == push_id)
        .first()
    )
    if existing:
        existing.coverage = coverage
        existing.reason = reason
        existing.code_snippet = code_snippet
        db.commit()
        db.refresh(existing)
        return existing

    match = TaskPushMatch(
        id_task=task_id,
        id_push=push_id,
        coverage=coverage,
        reason=reason,
        code_snippet=code_snippet,
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


def create_or_get_push_event(
    db: Session,
    project_id: int,
    repo_full_name: str,
    ref: str,
    pusher: str | None,
    commits: list,
    diff_text: str | None = None,
) -> GithubPushEvent:
    """Create or reuse a GithubPushEvent to avoid duplicate rows per same push.

    Django's webhook endpoint can persist the raw push first, then forward the same
    payload to FastAPI for analysis. Without idempotency this creates 2 rows for a
    single GitHub push. We reuse a recent matching row and only enrich diff_text.
    """
    # 15-minute window is enough for forwarded/retried deliveries of the same push.
    recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    candidate_events = (
        db.query(GithubPushEvent)
        .filter(
            GithubPushEvent.id_project == project_id,
            func.lower(GithubPushEvent.repo_full_name) == repo_full_name.lower(),
            GithubPushEvent.ref == ref,
            GithubPushEvent.pusher == pusher,
            GithubPushEvent.received_at >= recent_cutoff,
        )
        .order_by(GithubPushEvent.received_at.desc())
        .limit(20)
        .all()
    )
    existing = next((ev for ev in candidate_events if (ev.commits or []) == (commits or [])), None)

    if existing:
        # If Django stored the event first (without diff), enrich it here.
        if diff_text and not existing.diff_text:
            existing.diff_text = diff_text
            db.commit()
            db.refresh(existing)
        return existing

    push_event = GithubPushEvent(
        id_project=project_id,
        repo_full_name=repo_full_name,
        ref=ref,
        pusher=pusher,
        commits=commits,
        diff_text=diff_text,
    )
    db.add(push_event)
    db.commit()
    db.refresh(push_event)
    return push_event
