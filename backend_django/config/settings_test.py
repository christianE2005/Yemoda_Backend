from config.settings import *  # noqa: F401, F403

# Tests run with DEBUG and the Django test host explicitly allowed (production settings
# default to DEBUG=False with a restricted ALLOWED_HOSTS).
DEBUG = True
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
