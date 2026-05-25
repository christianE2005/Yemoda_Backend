from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserAccount(Base):
    __tablename__ = "user_account"

    id_user: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Project(Base):
    __tablename__ = "project"

    id_project: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    end_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_account.id_user", ondelete="SET NULL"),
        nullable=True,
    )
    github_repo_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)


class ProjectRepo(Base):
    __tablename__ = "project_repo"

    id_project_repo: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_project: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("project.id_project", ondelete="CASCADE"),
        nullable=False,
    )
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Role(Base):
    __tablename__ = "role"

    id_role: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectMember(Base):
    __tablename__ = "project_member"
    id_user: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_account.id_user", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    id_project: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("project.id_project", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    id_role: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("role.id_role", ondelete="SET NULL"),
        nullable=True,
    )
    joined_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Board(Base):
    __tablename__ = "board"

    id_board: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_project: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("project.id_project", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    coding_style: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    review_focus: Mapped[str] = mapped_column(String(10), nullable=False, default="general")
    tech_stack: Mapped[str] = mapped_column(String(20), nullable=False, default="mixed")
    naming_convention: Mapped[str] = mapped_column(String(20), nullable=False, default="default")
    response_language: Mapped[str] = mapped_column(String(5), nullable=False, default="es")
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class BoardColumn(Base):
    __tablename__ = "board_column"

    id_column: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_board: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("board.id_board", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_final: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    is_review: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)


class TaskStatus(Base):
    __tablename__ = "task_status"

    id_status: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskPriority(Base):
    __tablename__ = "task_priority"

    id_priority: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)


class Task(Base):
    __tablename__ = "task"

    id_task: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_project: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project.id_project", ondelete="CASCADE"),
        nullable=True,
    )
    id_column: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("board_column.id_column", ondelete="SET NULL"),
        nullable=True,
    )
    id_sprint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_priority: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("task_priority.id_priority", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    due_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    scrum_number: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TaskComment(Base):
    __tablename__ = "task_comment"

    id_comment: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_task: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("task.id_task", ondelete="CASCADE"),
        nullable=False,
    )
    id_user: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_account.id_user", ondelete="SET NULL"),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id_activity: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_user: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_account.id_user", ondelete="SET NULL"),
        nullable=True,
    )
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class GithubPushEvent(Base):
    __tablename__ = "github_push_event"

    id_push: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_project: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project.id_project", ondelete="CASCADE"),
        nullable=True,
    )
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ref: Mapped[str] = mapped_column(String(255), nullable=False)
    pusher: Mapped[str | None] = mapped_column(String(150), nullable=True)
    commits: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    received_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class TaskWarning(Base):
    __tablename__ = "task_warning"

    id_warning: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_task: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("task.id_task", ondelete="CASCADE"),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="warning")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    id_push_created: Mapped[int | None] = mapped_column(Integer, nullable=True)
    id_push_resolved: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TaskPushMatch(Base):
    __tablename__ = "task_push_match"

    id_match: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_task: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("task.id_task", ondelete="CASCADE"),
        nullable=False,
    )
    id_push: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("github_push_event.id_push", ondelete="CASCADE"),
        nullable=False,
    )
    coverage: Mapped[str] = mapped_column(String(10), nullable=False, default="partial")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
