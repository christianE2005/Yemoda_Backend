import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Restructures the task system:
    - Adds Sprint, Milestone, Tag, BoardColumn models
    - Removes Task.board (FK to Board) and Task.status (FK to TaskStatus)
    - Adds Task.project (FK to Project, required)
    - Adds Task.sprint, Task.board_column, Task.milestone (nullable FKs)
    - Adds Task.tags (M2M via task_tag table)
    """

    dependencies = [
        ("core", "0023_merge_0021_activitylog_project_0022_merge"),
    ]

    operations = [
        # ── New standalone models ──────────────────────────────────────────

        migrations.CreateModel(
            name="Sprint",
            fields=[
                ("id_sprint", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "project",
                    models.ForeignKey(
                        db_column="id_project",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sprints",
                        to="core.project",
                    ),
                ),
                ("name", models.CharField(max_length=150)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("planned", "Planned"),
                            ("active", "Active"),
                            ("closed", "Closed"),
                        ],
                        default="planned",
                        max_length=20,
                    ),
                ),
            ],
            options={"db_table": "sprint"},
        ),
        migrations.CreateModel(
            name="Milestone",
            fields=[
                ("id_milestone", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "project",
                    models.ForeignKey(
                        db_column="id_project",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="milestones",
                        to="core.project",
                    ),
                ),
                ("name", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True, null=True)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("is_completed", models.BooleanField(default=False)),
            ],
            options={"db_table": "milestone"},
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id_tag", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "project",
                    models.ForeignKey(
                        db_column="id_project",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tags",
                        to="core.project",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("color", models.CharField(blank=True, max_length=20, null=True)),
            ],
            options={
                "db_table": "tag",
                "unique_together": {("project", "name")},
            },
        ),
        migrations.CreateModel(
            name="BoardColumn",
            fields=[
                ("id_column", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "board",
                    models.ForeignKey(
                        db_column="id_board",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="columns",
                        to="core.board",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("order", models.PositiveIntegerField(default=0)),
                ("is_final", models.BooleanField(default=False)),
            ],
            options={
                "db_table": "board_column",
                "ordering": ["order"],
            },
        ),

        # ── Modify Task: remove old FK columns ───────────────────────────

        migrations.RemoveField(
            model_name="task",
            name="board",
        ),
        migrations.RemoveField(
            model_name="task",
            name="status",
        ),

        # ── Modify Task: add new FK columns ──────────────────────────────

        migrations.AddField(
            model_name="task",
            name="project",
            field=models.ForeignKey(
                db_column="id_project",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tasks",
                to="core.project",
                null=True,   # temporarily nullable so existing rows don't break
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="sprint",
            field=models.ForeignKey(
                blank=True,
                db_column="id_sprint",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tasks",
                to="core.sprint",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="board_column",
            field=models.ForeignKey(
                blank=True,
                db_column="id_column",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tasks",
                to="core.boardcolumn",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="milestone",
            field=models.ForeignKey(
                blank=True,
                db_column="id_milestone",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tasks",
                to="core.milestone",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="tags",
            field=models.ManyToManyField(
                blank=True,
                db_table="task_tag",
                related_name="tasks",
                to="core.tag",
            ),
        ),

        # Make task.project non-nullable after data migration step
        migrations.AlterField(
            model_name="task",
            name="project",
            field=models.ForeignKey(
                db_column="id_project",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tasks",
                to="core.project",
            ),
        ),
    ]
