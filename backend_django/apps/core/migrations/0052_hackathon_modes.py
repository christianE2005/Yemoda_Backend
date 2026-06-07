from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0051_hackathon"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="hackathon",
                    name="processing_mode",
                    field=models.CharField(
                        choices=[("normal", "Normal"), ("batch", "Batch")],
                        default="normal",
                        max_length=10,
                    ),
                ),
                migrations.AddField(
                    model_name="hackathon",
                    name="expected_teams",
                    field=models.IntegerField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="hackathonsubmission",
                    name="batch_id",
                    field=models.CharField(blank=True, max_length=255, null=True),
                ),
                migrations.AddField(
                    model_name="hackathonsubmission",
                    name="batch_meta",
                    field=models.JSONField(blank=True, null=True),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE hackathon "
                        "ADD COLUMN IF NOT EXISTS processing_mode VARCHAR(10) NOT NULL DEFAULT 'normal';"
                    ),
                    reverse_sql="ALTER TABLE hackathon DROP COLUMN IF EXISTS processing_mode;",
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE hackathon "
                        "ADD COLUMN IF NOT EXISTS expected_teams INTEGER NULL;"
                    ),
                    reverse_sql="ALTER TABLE hackathon DROP COLUMN IF EXISTS expected_teams;",
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE hackathon_submission "
                        "ADD COLUMN IF NOT EXISTS batch_id VARCHAR(255) NULL;"
                    ),
                    reverse_sql="ALTER TABLE hackathon_submission DROP COLUMN IF EXISTS batch_id;",
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE hackathon_submission "
                        "ADD COLUMN IF NOT EXISTS batch_meta JSONB NULL;"
                    ),
                    reverse_sql="ALTER TABLE hackathon_submission DROP COLUMN IF EXISTS batch_meta;",
                ),
            ],
        ),
    ]
