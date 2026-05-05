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
| POST | `/api/auth/login/` | ❌ | Login — retorna `access_token` y `refresh_token` |
| POST | `/api/auth/refresh/` | ❌ | Renueva el access token |

> El registro de usuarios lo hace un **Admin** via `POST /api/user-accounts/`.

#### GitHub App

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/api/github/app/install/start/` | ✅ Admin | URL para instalar la GitHub App en una org |
| GET | `/api/github/app/oauth/start/` | ✅ | Inicia flujo OAuth de GitHub — retorna `authorize_url` |
| POST | `/api/github/app/oauth/callback/` | ✅ | Completa OAuth y vincula cuenta GitHub al usuario |
| POST | `/api/github/app/install/link/` | ✅ | Vincula una instalación GitHub App al usuario |
| GET | `/api/github/connection/status/` | ✅ | Estado de la conexión GitHub del usuario autenticado |
| DELETE | `/api/github/connection/status/` | ✅ | Desvincula la cuenta de GitHub del usuario autenticado |
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
| DELETE | `/api/task-warnings/{warning_id}/` | ✅ | Elimina un warning (solo miembros del proyecto) |

##### Filtros de `/api/task-warnings/`

| Parámetro | Descripción |
|-----------|-------------|
| `task_id` | Warnings de una tarea específica |
| `status` | `active` o `resolved` |
| `project_id` | Todos los warnings de un proyecto |

#### Recursos principales (CRUD)

| Recurso | Endpoint base | Métodos | Filtros |
|---------|--------------|---------|---------|
| Usuarios | `/api/user-accounts/` | GET, POST*, PUT, PATCH, DELETE* | — |
| Proyectos | `/api/projects/` | GET, POST, PUT, PATCH, DELETE | — |
| Roles de proyecto | `/api/roles/` | GET, POST, PUT, PATCH, DELETE | — |
| Roles de sistema | `/api/system-roles/` | GET (solo lectura) | — |
| Miembros de proyecto | `/api/project-members/` | GET, POST, PUT, PATCH, DELETE | `?project=` |
| Tableros (Boards) | `/api/boards/` | GET, POST, PUT, PATCH, DELETE | `?project=` |
| Columnas de tablero | `/api/board-columns/` | GET, POST, PUT, PATCH, DELETE | `?board=` |
| Sprints | `/api/sprints/` | GET, POST, PUT, PATCH, DELETE | `?project=`, `?status=` |
| Milestones | `/api/milestones/` | GET, POST, PUT, PATCH, DELETE | `?project=` |
| Tags | `/api/tags/` | GET, POST, PUT, PATCH, DELETE | `?project=` |
| Estados de tarea | `/api/task-statuses/` | GET, POST, PUT, PATCH, DELETE | — |
| Prioridades de tarea | `/api/task-priorities/` | GET, POST, PUT, PATCH, DELETE | — |
| Tareas | `/api/tasks/` | GET, POST, PUT, PATCH, DELETE | `?project=`, `?sprint=`, `?board_column=`, `?milestone=`, `?tag=`, `?backlog=true` |
| Asignaciones de tarea | `/api/task-assignments/` | GET, POST, PUT, PATCH, DELETE | `?task=`, `?user=` |
| Comentarios de tarea | `/api/task-comments/` | GET, POST, PUT, PATCH, DELETE | `?task=` |
| Logs de actividad | `/api/activity-logs/` | GET (solo lectura) | — |

> \* `POST /api/user-accounts/` y `DELETE /api/user-accounts/{id}/` requieren rol **Admin**.

#### Endpoints anidados de proyectos

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/api/projects/{project_id}/members/` | ✅ | Lista los miembros del proyecto |
| POST | `/api/projects/{project_id}/members/` | ✅ | Añade un usuario al proyecto (y como colaborador en GitHub si hay repos vinculados) |
| GET | `/api/projects/{project_id}/repos/` | ✅ | Lista los repositorios vinculados al proyecto |
| POST | `/api/projects/{project_id}/repos/` | ✅ Creador | Vincula un repositorio existente al proyecto (máximo 4) |
| DELETE | `/api/projects/{project_id}/repos/{repo_id}/` | ✅ Creador | Desvincula un repositorio del proyecto |

##### Body de `POST /api/projects/{project_id}/members/`

```json
{ "user_id": 5, "role_id": 2 }
```

##### Body de `POST /api/projects/{project_id}/repos/`

```json
{ "repo_full_name": "owner/mi-repo" }
```

#### Historial de push por tarea

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/api/tasks/{task_id}/history/` | ✅ | Push matches vinculados a la tarea por el agente de IA, ordenados por fecha desc |

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
| `project` | Proyectos con `created_by` y estado de ciclo de vida |
| `role` | Roles dentro de un proyecto (Admin, Manager, Developer, Viewer, Stakeholder) |
| `project_member` | Relación usuario-proyecto-rol |
| `project_repo` | Repositorios vinculados a un proyecto (hasta 4 por proyecto) |
| `board` | Tableros kanban dentro de un proyecto |
| `board_column` | Columnas personalizadas de un tablero |
| `sprint` | Sprints de un proyecto con fechas y estado |
| `milestone` | Milestones/hitos de un proyecto |
| `tag` | Etiquetas reutilizables por proyecto |
| `task_status` | Estados: Backlog, To Do, In Progress, Review, Done |
| `task_priority` | Prioridades: Low, Medium, High, Critical |
| `task` | Tareas con sprint, columna de tablero, milestone, tags, fecha límite |
| `task_assignment` | Asignaciones de usuarios a tareas (M2M explícita) |
| `task_comment` | Comentarios en tareas (también los genera la IA) |
| `task_push_match` | Relación tarea↔push generada por el agente IA |
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
