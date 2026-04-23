from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_useraccount_is_admin"),
    ]

    operations = [
        # 1. Create system_role table
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS system_role (
                    id_system_role BIGSERIAL PRIMARY KEY,
                    name VARCHAR(50) UNIQUE NOT NULL,
                    description TEXT
                );
                INSERT INTO system_role (id_system_role, name, description)
                VALUES
                    (1, 'Admin', 'Administrador del sistema con acceso total'),
                    (2, 'User', 'Usuario estándar de la plataforma')
                ON CONFLICT (id_system_role) DO NOTHING;
                SELECT setval(
                    pg_get_serial_sequence('system_role', 'id_system_role'),
                    (SELECT MAX(id_system_role) FROM system_role)
                );
            """,
            reverse_sql="DROP TABLE IF EXISTS system_role;",
        ),
        # 2. Add id_system_role FK to user_account (default = 2 = User)
        migrations.RunSQL(
            sql="""
                ALTER TABLE user_account
                    ADD COLUMN IF NOT EXISTS id_system_role BIGINT
                        REFERENCES system_role(id_system_role)
                        ON DELETE SET NULL;
                UPDATE user_account SET id_system_role = 2 WHERE id_system_role IS NULL;
            """,
            reverse_sql="ALTER TABLE user_account DROP COLUMN IF EXISTS id_system_role;",
        ),
        # 3. Drop the old is_admin boolean column
        migrations.RunSQL(
            sql="ALTER TABLE user_account DROP COLUMN IF EXISTS is_admin;",
            reverse_sql="ALTER TABLE user_account ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;",
        ),
        # 4. Sync Django state
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="SystemRole",
                    fields=[
                        ("id_system_role", models.BigAutoField(primary_key=True, serialize=False)),
                        ("name", models.CharField(max_length=50, unique=True)),
                        ("description", models.TextField(blank=True, null=True)),
                    ],
                    options={"db_table": "system_role"},
                ),
                migrations.RemoveField(model_name="useraccount", name="is_admin"),
                migrations.AddField(
                    model_name="useraccount",
                    name="system_role",
                    field=models.ForeignKey(
                        blank=True,
                        db_column="id_system_role",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="users",
                        to="core.systemrole",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
