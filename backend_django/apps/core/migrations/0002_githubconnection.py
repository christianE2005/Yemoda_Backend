from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GithubConnection",
            fields=[
                ("id_connection", models.BigAutoField(primary_key=True, serialize=False)),
                ("github_user_id", models.BigIntegerField(unique=True)),
                ("github_login", models.CharField(max_length=150)),
                ("access_token", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        db_column="id_user",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="github_connection",
                        to="core.useraccount",
                    ),
                ),
            ],
            options={
                "db_table": "github_connection",
            },
        ),
    ]
