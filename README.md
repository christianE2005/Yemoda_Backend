# ABCDH Technologies Backend

Monorepo con dos backends en Python:

- **Django**: gestion de usuarios, autenticacion y API REST.
- **FastAPI**: servicios de ML y agentes.

## Estructura

```text
ABCDH_Technologies/
├── backend_django/
└── backend_fastapi/
```

## Requisitos

- Python 3.11+ (recomendado)
- Acceso a PostgreSQL (Aiven u otro)

## 1) Backend Django

Ruta: `backend_django`

### Variables de entorno

1. Copia el archivo de ejemplo:
   - `backend_django/.env.example` -> `backend_django/.env`
2. Llena tus credenciales reales.

Variables principales:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM` (usar `HS256` para el setup actual)
- `JWT_EXPIRE_MINUTES`
- `JWT_REFRESH_EXPIRE_MINUTES`
- `GITHUB_APP_ID`
- `GITHUB_APP_SLUG`
- `GITHUB_APP_CLIENT_ID`
- `GITHUB_APP_CLIENT_SECRET`
- `GITHUB_APP_OAUTH_CALLBACK_URL`
- `GITHUB_APP_PRIVATE_KEY`
- `GITHUB_APP_WEBHOOK_SECRET`
- `GITHUB_APP_WEBHOOK_TARGET_URL`

### Levantar Django

```bash
cd backend_django
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate --fake-initial
python manage.py runserver 8001
```

Swagger/OpenAPI:

- `http://127.0.0.1:8001/api/docs/`
- `http://127.0.0.1:8001/api/schema/`

### Auth endpoints (Django)

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/refresh/`

### GitHub App + repos + webhook (Django)

- `GET /api/github/app/install/start/`
  - Regresa URL para instalar tu GitHub App en cuenta/org.
- `GET /api/github/app/oauth/start/`
  - Regresa `authorize_url` para login del usuario via GitHub App OAuth.
- `POST /api/github/app/oauth/callback/`
  - Body: `{ "code": "...", "state": "..." }`
  - Vincula usuario local con su cuenta GitHub.
  - Tambien soporta callback GET para GitHub App y muestra texto simple:
    - `OAuth completed successfully` o
    - `OAuth failed: ...`
- `POST /api/github/app/install/link/`
  - Body: `{ "user_id": 1, "installation_id": 12345678 }`
  - Vincula instalacion GitHub App con usuario local.
- `POST /api/github/repos/`
  - Crea repositorio desde la app:
    - `owner_type="user"`: usa token OAuth del usuario.
    - `owner_type="org"`: usa token de instalacion GitHub App.
  - Tambien agrega webhook de `push`.
- `POST /api/github/webhook/push/`
  - Receptor de webhook. Valida firma y devuelve resumen de cambios en commits.

#### Ejemplo register

```json
{
  "email": "user@example.com",
  "username": "newuser",
  "password": "Password123!"
}
```

#### Ejemplo login

```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

#### Ejemplo refresh

```json
{
  "refresh_token": "tu_refresh_token"
}
```

## 2) Backend FastAPI

Ruta: `backend_fastapi`

### Variables de entorno

1. Copia:
   - `backend_fastapi/.env.example` -> `backend_fastapi/.env`
2. Configura:
   - `FASTAPI_DATABASE_URL`

### Levantar FastAPI

```bash
cd backend_fastapi
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

Docs:

- `http://127.0.0.1:8002/docs`

## Notas de DB y migraciones

- Si la BD ya tiene tablas preexistentes, usa:
  - `python manage.py migrate --fake-initial`
- Si ves errores de "relation already exists", la causa suele ser migraciones iniciales contra tablas ya creadas.
- En Aiven, revisa que `DB_NAME` sea el nombre real de la base (por ejemplo `defaultdb`), no un nombre de proyecto.

## Seguridad minima recomendada

- No subir `.env` al repositorio.
- Usar secretos distintos para:
  - `DJANGO_SECRET_KEY`
  - `JWT_SECRET_KEY`
- Mantener `JWT_ALGORITHM=HS256` en esta version base.
