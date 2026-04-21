# Generated migration to insert task statuses

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_insert_missing_system_roles'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                INSERT INTO task_status (name, description)
                VALUES
                    ('Backlog', 'Tareas pendientes en el backlog'),
                    ('To Do', 'Tareas listas para comenzar'),
                    ('In Progress', 'Tareas actualmente en desarrollo'),
                    ('Review', 'Tareas esperando revisión'),
                    ('Done', 'Tareas completadas')
                ON CONFLICT (name) DO NOTHING;
            """,
            reverse_sql="DELETE FROM task_status WHERE name IN ('Backlog', 'To Do', 'In Progress', 'Review', 'Done');",
        ),
    ]
