from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0042_alter_role_table"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE github_push_event ADD COLUMN IF NOT EXISTS diff_text TEXT;",
                    reverse_sql="ALTER TABLE github_push_event DROP COLUMN IF EXISTS diff_text;",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="githubpushevent",
                    name="diff_text",
                    field=models.TextField(blank=True, null=True),
                ),
            ],
        ),
    ]
