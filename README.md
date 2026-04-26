# ABCDH Technologies Backend

Monorepo con dos backends en Python para una plataforma de gestión de proyectos estilo Kanban con integración de GitHub y análisis de código con IA.

- **Django**: gestión de usuarios, autenticación JWT, proyectos, tareas y integración con GitHub App.
- **FastAPI**: agente de IA (Gemini) que analiza push events y vincula cambios a user stories automáticamente.

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend principal | Django 5 + Django REST Framework |
| Backend IA | FastAPI + Gemini API |
| Base de datos | PostgreSQL (Aiven) |
| Autenticación | JWT personalizado (Bearer token) |
| Documentación API | drf-spectacular (Swagger UI) |
| Integración GitHub | GitHub App (OAuth + Installation tokens) |
| Deploy | Railway (Procfile + railway.toml) |

## Estructura del monorepo

```text
ABCDH_Technologies/
├── backend_django/
│   ├── config/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── apps/
│   │   └── core/
│   │       ├── models.py
│   │       ├── views.py
│   │       ├── serializers.py
│   │       ├── authentication.py
│   │       └── migrations/
│   ├── requirements.txt
│   ├── Procfile
│   └── railway.toml
└── backend_fastapi/
    ├── app/
    │   ├── main.py
    │   ├── core/
    │   │   ├── database.py
    │   │   ├── deps.py
    │   │   └── gemini.py
    │   ├── models/
    │   │   └── models.py
    │   ├── routers/
    │   │   └── webhook.py
    │   └── services/
    │       ├── agent_service.py
    │       ├── github_service.py
    │       └── task_service.py
    ├── requirements.txt
    ├── Procfile
    └── railway.toml
```

## Requisitos

- Python 3.11+
- PostgreSQL (Aiven u otro)

---

## 1) Backend Django

Ruta: `backend_django`

### Levantar localmente

```bash
cd backend_django
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
python manage.py migrate --fake-initial
python manage.py runserver 8001
```

Swagger UI: `http://127.0.0.1:8001/api/docs/`

### Variables de entorno

Copia `backend_django/.env.example` → `backend_django/.env` y llena tus credenciales.

| Variable | Descripción |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Clave secreta de Django |
| `DJANGO_DEBUG` | `True` en desarrollo, `False` en producción |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos separados por coma |
| `DB_HOST` | Host PostgreSQL |
| `DB_PORT` | Puerto PostgreSQL (default `5432`) |
| `DB_NAME` | Nombre de la base de datos |
| `DB_USER` | Usuario de la base de datos |
| `DB_PASSWORD` | Contraseña de la base de datos |
| `JWT_SECRET_KEY` | Clave para firmar los JWT |
| `JWT_ALGORITHM` | Algoritmo JWT (`HS256`) |
| `JWT_EXPIRE_MINUTES` | Minutos de expiración del access token |
| `JWT_REFRESH_EXPIRE_MINUTES` | Minutos de expiración del refresh token |
| `CORS_ALLOWED_ORIGINS` | Orígenes CORS separados por coma (sin slash final) |
| `CORS_ALLOW_ALL_ORIGINS` | `true` para dev, `false` para prod |
| `GITHUB_APP_ID` | ID numérico de la GitHub App |
| `GITHUB_APP_SLUG` | Slug de la GitHub App |
| `GITHUB_APP_CLIENT_ID` | Client ID de la GitHub App |
| `GITHUB_APP_CLIENT_SECRET` | Client Secret de la GitHub App |
| `GITHUB_APP_OAUTH_CALLBACK_URL` | URL de callback OAuth |
| `GITHUB_APP_PRIVATE_KEY` | Llave privada RSA de la GitHub App (con saltos de línea reales) |
| `GITHUB_APP_WEBHOOK_SECRET` | Secret para validar webhooks |
| `GITHUB_APP_WEBHOOK_TARGET_URL` | URL del FastAPI que recibe los webhooks |

### Autenticación

Todas las rutas (excepto registro, login y webhook) requieren:

