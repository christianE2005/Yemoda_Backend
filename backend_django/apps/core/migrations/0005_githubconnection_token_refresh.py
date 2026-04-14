from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_project_github_repo_full_name"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE github_connection
                    ADD COLUMN IF NOT EXISTS refresh_token VARCHAR(255),
                    ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS refresh_token_expires_at TIMESTAMP WITH TIME ZONE;
            """,
            reverse_sql="""
                ALTER TABLE github_connection
                    DROP COLUMN IF EXISTS refresh_token,
                    DROP COLUMN IF EXISTS token_expires_at,
                    DROP COLUMN IF EXISTS refresh_token_expires_at;
            """,
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="githubconnection",
                    name="refresh_token",
                    field=models.CharField(blank=True, max_length=255, null=True),
                ),
                migrations.AddField(
                    model_name="githubconnection",
                    name="token_expires_at",
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="githubconnection",
                    name="refresh_token_expires_at",
                    field=models.DateTimeField(blank=True, null=True),
                ),
            ],
            database_operations=[],
        ),
    ]
