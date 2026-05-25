from django.db import migrations


class Migration(migrations.Migration):
    """
    Renombra la tabla 'role' → 'project_role' para evitar el conflicto con la
    palabra reservada ROLE de PostgreSQL, que causa OperationalError en ciertos
    contextos de introspección y genera HTTP 500 en /api/roles/.
    """

    dependencies = [
        ("core", "0040_useraccount_stripe_fields"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "role" RENAME TO "project_role";',
            reverse_sql='ALTER TABLE "project_role" RENAME TO "role";',
        ),
    ]
