from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_merge_0021_activitylog_project_0022_merge"),
    ]

    operations = [
        migrations.AddField(
            model_name="taskpushmatch",
            name="similarity",
            field=models.FloatField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="taskpushmatch",
            name="model_name",
            field=models.CharField(max_length=200, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="taskpushmatch",
            name="feedback",
            field=models.CharField(max_length=20, default="unknown", choices=[("unknown", "Unknown"), ("correct", "Correct"), ("incorrect", "Incorrect")]),
        ),
    ]
