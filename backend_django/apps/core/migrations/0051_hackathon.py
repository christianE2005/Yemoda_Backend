import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0050_taskaireviewresult"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Hackathon",
                    fields=[
                        ("id_hackathon", models.BigAutoField(primary_key=True, serialize=False)),
                        ("name", models.CharField(max_length=150)),
                        ("rubric", models.JSONField(default=dict)),
                        ("status", models.CharField(choices=[("open", "Open"), ("closed", "Closed")], default="open", max_length=20)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("created_by", models.ForeignKey(blank=True, db_column="id_user", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="hackathons_created", to="core.useraccount")),
                    ],
                    options={"db_table": "hackathon", "ordering": ["-created_at"]},
                ),
                migrations.CreateModel(
                    name="HackathonSubmission",
                    fields=[
                        ("id_submission", models.BigAutoField(primary_key=True, serialize=False)),
                        ("team_name", models.CharField(max_length=150)),
                        ("repo_url", models.CharField(max_length=500)),
                        ("ref", models.CharField(default="main", max_length=255)),
                        ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")], default="pending", max_length=20)),
                        ("score", models.IntegerField(blank=True, null=True)),
                        ("score_breakdown", models.JSONField(blank=True, null=True)),
                        ("findings", models.JSONField(blank=True, null=True)),
                        ("summary", models.TextField(blank=True, null=True)),
                        ("error", models.TextField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("analyzed_at", models.DateTimeField(blank=True, null=True)),
                        ("hackathon", models.ForeignKey(db_column="id_hackathon", on_delete=django.db.models.deletion.CASCADE, related_name="submissions", to="core.hackathon")),
                    ],
                    options={"db_table": "hackathon_submission", "ordering": ["-created_at"]},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS hackathon (
                            id_hackathon BIGSERIAL PRIMARY KEY,
                            name VARCHAR(150) NOT NULL,
                            id_user BIGINT NULL REFERENCES user_account(id_user) ON DELETE SET NULL,
                            rubric JSONB NOT NULL DEFAULT '{}'::jsonb,
                            status VARCHAR(20) NOT NULL DEFAULT 'open',
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
                        );
                        CREATE TABLE IF NOT EXISTS hackathon_submission (
                            id_submission BIGSERIAL PRIMARY KEY,
                            id_hackathon BIGINT NOT NULL REFERENCES hackathon(id_hackathon) ON DELETE CASCADE,
                            team_name VARCHAR(150) NOT NULL,
                            repo_url VARCHAR(500) NOT NULL,
                            ref VARCHAR(255) NOT NULL DEFAULT 'main',
                            status VARCHAR(20) NOT NULL DEFAULT 'pending',
                            score INTEGER NULL,
                            score_breakdown JSONB NULL,
                            findings JSONB NULL,
                            summary TEXT NULL,
                            error TEXT NULL,
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                            analyzed_at TIMESTAMP WITH TIME ZONE NULL
                        );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS hackathon_submission; DROP TABLE IF EXISTS hackathon;",
                ),
            ],
        ),
    ]
