from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_useraccount_is_premium_stripepayment"),
    ]

    operations = [
        # 1. Re-add is_admin column to DB
        migrations.RunSQL(
            sql="ALTER TABLE user_account ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;",
            reverse_sql="ALTER TABLE user_account DROP COLUMN IF EXISTS is_admin;",
        ),
        # 2. Drop id_system_role FK column from user_account
        migrations.RunSQL(
            sql="ALTER TABLE user_account DROP COLUMN IF EXISTS id_system_role;",
            reverse_sql="""
                ALTER TABLE user_account
                    ADD COLUMN IF NOT EXISTS id_system_role BIGINT
                        REFERENCES system_role(id_system_role)
                        ON DELETE SET NULL;
                UPDATE user_account SET id_system_role = 2 WHERE id_system_role IS NULL;
            """,
        ),
        # 3. Drop system_role table
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS system_role;",
            reverse_sql="""
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
            """,
        ),
        # 4. Sync Django state
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="useraccount", name="system_role"),
                migrations.AddField(
                    model_name="useraccount",
                    name="is_admin",
                    field=models.BooleanField(default=False),
                ),
                migrations.DeleteModel(name="SystemRole"),
            ],
            database_operations=[],
        ),
    ]
