from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0028_board_coding_style"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="board",
                    name="review_focus",
                    field=models.CharField(
                        choices=[
                            ("strict", "Strict — Story & acceptance criteria only"),
                            ("general", "General — Story + code quality suggestions"),
                        ],
                        default="general",
                        max_length=10,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE board ADD COLUMN IF NOT EXISTS review_focus varchar(10) NOT NULL DEFAULT 'general';",
                    reverse_sql="ALTER TABLE board DROP COLUMN IF EXISTS review_focus;",
                ),
            ],
        ),
    ]
