from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_systemrole_useraccount_system_role"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS github_push_event (
                            id_push BIGSERIAL PRIMARY KEY,
                            id_project BIGINT REFERENCES project(id_project) ON DELETE CASCADE,
                            repo_full_name VARCHAR(255) NOT NULL,
                            ref VARCHAR(255) NOT NULL,
                            pusher VARCHAR(150),
                            commits JSONB NOT NULL DEFAULT '[]',
                            received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS github_push_event;",
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name="GithubPushEvent",
                    fields=[
                        ("id_push", models.BigAutoField(primary_key=True, serialize=False)),
                        (
                            "project",
                            models.ForeignKey(
                                blank=True,
                                db_column="id_project",
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="push_events",
                                to="core.project",
                            ),
                        ),
                        ("repo_full_name", models.CharField(max_length=255)),
                        ("ref", models.CharField(max_length=255)),
                        ("pusher", models.CharField(blank=True, max_length=150, null=True)),
                        ("commits", models.JSONField(default=list)),
                        ("received_at", models.DateTimeField(auto_now_add=True)),
                    ],
                    options={"db_table": "github_push_event", "ordering": ["-received_at"]},
                ),
            ],
        ),
    ]
