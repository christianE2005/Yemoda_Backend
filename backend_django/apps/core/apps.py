from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        # Ensure drf-spectacular extension classes are imported and registered.
        from . import schema  # noqa: F401
