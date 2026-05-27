# Translates all Spanish-language stored data to English.
# Affects: task_priority names, project status values,
#          system_role descriptions, role descriptions, task_status descriptions.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0043_githubpushevent_diff_text"),
    ]

    operations = [
        # ── task_priority names ────────────────────────────────────────────────
        migrations.RunSQL(
            sql="""
                UPDATE task_priority SET name = 'Critical' WHERE name IN ('Crítica', 'Critica', 'Cr\u00edtica');
                UPDATE task_priority SET name = 'High'     WHERE name IN ('Alta');
                UPDATE task_priority SET name = 'Medium'   WHERE name IN ('Media');
                UPDATE task_priority SET name = 'Low'      WHERE name IN ('Baja');
            """,
            reverse_sql="""
                UPDATE task_priority SET name = 'Crítica' WHERE name = 'Critical';
                UPDATE task_priority SET name = 'Alta'    WHERE name = 'High';
                UPDATE task_priority SET name = 'Media'   WHERE name = 'Medium';
                UPDATE task_priority SET name = 'Baja'    WHERE name = 'Low';
            """,
        ),

        # ── project status values (stored as the choice value in the DB) ───────
        migrations.RunSQL(
            sql="""
                UPDATE project SET status = 'Planning'    WHERE status IN ('Planeaci\u00f3n', 'PlaneaciÃ³n', 'Planeacion');
                UPDATE project SET status = 'In Progress' WHERE status IN ('En Progreso');
                UPDATE project SET status = 'Review'      WHERE status IN ('Revisi\u00f3n', 'RevisiÃ³n', 'Revision');
                UPDATE project SET status = 'Finished'    WHERE status IN ('Finalizado');
                UPDATE project SET status = 'Retired'     WHERE status IN ('Retirado');
                UPDATE project SET status = 'Cancelled'   WHERE status IN ('Cancelado');
            """,
            reverse_sql="""
                UPDATE project SET status = 'Planeación'  WHERE status = 'Planning';
                UPDATE project SET status = 'En Progreso' WHERE status = 'In Progress';
                UPDATE project SET status = 'Revisión'    WHERE status = 'Review';
                UPDATE project SET status = 'Finalizado'  WHERE status = 'Finished';
                UPDATE project SET status = 'Retirado'    WHERE status = 'Retired';
                UPDATE project SET status = 'Cancelado'   WHERE status = 'Cancelled';
            """,
        ),

        # ── Alter Project.status field choices + default to English ────────────
        migrations.AlterField(
            model_name="project",
            name="status",
            field=models.CharField(
                max_length=50,
                choices=[
                    ("Planning",     "Planning"),
                    ("In Progress",  "In Progress"),
                    ("Review",       "Review"),
                    ("Finished",     "Finished"),
                    ("Retired",      "Retired"),
                    ("Cancelled",    "Cancelled"),
                ],
                default="Planning",
            ),
        ),

        # ── project_role descriptions (table renamed from 'role' in 0041) ────────
        migrations.RunSQL(
            sql="""
                UPDATE project_role
                SET description = 'Project observer with read-only access'
                WHERE name = 'Stakeholder'
                  AND description IN (
                    'Observador del proyecto con acceso de solo lectura',
                    'Observador del proyecto con acceso de s\u00f3lo lectura'
                  );
            """,
            reverse_sql="""
                UPDATE project_role
                SET description = 'Observador del proyecto con acceso de solo lectura'
                WHERE name = 'Stakeholder';
            """,
        ),

        # ── task_status descriptions ───────────────────────────────────────────
        migrations.RunSQL(
            sql="""
                UPDATE task_status SET description = 'Pending tasks in the backlog'   WHERE name = 'Backlog';
                UPDATE task_status SET description = 'Tasks ready to start'            WHERE name = 'To Do';
                UPDATE task_status SET description = 'Tasks currently in development'  WHERE name = 'In Progress';
                UPDATE task_status SET description = 'Tasks awaiting review'           WHERE name = 'Review';
                UPDATE task_status SET description = 'Completed tasks'                 WHERE name = 'Done';
            """,
            reverse_sql="""
                UPDATE task_status SET description = 'Tareas pendientes en el backlog'      WHERE name = 'Backlog';
                UPDATE task_status SET description = 'Tareas listas para comenzar'           WHERE name = 'To Do';
                UPDATE task_status SET description = 'Tareas actualmente en desarrollo'      WHERE name = 'In Progress';
                UPDATE task_status SET description = 'Tareas esperando revisión'             WHERE name = 'Review';
                UPDATE task_status SET description = 'Tareas completadas'                    WHERE name = 'Done';
            """,
        ),
    ]
