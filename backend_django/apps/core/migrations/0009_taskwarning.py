from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_githubpushevent"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS task_warning (
                            id_warning BIGSERIAL PRIMARY KEY,
                            id_task BIGINT NOT NULL REFERENCES task(id_task) ON DELETE CASCADE,
                            message TEXT NOT NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'active',
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            resolved_at TIMESTAMP WITH TIME ZONE,
                            id_push_resolved BIGINT REFERENCES github_push_event(id_push) ON DELETE SET NULL
                        );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS task_warning;",
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name="TaskWarning",
                    fields=[
                        ("id_warning", models.BigAutoField(primary_key=True, serialize=False)),
                        (
                            "task",
                            models.ForeignKey(
                                db_column="id_task",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="warnings",
                                to="core.task",
                            ),
                        ),
                        ("message", models.TextField()),
                        (
                            "status",
                            models.CharField(
                                choices=[("active", "Active"), ("resolved", "Resolved")],
                                default="active",
                                max_length=20,
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("resolved_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "resolved_in_push",
                            models.ForeignKey(
                                blank=True,
                                db_column="id_push_resolved",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="resolved_warnings",
                                to="core.githubpushevent",
                            ),
                        ),
                    ],
                    options={"db_table": "task_warning", "ordering": ["-created_at"]},
                ),
            ],
        ),
    ]