```
Authorization: Bearer <access_token>
```

El JWT contiene: `user_id`, `email`, `username`, `is_admin`, `system_role_id`.

### Endpoints Django

#### Autenticación

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| POST | `/api/auth/register/` | ❌ | Registro de usuario |
| POST | `/api/auth/login/` | ❌ | Login — retorna `access_token` y `refresh_token` |
| POST | `/api/auth/refresh/` | ❌ | Renueva el access token |

#### GitHub App

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/api/github/app/install/start/` | ✅ Admin | URL para instalar la GitHub App en una org |
| GET | `/api/github/app/oauth/start/` | ✅ | Inicia flujo OAuth de GitHub — retorna `authorize_url` |
| POST | `/api/github/app/oauth/callback/` | ✅ | Completa OAuth y vincula cuenta GitHub al usuario |
| POST | `/api/github/app/install/link/` | ✅ | Vincula una instalación GitHub App al usuario |
| GET | `/api/github/connection/status/` | ✅ | Estado de la conexión GitHub del usuario autenticado |
| GET | `/api/github/repos/` | ✅ | Lista los repos creados por el usuario (persistidos en BD) |
| POST | `/api/github/repos/` | ✅ | Crea repositorio en GitHub, configura webhook de push y lo persiste |
| GET | `/api/github/pushes/` | ✅ | Lista push events recibidos (`?project_id=1` o `?repo=owner/repo`) |
| GET | `/api/github/commits/diff/` | ✅ | Diff de un commit específico (`?repo=owner/repo&commit=SHA`) |
| GET | `/api/github/contents/` | ✅ | Navega archivos del repo (`?repo=owner/repo&path=src&ref=main`) |
| POST | `/api/github/webhook/push/` | ❌ | Receptor de webhooks push (validado por firma HMAC) |

##### Parámetros de `/api/github/contents/`

| Parámetro | Requerido | Descripción |
|-----------|-----------|-------------|
| `repo` | ✅ | `owner/nombre-repo` |
| `path` | ❌ | Ruta dentro del repo (default: raíz) |
| `ref` | ❌ | Branch, tag o SHA (default: branch principal) |

Respuesta directorio:
```json
{ "type": "dir", "path": "src", "items": [
  { "type": "dir", "name": "components", "path": "src/components" },
  { "type": "file", "name": "main.py", "path": "src/main.py", "size": 1024 }
]}
```
Respuesta archivo:
```json
{ "type": "file", "name": "main.py", "path": "src/main.py", "content": "def hello():..." }
```

#### Warnings de IA

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/api/task-warnings/` | ✅ | Lista warnings generados por el agente de IA |

##### Filtros de `/api/task-warnings/`

| Parámetro | Descripción |
|-----------|-------------|
| `task_id` | Warnings de una tarea específica |
| `status` | `active` o `resolved` |
| `project_id` | Todos los warnings de un proyecto |

#### Recursos principales (CRUD)

| Recurso | Endpoint base | Métodos |
|---------|--------------|---------|
| Usuarios | `/api/user-accounts/` | GET, POST, PUT, PATCH, DELETE |
| Proyectos | `/api/projects/` | GET, POST, PUT, PATCH, DELETE |
| Roles de proyecto | `/api/roles/` | GET, POST, PUT, PATCH, DELETE |
| Roles de sistema | `/api/system-roles/` | GET (solo lectura) |
| Miembros de proyecto | `/api/project-members/` | GET, POST, PUT, PATCH, DELETE |
| Tableros (Boards) | `/api/boards/` | GET, POST, PUT, PATCH, DELETE |
| Estados de tarea | `/api/task-statuses/` | GET, POST, PUT, PATCH, DELETE |
| Prioridades de tarea | `/api/task-priorities/` | GET, POST, PUT, PATCH, DELETE |
| Tareas | `/api/tasks/` | GET, POST, PUT, PATCH, DELETE |
| Comentarios de tarea | `/api/task-comments/` | GET, POST, PUT, PATCH, DELETE |
| Logs de actividad | `/api/activity-logs/` | GET (solo lectura) |

