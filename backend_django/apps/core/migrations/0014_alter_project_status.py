# Generated migration to add status choices to project model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_insert_task_statuses'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='status',
            field=models.CharField(
                choices=[
                    ('Planeación', 'Planeación'),
                    ('En Progreso', 'En Progreso'),
                    ('Revisión', 'Revisión'),
                    ('Finalizado', 'Finalizado'),
                    ('Retirado', 'Retirado'),
                    ('Cancelado', 'Cancelado'),
                ],
                default='Planeación',
                max_length=50,
            ),
        ),
    ]
