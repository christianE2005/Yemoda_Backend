import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds the missing migration for the (already live) TaskAIReviewResult model.

    The model is wired to a REST endpoint (`task-ai-review-results`) but never had a
    migration, so it showed up perpetually as an unapplied change and the table would be
    absent on a fresh database. Idempotent SQL (CREATE TABLE IF NOT EXISTS) makes this safe
    whether or not the table was already created out-of-band in an existing environment.
    """

    dependencies = [
        ("core", "0049_project_plan"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="TaskAIReviewResult",
                    fields=[
                        ("id_review_result", models.BigAutoField(primary_key=True, serialize=False)),
                        ("provider", models.CharField(choices=[("copilot", "Copilot"), ("yemoda", "Yemoda")], max_length=20)),
                        ("model_name", models.CharField(blank=True, max_length=100, null=True)),
                        ("result_text", models.TextField()),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("task", models.ForeignKey(db_column="id_task", on_delete=django.db.models.deletion.CASCADE, related_name="ai_review_results", to="core.task")),
                        ("user", models.ForeignKey(blank=True, db_column="id_user", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ai_review_results", to="core.useraccount")),
                    ],
                    options={"db_table": "task_ai_review_result", "ordering": ["-created_at"]},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS task_ai_review_result (
                            id_review_result BIGSERIAL PRIMARY KEY,
                            id_task BIGINT NOT NULL REFERENCES task(id_task) ON DELETE CASCADE,
                            id_user BIGINT REFERENCES user_account(id_user) ON DELETE SET NULL,
                            provider VARCHAR(20) NOT NULL,
                            model_name VARCHAR(100),
                            result_text TEXT NOT NULL,
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
                        );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS task_ai_review_result;",
                ),
            ],
        ),
    ]
