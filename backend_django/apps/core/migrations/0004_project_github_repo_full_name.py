from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_githubappinstallation"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="github_repo_full_name",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
    ]
