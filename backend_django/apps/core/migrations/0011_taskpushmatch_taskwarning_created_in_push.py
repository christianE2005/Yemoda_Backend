import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_githubrepo"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE task_warning
                        ADD COLUMN IF NOT EXISTS id_push_created BIGINT
                        REFERENCES github_push_event(id_push) ON DELETE SET NULL;

                        CREATE TABLE IF NOT EXISTS task_push_match (
                            id_match        BIGSERIAL PRIMARY KEY,
                            id_task         BIGINT NOT NULL REFERENCES task(id_task) ON DELETE CASCADE,
                            id_push         BIGINT NOT NULL REFERENCES github_push_event(id_push) ON DELETE CASCADE,
                            coverage        VARCHAR(10) NOT NULL DEFAULT 'partial',
                            reason          TEXT,
                            code_snippet    TEXT,
                            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (id_task, id_push)
                        );
                    """,
                    reverse_sql="""
                        ALTER TABLE task_warning DROP COLUMN IF EXISTS id_push_created;
                        DROP TABLE IF EXISTS task_push_match;
                    """,
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name="taskwarning",
                    name="created_in_push",
                    field=models.ForeignKey(
                        blank=True,
                        db_column="id_push_created",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_warnings",
                        to="core.githubpushevent",
                    ),
                ),
                migrations.CreateModel(
                    name="TaskPushMatch",
                    fields=[
                        ("id_match", models.BigAutoField(primary_key=True, serialize=False)),
                        ("coverage", models.CharField(
                            choices=[("full", "Full"), ("partial", "Partial")],
                            default="partial",
                            max_length=10,
                        )),
                        ("reason", models.TextField(blank=True, null=True)),
                        ("code_snippet", models.TextField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("push", models.ForeignKey(
                            db_column="id_push",
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="task_matches",
                            to="core.githubpushevent",
                        )),
                        ("task", models.ForeignKey(
                            db_column="id_task",
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="push_matches",
                            to="core.task",
                        )),
                    ],
                    options={"db_table": "task_push_match", "ordering": ["-created_at"]},
                ),
                migrations.AlterUniqueTogether(
                    name="taskpushmatch",
                    unique_together={("task", "push")},
                ),
            ],
        ),
    ]
