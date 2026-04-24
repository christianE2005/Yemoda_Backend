from pathlib import Path
from urllib.parse import unquote, urlparse
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
_allowed_hosts_raw = os.getenv("DJANGO_ALLOWED_HOSTS", "*")
ALLOWED_HOSTS = [host.strip() for host in _allowed_hosts_raw.split(",") if host.strip()]

# Railway health checks can use internal hostnames that differ from public domains.
if os.getenv("RAILWAY_ENVIRONMENT"):
    for host in [".railway.internal", ".railway.app", ".up.railway.app", "localhost", "127.0.0.1"]:
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

INSTALLED_APPS = [
    'corsheaders',
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if origin.strip()
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

_raw_db_url = os.getenv("DATABASE_URL", "")
if _raw_db_url.startswith("postgres://"):
    _raw_db_url = "postgresql" + _raw_db_url[len("postgres"):]

if _raw_db_url:
    _db = urlparse(_raw_db_url)
    _db_opts: dict = {}
    if _db.query:
        for _pair in _db.query.split("&"):
            if "=" in _pair:
                _k, _v = _pair.split("=", 1)
                if _k == "sslmode":
                    _db_opts["sslmode"] = _v
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(_db.path.lstrip("/")),
            "USER": unquote(_db.username or ""),
            "PASSWORD": unquote(_db.password or ""),
            "HOST": _db.hostname or "localhost",
            "PORT": str(_db.port or 5432),
            "OPTIONS": _db_opts,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "app_db"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.core.authentication.UserAccountAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ABCDH Backend API",
    "DESCRIPTION": "API base con Django REST Framework",
    "VERSION": "1.0.0",
    "SECURITY": [{"BearerAuth": []}],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
    },
}

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
JWT_REFRESH_EXPIRE_MINUTES = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "10080"))

GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_APP_SLUG = os.getenv("GITHUB_APP_SLUG", "")
GITHUB_APP_CLIENT_ID = os.getenv("GITHUB_APP_CLIENT_ID", "")
GITHUB_APP_CLIENT_SECRET = os.getenv("GITHUB_APP_CLIENT_SECRET", "")
GITHUB_APP_OAUTH_CALLBACK_URL = os.getenv("GITHUB_APP_OAUTH_CALLBACK_URL", "")
_raw_private_key = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
# Handle Railway-style escaped newlines AND multiline values
if "\\n" in _raw_private_key:
    _raw_private_key = _raw_private_key.replace("\\n", "\n")
# Strip surrounding quotes that some env systems add
_raw_private_key = _raw_private_key.strip('"').strip("'")
GITHUB_APP_PRIVATE_KEY = _raw_private_key
GITHUB_APP_WEBHOOK_SECRET = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")
GITHUB_APP_WEBHOOK_TARGET_URL = os.getenv("GITHUB_APP_WEBHOOK_TARGET_URL", "")
GITHUB_APP_STATE_SECRET = os.getenv("GITHUB_APP_STATE_SECRET", JWT_SECRET_KEY)
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "false").lower() == "true"
