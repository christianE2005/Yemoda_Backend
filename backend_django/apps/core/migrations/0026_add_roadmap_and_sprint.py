import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_add_scrum_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="start_date",
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="project",
            name="roadmap_type",
            field=models.CharField(max_length=20, choices=[('sprints', 'Sprints'), ('ci_cd', 'CI/CD')], default='sprints'),
        ),
        migrations.AddField(
            model_name="project",
            name="sprint_length_days",
            field=models.IntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="project",
            name="sprint_count",
            field=models.IntegerField(null=True, blank=True),
        ),
        migrations.CreateModel(
            name="Sprint",
            fields=[
                ('id_sprint', models.BigAutoField(primary_key=True, serialize=False)),
                ('number', models.IntegerField()),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('project', models.ForeignKey(db_column='id_project', on_delete=django.db.models.deletion.CASCADE, related_name='sprints', to='core.project')),
            ],
            options={
                'db_table': 'sprint',
                'unique_together': {('project', 'number')},
                'ordering': ['project_id', 'number'],
            },
        ),
        migrations.AddField(
            model_name='task',
            name='sprint',
            field=models.ForeignKey(null=True, blank=True, to='core.sprint', db_column='id_sprint', related_name='tasks', on_delete=django.db.models.deletion.SET_NULL),
        ),
    ]
