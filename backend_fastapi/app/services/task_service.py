from sqlalchemy.orm import Session

from app.models.models import Board, Project, Task, TaskComment, TaskStatus


def get_project_by_repo(db: Session, repo_full_name: str) -> Project | None:
    return db.query(Project).filter(Project.github_repo_full_name == repo_full_name).first()


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
