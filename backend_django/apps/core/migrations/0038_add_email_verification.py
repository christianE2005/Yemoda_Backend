import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_remove_system_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccount",
            name="is_email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="EmailVerificationToken",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("token", models.CharField(db_index=True, max_length=100, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("used", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        db_column="id_user",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="verification_tokens",
                        to="core.useraccount",
                    ),
                ),
            ],
            options={"db_table": "email_verification_token"},
        ),
    ]
