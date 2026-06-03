# ABCDH Technologies — Backend

Monorepo con dos backends en Python para una plataforma de gestión de proyectos estilo Kanban con integración de GitHub y análisis de código con IA.

- **Django** (`backend_django/`): API principal — usuarios, autenticación JWT, proyectos, tableros, tareas e integración con GitHub App.
- **FastAPI** (`backend_fastapi/`): agente de IA (Claude) que analiza push events y vincula cambios a user stories automáticamente. Incluye además un módulo de predicción de riesgo de proyectos (ML).

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend principal | Django 5 + Django REST Framework 3.15 |
| Backend IA | FastAPI 0.111 + Anthropic Claude |
| Base de datos | PostgreSQL (Aiven) — compartida entre ambos backends |
| Autenticación | JWT personalizado (Bearer token) |
| Documentación API | drf-spectacular (Swagger UI en `/api/docs/`) |
| Integración GitHub | GitHub App (OAuth + Installation tokens + Webhooks) |
| ML de riesgo | scikit-learn ElasticNet + joblib |
| Deploy | Railway (Procfile + railway.toml por backend) |

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
    │   │   └── anthropic.py
    │   ├── models/
    │   │   └── models.py
    │   ├── routers/
    │   │   ├── webhook.py
    │   │   └── predictions.py
    │   └── services/
    │       ├── agent_service.py
    │       ├── github_service.py
    │       ├── task_service.py
    │       └── ml_service.py
    ├── requirements.txt
    ├── Procfile
    └── railway.toml
```

## Requisitos

- Python 3.12+
- PostgreSQL (Aiven u otro)

---

## 1) Backend Django

Ruta: `backend_django/`

### Levantar localmente

```bash
cd backend_django
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
python manage.py migrate --fake-initial
python manage.py runserver 8001
```

Swagger UI: `http://127.0.0.1:8001/api/docs/`

### Variables de entorno

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
| `GITHUB_APP_WEBHOOK_SECRET` | Secret para validar webhooks entrantes |
| `GITHUB_APP_WEBHOOK_TARGET_URL` | URL del FastAPI que recibe los webhooks reenviados |

### Autenticación

Todas las rutas (excepto login y webhook) requieren:

```
Authorization: Bearer <access_token>
```

El JWT contiene: `user_id`, `email`, `username`, `is_admin`, `system_role_id`.

> El registro de nuevos usuarios lo hace un **Admin** vía `POST /api/user-accounts/`.

---

### Endpoints Django

#### Autenticación

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| POST | `/api/auth/login/` | ❌ | Login — retorna `access_token` y `refresh_token` |
| POST | `/api/auth/refresh/` | ❌ | Renueva el access token con el refresh token |
| POST | `/api/auth/change-password/` | ✅ | Cambia la contraseña del usuario autenticado |

#### Recursos principales (CRUD)

| Recurso | Endpoint base | Métodos | Filtros disponibles |
|---------|--------------|---------|---------------------|
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
| Tareas | `/api/tasks/` | GET, POST, PUT, PATCH, DELETE | `?project=`, `?sprint=`, `?board_column=`, `?milestone=`, `?tag=`, `?backlog=true`, `?parent=`, `?top_level=true` |
| Asignaciones de tarea | `/api/task-assignments/` | GET, POST, PUT, PATCH, DELETE | `?task=`, `?user=` |
| Comentarios de tarea | `/api/task-comments/` | GET, POST, PUT, PATCH, DELETE | `?task=` |
| Logs de actividad | `/api/activity-logs/` | GET (solo lectura) | — |

> \* `POST /api/user-accounts/` y `DELETE /api/user-accounts/{id}/` requieren rol **Admin**.

