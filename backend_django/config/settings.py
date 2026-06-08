from pathlib import Path
from urllib.parse import unquote, urlparse
import os
import secrets
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Never fall back to a publicly-known signing key. If DJANGO_SECRET_KEY is unset we use a
# per-process random key (forces it to be configured in production; never the old "change-me").
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or secrets.token_urlsafe(50)
# Default to production-safe (DEBUG off). Set DJANGO_DEBUG=true only in local development.
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
# Never default to a wildcard host outside DEBUG — configure DJANGO_ALLOWED_HOSTS in production.
_allowed_hosts_raw = os.getenv("DJANGO_ALLOWED_HOSTS", "*" if DEBUG else "localhost,127.0.0.1")
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
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Global defaults
        "anon": "30/minute",
        "user": "300/minute",
        # Scoped rates for specific endpoints
        "login": "5/minute",
        "register": "5/minute",
        "token_refresh": "10/minute",
        "change_password": "5/hour",
        "github_webhook": "120/minute",
        "github_oauth": "10/minute",
        "github_repo_create": "10/minute",
        "github_repo_contents": "60/minute",
        "resend_verification": "3/hour",
        # Slows mass user/email enumeration via the member-picker search.
        "user_search": "20/minute",
        # Resource creation limits
        "sprint_create": "20/hour",
        "milestone_create": "20/hour",
        "task_create": "60/hour",
        "board_create": "10/hour",
    },
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
# Normalize the private key regardless of how Railway stores it:
# 1. Replace literal \n (escaped) with real newlines
if "\\n" in _raw_private_key:
    _raw_private_key = _raw_private_key.replace("\\n", "\n")
# 2. Strip surrounding quotes that some env systems add
_raw_private_key = _raw_private_key.strip('"').strip("'").strip()
# 3. Normalize Windows line endings and remove carriage returns
_raw_private_key = _raw_private_key.replace("\r\n", "\n").replace("\r", "\n")
# 4. Rebuild PEM: strip each line and re-join to remove stray spaces/tabs
if "BEGIN" in _raw_private_key:
    _lines = [line.strip() for line in _raw_private_key.splitlines()]
    _lines = [line for line in _lines if line]  # remove blank lines
    _raw_private_key = "\n".join(_lines) + "\n"
GITHUB_APP_PRIVATE_KEY = _raw_private_key
GITHUB_APP_WEBHOOK_SECRET = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")
GITHUB_APP_WEBHOOK_TARGET_URL = os.getenv("GITHUB_APP_WEBHOOK_TARGET_URL", "")
# Dedicated server-to-server token Django presents to the FastAPI service (X-Internal-Token).
# Falls back to the GitHub App webhook secret for backwards compatibility if unset.
FASTAPI_INTERNAL_TOKEN = os.getenv("FASTAPI_INTERNAL_TOKEN") or os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")
GITHUB_APP_STATE_SECRET = os.getenv("GITHUB_APP_STATE_SECRET", JWT_SECRET_KEY)
FASTAPI_CHAT_BASE_URL = os.getenv("FASTAPI_CHAT_BASE_URL", "https://fast.yemoda.site")
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "false").lower() == "true"
# The refresh token is delivered as an HttpOnly cookie, so the browser must be allowed to
# send credentials cross-origin. This REQUIRES explicit CORS_ALLOWED_ORIGINS (never combine
# credentials with CORS_ALLOW_ALL_ORIGINS / a "*" origin — browsers reject that).
CORS_ALLOW_CREDENTIALS = True

# ── Refresh-token cookie (HttpOnly) ──────────────────────────────────────────
# The refresh token lives in an HttpOnly cookie (not readable by JS) instead of being handed
# to the SPA for localStorage. Defaults fit a same-site subdomain deploy (frontend yemoda.site
# + backend api.yemoda.site → SameSite=Lax suffices). If the frontend ever lives on a different
# registrable domain (e.g. *.vercel.app), set REFRESH_COOKIE_SAMESITE=None (Secure must then be
# true) so the cookie is sent on cross-site requests.
REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "yemoda_refresh")
REFRESH_COOKIE_SECURE = os.getenv("REFRESH_COOKIE_SECURE", "true").lower() == "true"
REFRESH_COOKIE_SAMESITE = os.getenv("REFRESH_COOKIE_SAMESITE", "Lax")  # "Lax" | "Strict" | "None"
REFRESH_COOKIE_DOMAIN = os.getenv("REFRESH_COOKIE_DOMAIN", "").strip() or None  # e.g. ".yemoda.site"; empty = host-only
REFRESH_COOKIE_PATH = os.getenv("REFRESH_COOKIE_PATH", "/api/auth/")

