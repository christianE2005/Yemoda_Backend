import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0044_translate_db_data_to_english"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="task",
                    name="parent",
                    field=models.ForeignKey(
                        null=True,
                        blank=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        db_column="id_parent_task",
                        related_name="subtasks",
                        to="core.task",
                        help_text=(
                            "Parent task. A task with a parent is a subtask. Supports arbitrary "
                            "depth (epic -> story -> subtask). Deleting a parent cascades to its subtasks."
                        ),
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE task
                        ADD COLUMN IF NOT EXISTS id_parent_task bigint NULL
                        REFERENCES task (id_task) ON DELETE CASCADE;
                        CREATE INDEX IF NOT EXISTS task_id_parent_task_idx
                        ON task (id_parent_task);
                    """,
                    reverse_sql="""
                        DROP INDEX IF EXISTS task_id_parent_task_idx;
                        ALTER TABLE task DROP COLUMN IF EXISTS id_parent_task;
                    """,
                ),
            ],
        ),
    ]
