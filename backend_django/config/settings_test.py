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

# Throttling off in tests: fixtures log in once per test, so the production login rate
# (5/minute, keyed by IP in the shared locmem cache) started returning 429 from the sixth
# test onward. A rate of None disables the throttle while keeping every scope defined
# (ScopedRateThrottle raises ImproperlyConfigured on a missing key).
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {key: None for key in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]},  # noqa: F405
}