# ── AI usage quotas (metering) ───────────────────────────────────────────────
# Per-seat monthly allowance, pooled across a project's members (seats). Must match the
# values set on the FastAPI service (it enforces; Django only reports usage). When enforcement
# is on and a project exhausts a category, chat/AI-fix calls are blocked (402) and push
# reviews are queued for retry.
# Pro plan: per-seat allowance, pooled across the project's members.
AI_QUOTA_REVIEWS_PER_SEAT = int(os.getenv("AI_QUOTA_REVIEWS_PER_SEAT", "50"))
AI_QUOTA_AIFIX_PER_SEAT = int(os.getenv("AI_QUOTA_AIFIX_PER_SEAT", "10"))
AI_QUOTA_CHAT_PER_SEAT = int(os.getenv("AI_QUOTA_CHAT_PER_SEAT", "50"))
# Free plan: a flat cap for the whole project (NOT multiplied by members).
AI_FREE_QUOTA_REVIEWS = int(os.getenv("AI_FREE_QUOTA_REVIEWS", "10"))
AI_FREE_QUOTA_AIFIX = int(os.getenv("AI_FREE_QUOTA_AIFIX", "1"))
AI_FREE_QUOTA_CHAT = int(os.getenv("AI_FREE_QUOTA_CHAT", "10"))
AI_METERING_ENFORCE = os.getenv("AI_METERING_ENFORCE", "true").lower() == "true"

# Hackathon pricing: charged per team. Batch mode applies a discount multiplier
# (cheaper async Anthropic Message Batches). See serializers/views for the price formula.
HACKATHON_PRICE_PER_TEAM = float(os.getenv("HACKATHON_PRICE_PER_TEAM", "1.50"))   # charge per team, normal mode
HACKATHON_BATCH_DISCOUNT = float(os.getenv("HACKATHON_BATCH_DISCOUNT", "0.5"))    # batch multiplier (-> $0.75/team)
HACKATHON_VERIFY_MULTIPLIER = float(os.getenv("HACKATHON_VERIFY_MULTIPLIER", "1.5"))  # high-fidelity (re-judge) surcharge

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_MONTHLY = os.getenv("STRIPE_PRICE_ID_MONTHLY", "")  # per-seat monthly price ($12/seat)
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "https://yemoda.site/payment/success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "https://yemoda.site/payment/cancel")

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")
GOOGLE_AUTH_FRONTEND_REDIRECT = os.getenv("GOOGLE_AUTH_FRONTEND_REDIRECT", "https://yemoda.site/auth/google/callback")
GITHUB_AUTH_FRONTEND_REDIRECT = os.getenv("GITHUB_AUTH_FRONTEND_REDIRECT", "https://yemoda.site/auth/github/callback")
GOOGLE_STATE_SECRET = os.getenv("GOOGLE_STATE_SECRET", JWT_SECRET_KEY)

# Resend (email)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "noreply@yemoda.site")
# Full backend URL prefix for the verification link in emails
# For scanner-proof verification: point this to the FRONTEND page that shows a "Verify" button,
# which then POSTs to /api/auth/verify-email/. The default backend GET flow is kept for compatibility.
EMAIL_VERIFICATION_BASE_URL = os.getenv("EMAIL_VERIFICATION_BASE_URL", "https://yemoda.site/auth/verify-email")
# Frontend page to redirect to after verification (success or error)
EMAIL_VERIFIED_REDIRECT = os.getenv("EMAIL_VERIFIED_REDIRECT", "https://yemoda.site/auth/verified")

# ---- Security headers ----
# Always-on: prevents MIME sniffing and clickjacking
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

if not DEBUG:
    # HSTS: tell browsers to always use HTTPS for 1 year
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
