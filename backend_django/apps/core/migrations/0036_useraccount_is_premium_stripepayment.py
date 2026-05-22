import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0035_project_review_branches"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccount",
            name="is_premium",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="StripePayment",
            fields=[
                ("id_payment", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "user",
                    models.ForeignKey(
                        db_column="id_user",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stripe_payments",
                        to="core.useraccount",
                    ),
                ),
                ("checkout_session_id", models.CharField(max_length=255, unique=True)),
                ("stripe_customer_id", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "amount_total",
                    models.IntegerField(
                        blank=True,
                        help_text="Amount in cents",
                        null=True,
                    ),
                ),
                ("currency", models.CharField(blank=True, max_length=10, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "stripe_payment",
                "ordering": ["-created_at"],
            },
        ),
    ]
