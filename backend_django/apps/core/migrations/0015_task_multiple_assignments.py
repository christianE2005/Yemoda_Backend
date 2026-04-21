# Migration to support multiple task assignments

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_alter_project_status'),
    ]

    operations = [
        # 1. Create the new TaskAssignment table
        migrations.CreateModel(
            name='TaskAssignment',
            fields=[
                ('id_assignment', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assigned_to', models.ForeignKey(
                    db_column='id_user',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='task_assignments',
                    to='core.useraccount',
                )),
                ('task', models.ForeignKey(
                    db_column='id_task',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='assignments',
                    to='core.task',
                )),
            ],
            options={
                'db_table': 'task_assignment',
            },
        ),
        
        # 2. Migrate existing assigned_to data to TaskAssignment
        migrations.RunSQL(
            sql="""
                INSERT INTO task_assignment (id_task, id_user, created_at)
                SELECT id_task, assigned_to, COALESCE(created_at, NOW())
                FROM task
                WHERE assigned_to IS NOT NULL
                ON CONFLICT DO NOTHING;
            """,
            reverse_sql="DELETE FROM task_assignment;",
        ),
        
        # 3. Add unique constraint to prevent duplicate assignments
        migrations.AddConstraint(
            model_name='taskassignment',
            constraint=models.UniqueConstraint(
                fields=('task', 'assigned_to'),
                name='unique_task_assignment',
            ),
        ),
        
        # 4. Remove the old assigned_to column from task table
        migrations.RemoveField(
            model_name='task',
            name='assigned_to',
        ),
    ]
