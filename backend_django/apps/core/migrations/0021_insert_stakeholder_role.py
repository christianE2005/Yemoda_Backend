from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_merge_0017_insert_project_roles_0018_taskpushmatch_taskwarning_created_in_push"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                INSERT INTO role (name, description)
                VALUES ('Stakeholder', 'Observador del proyecto con acceso de solo lectura')
                ON CONFLICT (name) DO NOTHING;
            """,
            reverse_sql="DELETE FROM role WHERE name = 'Stakeholder';",
        ),
        migrations.RunSQL(
            sql="""
                INSERT INTO task_priority (name, level)
                VALUES
                    ('Crítica',  1),
                    ('Alta',     2),
                    ('Media',    3),
                    ('Baja',     4)
                ON CONFLICT (name) DO NOTHING;
            """,
            reverse_sql="DELETE FROM task_priority WHERE name IN ('Crítica', 'Alta', 'Media', 'Baja');",
        ),
    ]