#### Endpoints anidados de proyectos

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/api/projects/{project_id}/members/` | ✅ | Lista los miembros del proyecto |
| POST | `/api/projects/{project_id}/members/` | ✅ | Añade usuario al proyecto (también como colaborador en GitHub si hay repos vinculados) |
| GET | `/api/projects/{project_id}/repos/` | ✅ | Lista los repositorios vinculados al proyecto |
| POST | `/api/projects/{project_id}/repos/` | ✅ Creador | Vincula un repositorio existente al proyecto (máximo 4) |
| DELETE | `/api/projects/{project_id}/repos/{repo_id}/` | ✅ Creador | Desvincula un repositorio del proyecto |

Body de `POST /api/projects/{project_id}/members/`:
```json
{ "user_id": 5, "role_id": 2 }
```

Body de `POST /api/projects/{project_id}/repos/`:
```json
{ "repo_full_name": "owner/mi-repo" }
```

#### GitHub App

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/api/github/app/install/start/` | ✅ Admin | Genera la URL de instalación de la GitHub App en una organización |
| GET | `/api/github/app/oauth/start/` | ✅ | Inicia flujo OAuth — retorna `authorize_url` |
| POST | `/api/github/app/oauth/callback/` | ✅ | Completa OAuth y vincula la cuenta de GitHub al usuario |
| POST | `/api/github/app/install/link/` | ✅ | Vincula una instalación de la GitHub App al usuario |
| GET | `/api/github/connection/status/` | ✅ | Estado de la conexión GitHub del usuario autenticado |
| DELETE | `/api/github/connection/status/` | ✅ | Desvincula la cuenta de GitHub del usuario autenticado |
| GET | `/api/github/repos/` | ✅ | Lista los repos creados desde la plataforma (persistidos en BD) |
| POST | `/api/github/repos/` | ✅ | Crea repositorio en GitHub, configura webhook de push y lo persiste |
| GET | `/api/github/pushes/` | ✅ | Lista push events recibidos (`?project_id=1` o `?repo=owner/repo`) |
| GET | `/api/github/commits/diff/` | ✅ | Diff de un commit (`?repo=owner/repo&commit=SHA`) |
| GET | `/api/github/contents/` | ✅ | Navega archivos del repo (`?repo=owner/repo&path=src&ref=main`) |
| POST | `/api/github/webhook/push/` | ❌ | Receptor de webhooks push (validado por firma HMAC-SHA256) |

Respuesta de `GET /api/github/contents/` — directorio:
```json
{
  "type": "dir",
  "path": "src",
  "items": [
    { "type": "dir", "name": "components", "path": "src/components" },
    { "type": "file", "name": "main.py", "path": "src/main.py", "size": 1024 }
  ]
}
```

Respuesta — archivo:
```json
{ "type": "file", "name": "main.py", "path": "src/main.py", "content": "def hello():..." }
```

