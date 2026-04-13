from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_githubappinstallation"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE project ADD COLUMN IF NOT EXISTS github_repo_full_name VARCHAR(255);",
            reverse_sql="ALTER TABLE project DROP COLUMN IF EXISTS github_repo_full_name;",
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="project",
                    name="github_repo_full_name",
                    field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
                ),
            ],
            database_operations=[],
        ),
    ]