#### Documentación

| Endpoint | Descripción |
|----------|-------------|
| `/api/docs/` | Swagger UI |
| `/api/schema/` | OpenAPI JSON/YAML |

### Modelos de base de datos (Django)

| Tabla | Descripción principal |
|-------|-----------------------|
| `system_role` | Roles del sistema: `Admin (id=1)`, `User (id=2)` |
| `user_account` | Usuarios con FK a `system_role`, `password_hash` |
| `project` | Proyectos con `github_repo_full_name` para vinculación |
| `role` | Roles dentro de un proyecto (Admin, Manager, Developer, Viewer) |
| `project_member` | Relación usuario-proyecto-rol |
| `board` | Tableros kanban dentro de un proyecto |
| `task_status` | Estados: Backlog, To Do, In Progress, Review, Done |
| `task_priority` | Prioridades: Low, Medium, High, Critical |
| `task` | Tareas con asignado, creador, estado, prioridad, fecha límite |
| `task_comment` | Comentarios en tareas (también los genera la IA) |
| `activity_log` | Log de acciones por entidad y usuario |
| `github_connection` | Token OAuth de GitHub del usuario con soporte de refresco |
| `github_app_installation` | Instalaciones de la GitHub App por organización |
| `github_repo` | Repositorios creados desde la app (persistidos para listado) |
| `github_push_event` | Historial de push events recibidos con commits |
| `task_warning` | Warnings activos/resueltos generados por el agente de IA |

---

## 2) Backend FastAPI

Ruta: `backend_fastapi`

### Levantar localmente

```bash
cd backend_fastapi
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

Docs: `http://127.0.0.1:8002/docs`

### Variables de entorno

Copia `backend_fastapi/.env.example` → `backend_fastapi/.env`.

| Variable | Descripción |
|----------|-------------|
| `FASTAPI_DATABASE_URL` | URL completa de PostgreSQL (`postgresql+psycopg2://...`) |
| `GEMINI_API_KEY` | API key de Google Gemini |
| `GITHUB_APP_ID` | ID de la GitHub App (mismo que Django) |
| `GITHUB_APP_PRIVATE_KEY` | Llave privada RSA de la GitHub App |
| `GITHUB_APP_WEBHOOK_SECRET` | Secret para validar firmas de webhooks |

### Endpoints FastAPI

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Health check — retorna `{"status": "ok"}` |
| POST | `/webhook/push/` | Recibe push events de GitHub, valida firma HMAC-SHA256 y ejecuta análisis de IA en background |

### Flujo del agente de IA

1. GitHub envía un push event a `/webhook/push/`
2. FastAPI valida la firma con `GITHUB_APP_WEBHOOK_SECRET`
3. En background: obtiene el diff del commit via GitHub App installation token
4. Consulta las tareas activas del proyecto vinculado por `github_repo_full_name`
5. Carga los **warnings activos** de cada tarea y los incluye en el prompt
6. Envía el diff + user stories + warnings a Gemini para análisis
7. Para tareas detectadas: mueve el estado a **Review**
8. **Warnings nuevos**: si el código es parcial, crea `TaskWarning` con `status=active`
9. **Warnings resueltos**: si el nuevo código soluciona un warning previo, lo marca como `resolved`
10. Agrega un comentario automático en la tarea con el análisis completo

---

## Notas de despliegue (Railway)

- Cada backend tiene su propio `Procfile` y `railway.toml`
- La llave privada de GitHub App (`GITHUB_APP_PRIVATE_KEY`) debe pegarse **con saltos de línea reales** en Railway, no con `\n` literales
- `CORS_ALLOWED_ORIGINS` no debe terminar en `/`
- `GITHUB_APP_WEBHOOK_TARGET_URL` debe apuntar a la URL de FastAPI en Railway

## Notas de migraciones