#### Tareas — Endpoints especiales

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/api/tasks/{task_id}/history/` | ✅ | Push matches vinculados a la tarea por el agente IA, ordenados por fecha desc |
| POST | `/api/tasks/{task_id}/branch/` | ✅ | Crea una rama de GitHub para la tarea y retorna el comando `git checkout` |

##### `POST /api/tasks/{task_id}/branch/`

Crea una rama con formato `{task_id}-{slug-del-titulo}` en el repositorio del proyecto usando la GitHub App.

Body:
```json
{ "base_branch": "main" }
```

Respuesta `201`:
```json
{
  "branch_name": "42-fix-login-con-google",
  "checkout_command": "git fetch origin && git checkout 42-fix-login-con-google"
}
```

| Status | Cuándo ocurre |
|--------|--------------|
| `201` | Rama creada correctamente |
| `400` | `base_branch` vacío, rama base no existe, repo no vinculado o GitHub App no instalada |
| `403` | El usuario no pertenece al proyecto |
| `404` | Tarea no encontrada |
| `409` | La rama ya existe en GitHub |

> Cuando alguien hace push a una rama `{task_id}-*`, el agente analiza **únicamente esa tarea** en lugar de todas las del proyecto.

#### Subtareas y tareas épicas

Las tareas soportan jerarquía mediante el campo auto-referencial `parent`. Una tarea con `parent` es una **subtarea**; una tarea con subtareas funciona como **historia o épica** que agrupa el trabajo. La jerarquía admite **profundidad arbitraria** (épica → historia → subtarea → …) reusando la misma tabla `task`, por lo que las subtareas heredan todo: asignados, comentarios, warnings de IA, ramas Git y push matches.

**Crear una subtarea** — `POST /api/tasks/` con el campo `parent`:
```json
{ "project": 1, "title": "Validar formulario de login", "parent": 42 }
```

**Filtros nuevos en `GET /api/tasks/`:**

| Parámetro | Descripción |
|-----------|-------------|
| `?parent=42` | Lista las subtareas directas de la tarea 42 |
| `?top_level=true` | Lista solo tareas sin padre (épicas/tareas independientes) |

**Campos calculados en la respuesta de cada tarea:**

| Campo | Descripción |
|-------|-------------|
| `subtask_progress` | `{ "total", "completed", "percent" }` sobre las subtareas directas |
| `rolled_up_points` | Suma de `story_points` de las **hojas** descendientes (solo las hojas llevan puntos reales; el padre los acumula) |

**Reglas de negocio:**

- **Bloqueo de cierre:** una tarea padre **no puede moverse a una columna final** (completarse) mientras tenga subtareas sin terminar → responde `400`.
- **Sin ciclos:** una tarea no puede ser su propia subtarea ni asignarse como padre a uno de sus descendientes.
- **Mismo proyecto:** el `parent` debe pertenecer al mismo proyecto.
- **Borrado en cascada:** eliminar una tarea padre elimina sus subtareas (`ON DELETE CASCADE`).
- **ML:** el modelo de riesgo cuenta puntos **solo de las hojas** para no duplicar la velocidad del proyecto.
- **Agente IA:** al analizar un push, las subtareas se envían a Claude **anidadas bajo su padre**, y una rama `{id_padre}-...` arrastra al análisis también a sus subtareas activas.

#### Warnings de IA

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| GET | `/api/task-warnings/` | ✅ | Lista warnings generados por el agente de IA |
| DELETE | `/api/task-warnings/{warning_id}/` | ✅ | Elimina un warning (solo miembros del proyecto) |

Filtros de `GET /api/task-warnings/`:

| Parámetro | Descripción |
|-----------|-------------|
| `task_id` | Warnings de una tarea específica |
| `status` | `active` o `resolved` |
| `project_id` | Todos los warnings de un proyecto |

Cada warning incluye el campo `severity`:

| Valor | Significado |
|-------|-------------|
| `"critical"` | Vulnerabilidad de seguridad o riesgo de pérdida de datos |
| `"warning"` | Requisito faltante o comportamiento roto |
| `"info"` | Mejora menor u observación opcional |

#### Documentación

| Endpoint | Descripción |
|----------|-------------|
| `/api/docs/` | Swagger UI interactivo |
| `/api/schema/` | OpenAPI JSON/YAML |

---

### Modelos de base de datos (Django)

| Tabla | Descripción |
|-------|-------------|
| `system_role` | Roles del sistema: `Admin (id=1)`, `User (id=2)` |
| `user_account` | Usuarios con FK a `system_role` y `password_hash` |
| `project` | Proyectos con `created_by`, estado de ciclo de vida y `review_branches` (ramas que activan el agente) |
| `role` | Roles dentro de un proyecto (Admin, Manager, Developer, Viewer, Stakeholder) |
| `project_member` | Relación usuario↔proyecto↔rol |
| `project_repo` | Repositorios vinculados a un proyecto (hasta 4 por proyecto) |
| `board` | Tableros kanban; incluye `response_language` y `custom_instructions` para configurar el agente IA |
| `board_column` | Columnas personalizadas de un tablero |
| `sprint` | Sprints de un proyecto con fechas y estado |
| `milestone` | Milestones/hitos de un proyecto |
| `tag` | Etiquetas reutilizables por proyecto |
| `task_status` | Estados: Backlog, To Do, In Progress, Review, Done |
| `task_priority` | Prioridades: Low, Medium, High, Critical |
| `task` | Tareas con sprint, columna de tablero, milestone, tags, fecha límite y `scrum_number` (story points). Campo `parent` (auto-referencia) para **subtareas/épicas**: una tarea con `parent` es subtarea; soporta jerarquía a cualquier profundidad (épica → historia → subtarea) |
| `task_assignment` | Asignaciones de usuarios a tareas (M2M explícita) |
| `task_comment` | Comentarios en tareas (también los genera la IA automáticamente) |
| `task_push_match` | Relación tarea↔push generada por el agente IA |
| `activity_log` | Log de acciones por entidad y usuario |
| `github_connection` | Token OAuth de GitHub del usuario con soporte de refresco |
| `github_app_installation` | Instalaciones de la GitHub App por organización |
| `github_repo` | Repositorios creados desde la app (persistidos para listado) |
| `github_push_event` | Historial de push events recibidos con commits |
| `task_warning` | Warnings activos/resueltos generados por el agente IA; incluye campo `severity` (`critical`, `warning`, `info`) |

#### Campos de configuración del agente en `board`

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `response_language` | `"es"` \| `"en"` | `"es"` | Idioma en el que el agente redacta análisis y comentarios |
| `custom_instructions` | texto libre \| `null` | `null` | Instrucciones personalizadas que el agente seguirá (ej. "Este proyecto usa Flutter") |
| `coding_style` | string | `"standard"` | Estilo de código esperado |
| `review_focus` | `"general"` \| `"strict"` | `"general"` | Nivel de exigencia del análisis |
| `tech_stack` | string | `"mixed"` | Stack tecnológico del proyecto |
| `naming_convention` | string | `"default"` | Convención de nombres del código |

#### Campo `review_branches` en `project`

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `review_branches` | string | `""` | Ramas separadas por coma (ej. `"main,develop"`) que activan el agente. Vacío = analiza todas |

> Las ramas con formato `{task_id}-*` siempre se analizan, independientemente de `review_branches`.

---

## 2) Backend FastAPI

Ruta: `backend_fastapi/`

### Levantar localmente

```bash
cd backend_fastapi
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

