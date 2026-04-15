from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_githubconnection_token_refresh"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE user_account ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;",
            reverse_sql="ALTER TABLE user_account DROP COLUMN IF EXISTS is_admin;",
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="useraccount",
                    name="is_admin",
                    field=models.BooleanField(default=False),
                ),
            ],
            database_operations=[],
        ),
    ]
