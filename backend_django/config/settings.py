from pathlib import Path
import os
from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent.parent
env = dotenv_values(BASE_DIR / ".env")

SECRET_KEY = env.get("DJANGO_SECRET_KEY", "change-me")
DEBUG = env.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in env.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()]

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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in env.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if origin.strip()
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.get("DB_NAME", "app_db"),
        "USER": env.get("DB_USER", "postgres"),
        "PASSWORD": env.get("DB_PASSWORD", "postgres"),
        "HOST": env.get("DB_HOST", "localhost"),
        "PORT": env.get("DB_PORT", "5432"),
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ABCDH Backend API",
    "DESCRIPTION": "API base con Django REST Framework",
    "VERSION": "1.0.0",
}

JWT_SECRET_KEY = env.get("JWT_SECRET_KEY", SECRET_KEY)
JWT_ALGORITHM = env.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(env.get("JWT_EXPIRE_MINUTES", "60"))
JWT_REFRESH_EXPIRE_MINUTES = int(env.get("JWT_REFRESH_EXPIRE_MINUTES", "10080"))

GITHUB_APP_ID = env.get("GITHUB_APP_ID", "")
GITHUB_APP_SLUG = env.get("GITHUB_APP_SLUG", "")
GITHUB_APP_CLIENT_ID = env.get("GITHUB_APP_CLIENT_ID", "")
GITHUB_APP_CLIENT_SECRET = env.get("GITHUB_APP_CLIENT_SECRET", "")
GITHUB_APP_OAUTH_CALLBACK_URL = env.get("GITHUB_APP_OAUTH_CALLBACK_URL", "")
GITHUB_APP_PRIVATE_KEY = env.get("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")
GITHUB_APP_WEBHOOK_SECRET = env.get("GITHUB_APP_WEBHOOK_SECRET", "")
GITHUB_APP_WEBHOOK_TARGET_URL = env.get("GITHUB_APP_WEBHOOK_TARGET_URL", "")