Docs: `http://127.0.0.1:8002/docs`

### Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `FASTAPI_DATABASE_URL` | URL completa de PostgreSQL (`postgresql+psycopg2://...`) |
| `ANTHROPIC_API_KEY` | API key de Anthropic (Claude) |
| `GITHUB_APP_ID` | ID de la GitHub App (mismo que Django) |
| `GITHUB_APP_PRIVATE_KEY` | Llave privada RSA de la GitHub App |
| `GITHUB_APP_WEBHOOK_SECRET` | Secret para validar firmas HMAC-SHA256 de webhooks |

### Endpoints FastAPI

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Health check — retorna `{"status": "ok"}` |
| POST | `/webhook/push/` | Recibe push events de GitHub, valida firma HMAC-SHA256 y ejecuta análisis de IA en background |
| POST | `/predictions/project-risk/` | Predice si un proyecto va a retrasarse respecto a su deadline |
| POST | `/predictions/train/` | Reentrena el modelo ML con todos los proyectos completados |

---

### Agente de IA — Flujo completo

El agente analiza cada push recibido y vincula los cambios de código a las user stories activas del proyecto.

```
1. GitHub envía push event → POST /webhook/push/
2. FastAPI valida firma HMAC-SHA256 con GITHUB_APP_WEBHOOK_SECRET
3. Busca el proyecto en BD por repo_full_name
4. Aplica filtro de ramas (review_branches):
   - Rama con formato {task_id}-*  → analiza solo esa tarea (modo enfocado)
   - review_branches configurado   → omite ramas no incluidas en la lista
   - review_branches vacío         → analiza todas las ramas
5. En background: obtiene el diff del push vía GitHub App installation token
6. Consulta tareas activas + warnings activos del proyecto
7. Lee configuración del tablero: coding_style, review_focus, tech_stack,
   naming_convention, response_language, custom_instructions
8. Envía a Claude: diff + user stories + warnings activos + configuración del tablero
9. Claude retorna matches: { story_id, coverage, reason, new_warnings[], resolved_warning_ids[] }
   - new_warnings incluye { message, severity: "critical" | "warning" | "info" }
10. Por cada match detectado:
    - Mueve la tarea al estado "En revisión"
    - Crea TaskWarning nuevos con su severidad correspondiente
    - Marca como resolved los warnings que Claude identificó como solucionados
    - Agrega comentario automático en la tarea con el análisis completo
```

