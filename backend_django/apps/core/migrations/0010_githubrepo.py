from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_taskwarning"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS github_repo (
                            id_repo BIGSERIAL PRIMARY KEY,
                            id_user BIGINT NOT NULL REFERENCES user_account(id_user) ON DELETE CASCADE,
                            id_project BIGINT REFERENCES project(id_project) ON DELETE SET NULL,
                            github_repo_id BIGINT UNIQUE NOT NULL,
                            full_name VARCHAR(255) NOT NULL,
                            name VARCHAR(150) NOT NULL,
                            owner VARCHAR(150) NOT NULL,
                            private BOOLEAN NOT NULL DEFAULT TRUE,
                            html_url VARCHAR(500) NOT NULL,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS github_repo;",
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name="GithubRepo",
                    fields=[
                        ("id_repo", models.BigAutoField(primary_key=True, serialize=False)),
                        (
                            "user",
                            models.ForeignKey(
                                db_column="id_user",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="github_repos",
                                to="core.useraccount",
                            ),
                        ),
                        (
                            "project",
                            models.ForeignKey(
                                blank=True,
                                db_column="id_project",
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="github_repos",
                                to="core.project",
                            ),
                        ),
                        ("github_repo_id", models.BigIntegerField(unique=True)),
                        ("full_name", models.CharField(max_length=255)),
                        ("name", models.CharField(max_length=150)),
                        ("owner", models.CharField(max_length=150)),
                        ("private", models.BooleanField(default=True)),
                        ("html_url", models.CharField(max_length=500)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                    ],
                    options={"db_table": "github_repo", "ordering": ["-created_at"]},
                ),
            ],
        ),
    ]
