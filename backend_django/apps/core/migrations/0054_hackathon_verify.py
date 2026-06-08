from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0053_alter_hackathonsubmission_status"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="hackathon",
                    name="verify_findings",
                    field=models.BooleanField(default=False),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE hackathon "
                        "ADD COLUMN IF NOT EXISTS verify_findings BOOLEAN NOT NULL DEFAULT false;"
                    ),
                    reverse_sql="ALTER TABLE hackathon DROP COLUMN IF EXISTS verify_findings;",
                ),
            ],
        ),
    ]
