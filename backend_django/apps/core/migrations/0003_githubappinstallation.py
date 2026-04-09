from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_githubconnection"),
    ]

    operations = [
        migrations.CreateModel(
            name="GithubAppInstallation",
            fields=[
                ("id_installation", models.BigAutoField(primary_key=True, serialize=False)),
                ("installation_id", models.BigIntegerField(unique=True)),
                ("account_login", models.CharField(max_length=150)),
                ("account_type", models.CharField(blank=True, max_length=50, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        db_column="id_user",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="github_app_installations",
                        to="core.useraccount",
                    ),
                ),
            ],
            options={
                "db_table": "github_app_installation",
            },
        ),
    ]
