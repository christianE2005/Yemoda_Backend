import apps.core.crypto
from django.db import migrations


def _reencrypt_existing(apps_registry, schema_editor):
    """Re-encrypt any legacy plaintext GitHub tokens. Defensive per-row: a failure on one row is
    skipped (the field's read fallback still returns its plaintext), so a deploy can never break."""
    GithubConnection = apps_registry.get_model("core", "GithubConnection")
    for conn in GithubConnection.objects.all().iterator():
        try:
            # Reading decrypts legacy plaintext via the field fallback; saving re-encrypts it.
            conn.save(update_fields=["access_token", "refresh_token"])
        except Exception:
            continue


def _noop(apps_registry, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0054_hackathon_verify"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="githubconnection",
                    name="access_token",
                    field=apps.core.crypto.EncryptedField(),
                ),
                migrations.AlterField(
                    model_name="githubconnection",
                    name="refresh_token",
                    field=apps.core.crypto.EncryptedField(blank=True, null=True),
                ),
            ],
            database_operations=[
                # Ciphertext is longer than the original token, so widen the columns to TEXT.
                # ALTER ... TYPE text is safe to re-run (text -> text is a no-op).
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE github_connection ALTER COLUMN access_token TYPE text; "
                        "ALTER TABLE github_connection ALTER COLUMN refresh_token TYPE text;"
                    ),
                    reverse_sql=(
                        "ALTER TABLE github_connection ALTER COLUMN access_token TYPE varchar(255); "
                        "ALTER TABLE github_connection ALTER COLUMN refresh_token TYPE varchar(255);"
                    ),
                ),
            ],
        ),
        migrations.RunPython(_reencrypt_existing, _noop),
    ]
