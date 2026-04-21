# Generated migration to insert project roles

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_remove_taskassignment_unique_task_assignment_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                INSERT INTO role (name, description)
                VALUES
                    ('Project Manager', 'Responsible for planning, executing, and closing projects'),
                    ('Product Owner', 'Defines product vision and manages the product backlog'),
                    ('Scrum Master', 'Facilitates Scrum processes and removes team impediments'),
                    ('Developer', 'Designs, builds, and delivers product increments')
                ON CONFLICT (name) DO NOTHING;
            """,
            reverse_sql="DELETE FROM role WHERE name IN ('Project Manager', 'Product Owner', 'Scrum Master', 'Developer');",
        ),
    ]
