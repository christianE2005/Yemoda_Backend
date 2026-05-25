from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0038_add_email_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccount",
            name="subscription_plan",
            field=models.CharField(
                blank=True,
                choices=[("monthly", "Monthly"), ("annual", "Annual")],
                help_text="Active subscription tier: 'monthly' or 'annual'. Null means free tier.",
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="stripepayment",
            name="plan",
            field=models.CharField(
                blank=True,
                help_text="'monthly' or 'annual'",
                max_length=20,
                null=True,
            ),
        ),
    ]
