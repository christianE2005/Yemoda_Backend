from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0039_useraccount_subscription_plan_stripepayment_plan"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccount",
            name="stripe_subscription_id",
            field=models.CharField(
                blank=True,
                help_text="Stripe subscription ID (sub_xxx). Required to cancel/modify subscription.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="useraccount",
            name="stripe_customer_id",
            field=models.CharField(
                blank=True,
                help_text="Stripe customer ID (cus_xxx).",
                max_length=255,
                null=True,
            ),
        ),
    ]