#### Configuración del análisis por tablero

| Parámetro | Efecto en el agente |
|-----------|---------------------|
| `response_language` | El agente responde en español (`"es"`) o inglés (`"en"`) |
| `custom_instructions` | Reglas adicionales del proyecto inyectadas en el prompt |
| `review_focus` | `"strict"` activa un prompt más exigente; `"general"` es más permisivo |
| `coding_style` | Ajusta las instrucciones de estilo del prompt |
| `tech_stack` | Incluye contexto tecnológico en el prompt |
| `naming_convention` | Instrucciones sobre convenciones de nombres esperadas |

---

### Módulo de predicción de riesgos (ML)

Usa **ElasticNet** (regularización L1+L2) para predecir si un proyecto se va a atrasar respecto a su deadline. Maneja features correlacionadas con pocos datos históricos sin overfitting.

#### `POST /predictions/project-risk/`

Body:
```json
{ "project_id": 5 }
```

Respuesta:
```json
{
  "project_id": 5,
  "at_risk": true,
  "confidence": 0.74,
  "predicted_end_date": "2026-06-15",
  "days_delay_estimate": 12,
  "model_used": "elasticnet",
  "features": {
    "velocity_last_week": 8.0,
    "velocity_avg": 6.3,
    "velocity_trend": 0.27,
    "sprint_consistency": 3.1,
    "points_remaining": 45.0,
    "days_remaining": 33.0,
    "completion_rate": 0.62,
    "tasks_in_progress": 7.0
  }
}
```

| Campo | Descripción |
|-------|-------------|
| `at_risk` | `true` si el proyecto tiene riesgo de atraso |
| `confidence` | Confianza del modelo (0–1). `null` si no hay modelo entrenado (usa burndown matemático) |
| `model_used` | `"elasticnet"` o `"rule_based_burndown"` (fallback con < 3 proyectos completados) |
| `days_delay_estimate` | Días estimados de retraso (0 si está a tiempo) |

> Mientras `scrum_number` sea `NULL` en las tareas, cada tarea vale **1 punto** (`COALESCE`).

#### `POST /predictions/train/`

Reentrena el modelo bajo demanda. Requiere al menos **3 proyectos** con `status='closed'` y tareas completadas. El modelo se persiste en `backend_fastapi/app/ml_models/` con `joblib`.

---

## Notas de despliegue (Railway)

- Cada backend tiene su propio `Procfile` y `railway.toml` para deploys independientes
- `GITHUB_APP_PRIVATE_KEY` debe pegarse con **saltos de línea reales** en Railway (no `\n` literales)
- `CORS_ALLOWED_ORIGINS` no debe terminar en `/`
- `GITHUB_APP_WEBHOOK_TARGET_URL` debe apuntar a la URL del FastAPI en Railway

## Notas de migraciones

- Si la BD ya tiene tablas preexistentes: `python manage.py migrate --fake-initial`
- Las migraciones usan `RunSQL` con `IF NOT EXISTS` para ser idempotentes en producción
- En Aiven, `DB_NAME` debe ser el nombre real de la base (normalmente `defaultdb`), no el nombre del proyecto Railway

## Seguridad

- No subir `.env` al repositorio (en `.gitignore`)
- Usar secretos distintos para `DJANGO_SECRET_KEY` y `JWT_SECRET_KEY`
- El endpoint de instalación de GitHub App (`/api/github/app/install/start/`) requiere rol **Admin** (`system_role_id=1`)
- Los webhooks de GitHub se validan con firma HMAC-SHA256 tanto en Django como en FastAPI
