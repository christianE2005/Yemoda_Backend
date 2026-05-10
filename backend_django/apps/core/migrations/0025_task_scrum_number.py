from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0024_sprint_milestone_tag_boardcolumn_task_restructure"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="task",
                    name="scrum_number",
                    field=models.PositiveIntegerField(null=True, blank=True),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE task
                        ADD COLUMN IF NOT EXISTS scrum_number integer
                        CONSTRAINT task_scrum_number_positive CHECK (scrum_number > 0);
                    """,
                    reverse_sql="""
                        ALTER TABLE task DROP COLUMN IF EXISTS scrum_number;
                    """,
                ),
            ],
        ),
    ]
