import logging

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Board, GithubPushEvent, Project, Task, TaskComment, TaskPushMatch, TaskStatus, TaskWarning

logger = logging.getLogger(__name__)


def get_project_by_repo(db: Session, repo_full_name: str) -> Project | None:
    all_projects = db.query(Project.id_project, Project.github_repo_full_name).all()
    logger.info(
        "DB project lookup: searching '%s' among %d projects: %s",
        repo_full_name,
        len(all_projects),
        [(p.id_project, p.github_repo_full_name) for p in all_projects],
    )
    return (
        db.query(Project)
        .filter(func.lower(Project.github_repo_full_name) == repo_full_name.lower())
        .first()
    )


def get_active_tasks(db: Session, project_id: int) -> list[Task]:
    """Return all tasks for a project that are not yet completed."""
    return (
        db.query(Task)
        .join(Board, Task.id_board == Board.id_board)
        .filter(
            Board.id_project == project_id,
            Task.completed_at.is_(None),
        )
        .all()
    )


def get_review_status(db: Session) -> TaskStatus | None:
    return db.query(TaskStatus).filter(TaskStatus.name == "Review").first()


def move_task_to_review(db: Session, task: Task, review_status_id: int) -> None:
    task.id_status = review_status_id
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


def create_warning(db: Session, task_id: int, message: str, push_id: int | None = None) -> TaskWarning:
    warning = TaskWarning(
        id_task=task_id,
        message=message,
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
) -> GithubPushEvent:
    """Create a new GithubPushEvent record and return it."""
    push_event = GithubPushEvent(
        id_project=project_id,
        repo_full_name=repo_full_name,
        ref=ref,
        pusher=pusher,
        commits=commits,
    )
    db.add(push_event)
    db.commit()
    db.refresh(push_event)
    return push_event
