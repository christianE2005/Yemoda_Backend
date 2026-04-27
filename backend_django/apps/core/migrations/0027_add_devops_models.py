import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_add_roadmap_and_sprint"),
    ]

    operations = [
        migrations.CreateModel(
            name="DevOpsConnection",
            fields=[
                ("id_connection", models.BigAutoField(primary_key=True, serialize=False)),
                ("organization", models.CharField(max_length=255, null=True, blank=True)),
                ("access_token", models.CharField(max_length=255)),
                ("refresh_token", models.CharField(max_length=255, null=True, blank=True)),
                ("token_expires_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="devops_connection",
                        to="core.useraccount",
                        db_column="id_user",
                    ),
                ),
            ],
            options={
                "db_table": "devops_connection",
            },
        ),
        migrations.CreateModel(
            name="DevOpsSubscription",
            fields=[
                ("id_subscription", models.BigAutoField(primary_key=True, serialize=False)),
                ("project_id", models.CharField(max_length=100)),
                ("subscription_id", models.CharField(max_length=100)),
                ("event_type", models.CharField(max_length=100, null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscriptions",
                        to="core.devopsconnection",
                        db_column="id_connection",
                    ),
                ),
            ],
            options={
                "db_table": "devops_subscription",
            },
        ),
        migrations.AddConstraint(
            model_name="devopssubscription",
            constraint=models.UniqueConstraint(fields=("connection", "subscription_id"), name="unique_connection_subscription"),
        ),
        migrations.CreateModel(
            name="DevOpsWebhookEvent",
            fields=[
                ("id_event", models.BigAutoField(primary_key=True, serialize=False)),
                ("event_type", models.CharField(max_length=100, null=True, blank=True)),
                ("payload", models.JSONField(default=dict)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="webhook_events",
                        to="core.devopsconnection",
                        db_column="id_connection",
                        null=True,
                        blank=True,
                    ),
                ),
            ],
            options={
                "db_table": "devops_webhook_event",
                "ordering": ["-received_at"],
            },
        ),
    ]