- Si la BD ya tiene tablas preexistentes: `python manage.py migrate --fake-initial`
- Las migraciones usan `RunSQL` con `IF NOT EXISTS` para ser idempotentes en producción
- En Aiven, `DB_NAME` debe ser el nombre real de la base (`defaultdb`), no el nombre del proyecto

## Seguridad

- No subir `.env` al repositorio (está en `.gitignore`)
- Usar secretos distintos para `DJANGO_SECRET_KEY` y `JWT_SECRET_KEY`
- El endpoint de instalación de GitHub App (`/api/github/app/install/start/`) requiere rol **Admin** (`system_role_id=1`)
- Los webhooks de GitHub se validan con firma HMAC-SHA256

---

## 3) Match & Feedback endpoints (IA)

Estos endpoints permiten exportar los matches generados por el agente IA, revisar matches por push y que los desarrolladores confirmen/etiqueten los resultados. El flujo esperado es:

- El agente ML intenta emparejar el diff con historias de usuario y crea `TaskPushMatch` (con `similarity` y `model_name`).
- Los desarrolladores revisan los matches y usan el endpoint bulk para confirmar/descartar y añadir matches perdidos.
- Se puede exportar todo a CSV para análisis y entrenamiento offline.

Endpoints relevantes (Django API):

- `GET /api/matches/export/?project_id=<id>`
  - Auth: requiere token Bearer y pertenecer al proyecto (o admin).
  - Descripción: descarga un CSV con todos los `TaskPushMatch` en los proyectos accesibles o en `project_id` si se proporciona.
  - Columnas principales en CSV: `id_match, task_id, task_title, task_description, push_id, push_repo, push_ref, push_commits, created_at, similarity, model_name, feedback, coverage, reason, code_snippet`.

- `GET /api/pushes/<push_id>/matches/`
  - Auth: requiere token Bearer y pertenecer al proyecto del push.
  - Descripción: lista JSON de `TaskPushMatch` asociados a ese push (útil para mostrar en UI antes de etiquetar).

- `POST /api/pushes/<push_id>/matches/confirm/`
  - Auth: requiere token Bearer y pertenecer al proyecto del push.
  - Payload JSON:
    ```json
    {
      "confirmed_matches": [123, 124],
      "incorrect_matches": [125],
      "missed_task_ids": [10, 11]
    }
    ```
  - Descripción: confirma en bloque qué matches estaban correctos, cuáles fueron incorrectos, y permite crear registros `TaskPushMatch` manuales para tareas que el ML omitió (`missed_task_ids`). Devuelve conteos de acciones realizadas.

- `POST /api/matches/<match_id>/feedback/`
  - Auth: requiere token Bearer y pertenecer al proyecto de la historia relacionada.
  - Payload JSON:
    ```json
    { "feedback": "correct" }
    ```
    o
    ```json
    { "feedback": "incorrect" }
    ```
  - Descripción: marca un `TaskPushMatch` individual como correcto o incorrecto (campo `feedback`).

Ejemplo rápido (curl):

```
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-host/api/pushes/42/matches/"

curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"confirmed_matches": [1,2], "incorrect_matches": [3], "missed_task_ids": [10]}' \
  "https://your-host/api/pushes/42/matches/confirm/"

curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"feedback": "correct"}' \
  "https://your-host/api/matches/7/feedback/"
```

Dónde mirar en el código:

- Implementación export CSV: [backend_django/apps/core/views.py](backend_django/apps/core/views.py#L1548-L1628)
- Listar matches por push: [backend_django/apps/core/views.py](backend_django/apps/core/views.py#L1628-L1690)
- Bulk feedback para push: [backend_django/apps/core/views.py](backend_django/apps/core/views.py#L1690-L1790)
- FastAPI webhook / persistencia de `similarity`/`model_name`: [backend_fastapi/app/routers/webhook.py](backend_fastapi/app/routers/webhook.py#L1-L340)

---

Con esto ya puedes descargar el Excel / CSV, etiquetar localmente y volver a subir etiquetas con `POST /api/pushes/<push_id>/matches/confirm/` o marcar individualmente con `POST /api/matches/<match_id>/feedback/`.
