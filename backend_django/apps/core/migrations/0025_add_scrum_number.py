from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_add_similarity_feedback_to_taskpushmatch"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="scrum_number",
            field=models.IntegerField(null=True, blank=True),
        ),
    ]
