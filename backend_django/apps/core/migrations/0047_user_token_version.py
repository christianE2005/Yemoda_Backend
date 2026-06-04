from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0046_project_roles"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="useraccount",
                    name="token_version",
                    field=models.IntegerField(default=0),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE user_account ADD COLUMN IF NOT EXISTS token_version integer NOT NULL DEFAULT 0;",
                    reverse_sql="ALTER TABLE user_account DROP COLUMN IF EXISTS token_version;",
                ),
            ],
        ),
    ]
