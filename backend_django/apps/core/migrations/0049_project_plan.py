from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0048_project_ai_usage"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="project",
                    name="plan",
                    field=models.CharField(
                        choices=[("free", "Free"), ("pro", "Pro")],
                        default="free",
                        max_length=10,
                    ),
                ),
                migrations.AddField(
                    model_name="project",
                    name="stripe_subscription_id",
                    field=models.CharField(blank=True, max_length=255, null=True),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE project ADD COLUMN IF NOT EXISTS plan VARCHAR(10) NOT NULL DEFAULT 'free';"
                        "ALTER TABLE project ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255);"
                    ),
                    reverse_sql=(
                        "ALTER TABLE project DROP COLUMN IF EXISTS stripe_subscription_id;"
                        "ALTER TABLE project DROP COLUMN IF EXISTS plan;"
                    ),
                ),
            ],
        ),
    ]
