from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0034_taskwarning_severity"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="project",
                    name="review_branches",
                    field=models.CharField(
                        blank=True,
                        default="",
                        help_text="Comma-separated branch names to trigger AI review (e.g. main,develop). Leave empty to analyze all branches.",
                        max_length=255,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE project ADD COLUMN IF NOT EXISTS review_branches varchar(255) NOT NULL DEFAULT '';",
                    reverse_sql="ALTER TABLE project DROP COLUMN IF EXISTS review_branches;",
                ),
            ],
        ),
    ]
