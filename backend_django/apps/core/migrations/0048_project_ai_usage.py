import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0047_user_token_version"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="ProjectAiUsage",
                    fields=[
                        ("id_usage", models.BigAutoField(primary_key=True, serialize=False)),
                        ("period", models.CharField(max_length=7)),
                        ("reviews_used", models.IntegerField(default=0)),
                        ("chat_used", models.IntegerField(default=0)),
                        ("aifix_used", models.IntegerField(default=0)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("project", models.ForeignKey(db_column="id_project", on_delete=django.db.models.deletion.CASCADE, related_name="ai_usage", to="core.project")),
                    ],
                    options={"db_table": "project_ai_usage", "unique_together": {("project", "period")}},
                ),
                migrations.CreateModel(
                    name="PendingAiReview",
                    fields=[
                        ("id_pending", models.BigAutoField(primary_key=True, serialize=False)),
                        ("trigger", models.CharField(default="push", max_length=20)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("project", models.ForeignKey(db_column="id_project", on_delete=django.db.models.deletion.CASCADE, related_name="pending_ai_reviews", to="core.project")),
                        ("push", models.ForeignKey(db_column="id_push", on_delete=django.db.models.deletion.CASCADE, related_name="pending_reviews", to="core.githubpushevent")),
                    ],
                    options={"db_table": "pending_ai_review", "ordering": ["created_at"]},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS project_ai_usage (
                            id_usage BIGSERIAL PRIMARY KEY,
                            id_project BIGINT NOT NULL REFERENCES project(id_project) ON DELETE CASCADE,
                            period VARCHAR(7) NOT NULL,
                            reviews_used INTEGER NOT NULL DEFAULT 0,
                            chat_used INTEGER NOT NULL DEFAULT 0,
                            aifix_used INTEGER NOT NULL DEFAULT 0,
                            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                            CONSTRAINT uq_project_ai_usage_project_period UNIQUE (id_project, period)
                        );
                        CREATE TABLE IF NOT EXISTS pending_ai_review (
                            id_pending BIGSERIAL PRIMARY KEY,
                            id_project BIGINT NOT NULL REFERENCES project(id_project) ON DELETE CASCADE,
                            id_push BIGINT NOT NULL REFERENCES github_push_event(id_push) ON DELETE CASCADE,
                            trigger VARCHAR(20) NOT NULL DEFAULT 'push',
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
                        );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS pending_ai_review; DROP TABLE IF EXISTS project_ai_usage;",
                ),
            ],
        ),
    ]
