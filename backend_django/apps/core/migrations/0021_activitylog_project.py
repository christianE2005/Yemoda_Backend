from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_project_repo"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE activity_log ADD COLUMN IF NOT EXISTS id_project BIGINT REFERENCES project(id_project) ON DELETE SET NULL;",
                    reverse_sql="ALTER TABLE activity_log DROP COLUMN IF EXISTS id_project;",
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name="activitylog",
                    name="project",
                    field=models.ForeignKey(
                        blank=True,
                        db_column="id_project",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activity_logs",
                        to="core.project",
                    ),
                )
            ],
        )
    ]
