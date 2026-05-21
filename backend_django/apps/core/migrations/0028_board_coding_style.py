from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_boardcolumn_is_review"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="board",
                    name="coding_style",
                    field=models.CharField(
                        choices=[
                            ("standard", "Standard"),
                            ("clean_code", "Clean Code / SOLID"),
                            ("tdd", "Test-Driven Development"),
                            ("security", "Security-First"),
                            ("performance", "Performance & Optimization"),
                        ],
                        default="standard",
                        max_length=20,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE board ADD COLUMN IF NOT EXISTS coding_style varchar(20) NOT NULL DEFAULT 'standard';",
                    reverse_sql="ALTER TABLE board DROP COLUMN IF EXISTS coding_style;",
                ),
            ],
        ),
    ]
