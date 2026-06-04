import django.db.models.deletion
from django.db import migrations, models


# Permission boolean fields shared by the model and the seeding logic.
_ALL_PERMS = [
    "can_create_tasks",
    "can_edit_tasks",
    "can_delete_tasks",
    "can_move_tasks",
    "can_manage_sprints",
    "can_manage_board",
    "can_manage_milestones",
    "can_manage_tags",
    "can_comment",
    "can_manage_members",
    "can_manage_project",
    "can_trigger_ai",
]

# legacy global role name (lowercase) -> new per-project default role name
_LEGACY_MAP = {
    "project manager": "Admin",
    "product owner": "Editor",
    "scrum master": "Editor",
    "developer": "Contributor",
    "stakeholder": "Viewer",
    "admin": "Admin",
    "manager": "Admin",
}


def seed_project_roles(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    ProjectRole = apps.get_model("core", "ProjectRole")
    ProjectMember = apps.get_model("core", "ProjectMember")
    BoardColumn = apps.get_model("core", "BoardColumn")

    def make(project, name, desc, perms, is_admin=False, max_col=None):
        kwargs = {p: (p in perms) for p in _ALL_PERMS}
        return ProjectRole.objects.create(
            project=project,
            name=name,
            description=desc,
            is_system=True,
            is_admin_role=is_admin,
            max_move_column=max_col,
            **kwargs,
        )

    for project in Project.objects.all():
        if ProjectRole.objects.filter(project=project).exists():
            continue

        # Contributor move cap: the review column, else the last non-final column.
        cols = list(
            BoardColumn.objects.filter(board__id_project=project.id_project).order_by("order")
        )
        review_col = next((c for c in cols if c.is_review), None)
        cap_col = review_col or next((c for c in reversed(cols) if not c.is_final), None)

        make(project, "Admin", "Full access to the project.", _ALL_PERMS, is_admin=True)
        make(
            project,
            "Editor",
            "Create and manage tasks, sprints, milestones and tags.",
            [
                "can_create_tasks", "can_edit_tasks", "can_delete_tasks", "can_move_tasks",
                "can_manage_sprints", "can_manage_milestones", "can_manage_tags",
                "can_comment", "can_trigger_ai",
            ],
        )
        make(
            project,
            "Contributor",
            "Work on tasks (move up to the review column) and comment.",
            ["can_create_tasks", "can_edit_tasks", "can_move_tasks", "can_comment", "can_trigger_ai"],
            max_col=cap_col,
        )
        make(project, "Viewer", "Read-only access to the project.", [])

        roles_by_name = {r.name: r for r in ProjectRole.objects.filter(project=project)}
        for member in ProjectMember.objects.filter(project=project).select_related("role"):
            target = "Viewer"
            legacy = getattr(member.role, "name", None)
            if legacy:
                target = _LEGACY_MAP.get(legacy.strip().lower(), "Viewer")
            if project.created_by_id and member.user_id == project.created_by_id:
                target = "Admin"
            member.project_role = roles_by_name.get(target)
            member.save(update_fields=["project_role"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0045_task_parent"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="ProjectRole",
                    fields=[
                        ("id_project_role", models.BigAutoField(primary_key=True, serialize=False)),
                        ("name", models.CharField(max_length=50)),
                        ("description", models.TextField(blank=True, null=True)),
                        ("is_admin_role", models.BooleanField(default=False)),
                        ("is_system", models.BooleanField(default=False)),
                        ("can_create_tasks", models.BooleanField(default=False)),
                        ("can_edit_tasks", models.BooleanField(default=False)),
                        ("can_delete_tasks", models.BooleanField(default=False)),
                        ("can_move_tasks", models.BooleanField(default=False)),
                        ("can_manage_sprints", models.BooleanField(default=False)),
                        ("can_manage_board", models.BooleanField(default=False)),
                        ("can_manage_milestones", models.BooleanField(default=False)),
                        ("can_manage_tags", models.BooleanField(default=False)),
                        ("can_comment", models.BooleanField(default=False)),
                        ("can_manage_members", models.BooleanField(default=False)),
                        ("can_manage_project", models.BooleanField(default=False)),
                        ("can_trigger_ai", models.BooleanField(default=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("project", models.ForeignKey(db_column="id_project", on_delete=django.db.models.deletion.CASCADE, related_name="project_roles", to="core.project")),
                        ("max_move_column", models.ForeignKey(blank=True, db_column="id_max_move_column", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="role_move_caps", to="core.boardcolumn")),
                    ],
                    options={
                        "db_table": "project_custom_role",
                        "unique_together": {("project", "name")},
                    },
                ),
                migrations.AddField(
                    model_name="projectmember",
                    name="project_role",
                    field=models.ForeignKey(blank=True, db_column="id_project_role", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="members", to="core.projectrole"),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS project_custom_role (
                            id_project_role     bigserial PRIMARY KEY,
                            id_project          bigint NOT NULL REFERENCES project(id_project) ON DELETE CASCADE,
                            name                varchar(50) NOT NULL,
                            description         text NULL,
                            is_admin_role       boolean NOT NULL DEFAULT false,
                            is_system           boolean NOT NULL DEFAULT false,
                            can_create_tasks    boolean NOT NULL DEFAULT false,
                            can_edit_tasks      boolean NOT NULL DEFAULT false,
                            can_delete_tasks    boolean NOT NULL DEFAULT false,
                            can_move_tasks      boolean NOT NULL DEFAULT false,
                            can_manage_sprints  boolean NOT NULL DEFAULT false,
                            can_manage_board    boolean NOT NULL DEFAULT false,
                            can_manage_milestones boolean NOT NULL DEFAULT false,
                            can_manage_tags     boolean NOT NULL DEFAULT false,
                            can_comment         boolean NOT NULL DEFAULT false,
                            can_manage_members  boolean NOT NULL DEFAULT false,
                            can_manage_project  boolean NOT NULL DEFAULT false,
                            can_trigger_ai      boolean NOT NULL DEFAULT false,
                            id_max_move_column  bigint NULL REFERENCES board_column(id_column) ON DELETE SET NULL,
                            created_at          timestamptz NOT NULL DEFAULT now(),
                            CONSTRAINT uniq_project_custom_role_name UNIQUE (id_project, name)
                        );
                        CREATE INDEX IF NOT EXISTS project_custom_role_project_idx ON project_custom_role (id_project);
                        ALTER TABLE project_member
                            ADD COLUMN IF NOT EXISTS id_project_role bigint NULL
                            REFERENCES project_custom_role (id_project_role) ON DELETE SET NULL;
                    """,
                    reverse_sql="""
                        ALTER TABLE project_member DROP COLUMN IF EXISTS id_project_role;
                        DROP TABLE IF EXISTS project_custom_role;
                    """,
                ),
            ],
        ),
        migrations.RunPython(seed_project_roles, migrations.RunPython.noop),
    ]
