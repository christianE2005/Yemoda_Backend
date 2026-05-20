from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0025_task_scrum_number"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="task",
                    name="story_points",
                    field=models.PositiveSmallIntegerField(null=True, blank=True),
                ),
                migrations.AddConstraint(
                    model_name="task",
                    constraint=models.UniqueConstraint(
                        fields=["project", "scrum_number"],
                        condition=models.Q(scrum_number__isnull=False),
                        name="unique_task_scrum_number_per_project",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE task
                        ADD COLUMN IF NOT EXISTS story_points smallint
                        CONSTRAINT task_story_points_positive CHECK (story_points > 0);

                        CREATE UNIQUE INDEX IF NOT EXISTS task_project_scrum_number_key
                        ON task (id_project, scrum_number)
                        WHERE scrum_number IS NOT NULL;
                    """,
                    reverse_sql="""
                        ALTER TABLE task DROP COLUMN IF EXISTS story_points;
                        DROP INDEX IF EXISTS task_project_scrum_number_key;
                    """,
                ),
            ],
        ),
    ]
