import logging
import os
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Task

logger = logging.getLogger(__name__)

# URL for internal FastAPI invalidation endpoint. Configure via env var in production
FASTAPI_INTERNAL_URL = os.getenv("FASTAPI_INTERNAL_URL", "http://localhost:8001").rstrip("/")


def _call_fastapi_invalidate(story_id: int) -> None:
    """Call the FastAPI internal endpoint to invalidate a single story embedding."""
    url = f"{FASTAPI_INTERNAL_URL}/ml/cache/invalidate/{story_id}"
    try:
        import requests

        resp = requests.post(url, timeout=2)
        if resp.status_code >= 400:
            logger.warning("FastAPI invalidate returned %s: %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Could not invalidate FastAPI cache for task %s via HTTP: %s", story_id, exc)


def _get_invalidate_fn_direct():
    """Try to import the invalidate function directly (works if Django and FastAPI share a process)."""
    try:
        from app.services.ml_service import invalidate_story_embedding

        return invalidate_story_embedding
    except Exception:
        logger.debug("Direct import from 'app.services.ml_service' failed, trying backup path")

    try:
        from backend_fastapi.app.services.ml_service import invalidate_story_embedding

        return invalidate_story_embedding
    except Exception:
        logger.info("invalidate_story_embedding not importable; will use HTTP fallback if configured")
        return None


@receiver(post_save, sender=Task)
def task_post_save(sender, instance: Task, **kwargs):
    fn = _get_invalidate_fn_direct()
    if fn:
        try:
            fn(instance.id_task)
            logger.debug("invalidate_story_embedding called for task id %s (post_save direct)", instance.id_task)
            return
        except Exception as exc:
            logger.warning("Direct invalidate failed for task %s: %s", instance.id_task, exc)

    # Fallback to HTTP call so multi-process setups are handled
    _call_fastapi_invalidate(instance.id_task)


@receiver(post_delete, sender=Task)
def task_post_delete(sender, instance: Task, **kwargs):
    fn = _get_invalidate_fn_direct()
    if fn:
        try:
            fn(instance.id_task)
            logger.debug("invalidate_story_embedding called for task id %s (post_delete direct)", instance.id_task)
            return
        except Exception as exc:
            logger.warning("Direct invalidate failed for task %s: %s", instance.id_task, exc)

    # Fallback to HTTP call so multi-process setups are handled
    _call_fastapi_invalidate(instance.id_task)
