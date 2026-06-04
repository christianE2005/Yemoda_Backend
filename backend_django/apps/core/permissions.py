"""
Project-level authorization helpers built on per-project custom roles (ProjectRole).

The project creator and system admins always have full access. Everyone else is
authorized by the permission booleans on the ProjectRole assigned to their
ProjectMember row. `max_move_column` caps how far a role may move a task on the board.
"""
from __future__ import annotations

from rest_framework.exceptions import PermissionDenied

from .models import BoardColumn, ProjectMember, ProjectRole

# Default role set seeded for every new project.
_ALL_PERMS = ProjectRole.PERMISSION_FIELDS


def _user_id(user) -> int | None:
    return getattr(user, "id_user", None) or getattr(user, "id", None)


def is_project_admin(user, project) -> bool:
    """The project creator or a system admin — bypasses all per-role checks."""
    if user is None or project is None:
        return False
    if getattr(user, "is_admin", False):
        return True
    return project.created_by_id is not None and project.created_by_id == _user_id(user)


def get_project_role(user, project) -> ProjectRole | None:
    """The ProjectRole assigned to this user in this project (None if not a member)."""
    uid = _user_id(user)
    if uid is None or project is None:
        return None
    member = (
        ProjectMember.objects
        .select_related("project_role")
        .filter(project=project, user_id=uid)
        .first()
    )
    return member.project_role if member else None


def has_project_perm(user, project, perm: str) -> bool:
    """True if the user may perform the given capability in the project."""
    if is_project_admin(user, project):
        return True
    role = get_project_role(user, project)
    if role is None:
        return False
    if role.is_admin_role:
        return True
    return bool(getattr(role, perm, False))


def can_move_task_to_column(user, project, target_column: BoardColumn | None) -> tuple[bool, str | None]:
    """
    Whether the user may move a task into target_column.

    Returns (allowed, reason). Enforces can_move_tasks and the role's max_move_column
    cap (a task may only move into columns whose order <= the cap column's order).
    """
    if is_project_admin(user, project):
        return True, None
    role = get_project_role(user, project)
    if role is None:
        return False, "You are not a member of this project."
    if role.is_admin_role:
        return True, None
    if not role.can_move_tasks:
        return False, "Your role cannot move tasks."
    cap = role.max_move_column
    if cap is not None and target_column is not None and target_column.order > cap.order:
        return False, f"Your role can only move tasks up to the '{cap.name}' column."
    return True, None


def require_perm(user, project, perm: str) -> None:
    """Raise PermissionDenied unless the user has the capability."""
    if not has_project_perm(user, project, perm):
        raise PermissionDenied("Your project role does not allow this action.")


def assert_can_assign_role(user, project, role) -> None:
    """The full-access (admin) role can only be granted by a project admin (creator/system admin).

    Without this, anyone holding `can_manage_members` could elevate themselves or others to
    full project admin — a privilege escalation. `can_manage_members` is itself grantable to
    non-admins, so the admin role must be gated separately.
    """
    if role is not None and getattr(role, "is_admin_role", False) and not is_project_admin(user, project):
        raise PermissionDenied("Solo el administrador del proyecto puede asignar el rol de Admin.")


def resolve_capabilities(user, project) -> dict:
    """
    Flatten the effective capabilities for the current user in the project, for the
    frontend to gate its UI. Admins/creator get everything.
    """
    admin = is_project_admin(user, project)
    role = None if admin else get_project_role(user, project)
    role_is_admin = bool(role and role.is_admin_role)
    full = admin or role_is_admin

    caps = {perm: (full or bool(getattr(role, perm, False))) for perm in _ALL_PERMS}
    cap_col = getattr(role, "max_move_column", None) if (role and not role_is_admin) else None
    caps.update({
        "is_project_admin": admin,
        "project_role_id": getattr(role, "id_project_role", None),
        "project_role_name": "Admin" if full else getattr(role, "name", None),
        # Tasks may only be moved into columns with order <= this value (null = no limit).
        "max_move_column_id": getattr(cap_col, "id_column", None),
        "max_move_column_order": getattr(cap_col, "order", None),
    })
    return caps


# ── Default role seeding (runtime, mirrors migration 0046) ───────────────────

def seed_default_project_roles(project) -> None:
    """Create the default role set for a project if it has none yet."""
    if ProjectRole.objects.filter(project=project).exists():
        return

    def make(name, desc, perms, is_admin=False, max_col=None):
        kwargs = {p: (p in perms) for p in _ALL_PERMS}
        ProjectRole.objects.create(
            project=project,
            name=name,
            description=desc,
            is_system=True,
            is_admin_role=is_admin,
            max_move_column=max_col,
            **kwargs,
        )

    cols = list(BoardColumn.objects.filter(board__project_id=project.id_project).order_by("order"))
    review_col = next((c for c in cols if c.is_review), None)
    cap_col = review_col or next((c for c in reversed(cols) if not c.is_final), None)

    make("Admin", "Full access to the project.", list(_ALL_PERMS), is_admin=True)
    make(
        "Editor",
        "Create and manage tasks, sprints, milestones and tags.",
        [
            "can_create_tasks", "can_edit_tasks", "can_delete_tasks", "can_move_tasks",
            "can_manage_sprints", "can_manage_milestones", "can_manage_tags",
            "can_comment", "can_trigger_ai",
        ],
    )
    make(
        "Contributor",
        "Work on tasks (move up to the review column) and comment.",
        ["can_create_tasks", "can_edit_tasks", "can_move_tasks", "can_comment", "can_trigger_ai"],
        max_col=cap_col,
    )
    make("Viewer", "Read-only access to the project.", [])
