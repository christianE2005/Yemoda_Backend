# Generated migration to insert missing system roles

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_alter_systemrole_name'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                INSERT INTO system_role (name, description)
                VALUES
                    ('Stakeholder', 'Stakeholder con acceso limitado'),
                    ('Project Manager', 'Gestor de proyecto con permisos especiales')
                ON CONFLICT (name) DO NOTHING;
            """,
            reverse_sql="DELETE FROM system_role WHERE name IN ('Stakeholder', 'Project Manager');",
        ),
    ]
