from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_task_story_points_scrum_unique"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="boardcolumn",
                    name="is_review",
                    field=models.BooleanField(default=False),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE board_column ADD COLUMN IF NOT EXISTS is_review boolean NOT NULL DEFAULT false;",
                    reverse_sql="ALTER TABLE board_column DROP COLUMN IF EXISTS is_review;",
                ),
            ],
        ),
    ]
