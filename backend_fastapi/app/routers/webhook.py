import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.services.agent_service import analyze_push
from app.services.github_service import fetch_push_diff
from app.services.task_service import (
    add_agent_comment,
    create_or_get_push_event,
    create_push_match,
    create_warning,
    get_active_tasks,
    get_active_warnings,
    get_project_by_repo,
    get_review_status,
    move_task_to_review,
    resolve_warning,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["agent-webhook"])

_WEBHOOK_SECRET = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")


def _verify_signature(payload: bytes, signature: str) -> bool:
    if not _WEBHOOK_SECRET:
        return True
    expected = "sha256=" + hmac.new(
        _WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


async def _process_push(payload: dict, db: Session) -> None:
    repo_full_name: str = (payload.get("repository") or {}).get("full_name", "")
    before: str = payload.get("before", "")
    after: str = payload.get("after", "")
    ref: str = payload.get("ref", "")
    pusher: str | None = (payload.get("pusher") or {}).get("name")
    commits: list = payload.get("commits") or []
    installation_id: int | None = (payload.get("installation") or {}).get("id")

    if not repo_full_name:
        return

    project = get_project_by_repo(db, repo_full_name)
    if not project:
        logger.info("No project found for repo: %s", repo_full_name)
        return

    tasks = get_active_tasks(db, project.id_project)
    if not tasks:
        logger.info("No active tasks for project %s", project.id_project)
        return

    diff = await fetch_push_diff(repo_full_name, before, after, installation_id)
    if not diff:
        logger.warning("Could not fetch diff for %s (%s...%s)", repo_full_name, before[:7], after[:7])
        return

    # Create a push event record so we can link matches to it
    push_event = create_or_get_push_event(
        db,
        project_id=project.id_project,
        repo_full_name=repo_full_name,
        ref=ref,
        pusher=pusher,
        commits=commits,
    )

    stories = [
        {"id": t.id_task, "title": t.title, "description": t.description}
        for t in tasks
    ]

    # Gather active warnings per task to pass to Gemini
    active_warnings_map: dict[int, list[dict]] = {}
    for t in tasks:
        warnings = get_active_warnings(db, t.id_task)
        if warnings:
            active_warnings_map[t.id_task] = [
                {"id": w.id_warning, "message": w.message} for w in warnings
            ]

    try:
        analysis = analyze_push(stories, diff, active_warnings=active_warnings_map)
    except Exception as exc:
        logger.error("Gemini analysis failed: %s", exc)
        return

    review_status = get_review_status(db)
    review_status_id = review_status.id_status if review_status else None

    for match in analysis.get("matches", []):
        story_id = match.get("story_id")
        task = next((t for t in tasks if t.id_task == story_id), None)
        if not task:
            continue

        if review_status_id:
            move_task_to_review(db, task, review_status_id)

        # Resolve warnings that Gemini says are fixed
        resolved_ids = match.get("resolved_warning_ids") or []
        task_warns = get_active_warnings(db, story_id)
        for w in task_warns:
            if w.id_warning in resolved_ids:
                resolve_warning(db, w)
                logger.info("Warning %s resolved for story %s.", w.id_warning, story_id)

        # Create new warnings linked to this push
        new_warnings = match.get("new_warnings") or []
        for msg in new_warnings:
            create_warning(db, story_id, msg, push_id=push_event.id_push)
            logger.info("New warning created for story %s: %s", story_id, msg)

        # Save the push<->task match with code snippet
        coverage = match.get("coverage", "partial")
        code_snippet = match.get("code_snippet")
        create_push_match(
            db,
            task_id=story_id,
            push_id=push_event.id_push,
            coverage=coverage,
            reason=match.get("reason"),
            code_snippet=code_snippet,
        )
        logger.info("TaskPushMatch saved for story %s (push %s).", story_id, push_event.id_push)

        # Build comment
        coverage_label = "✅ Completa" if coverage == "full" else "⚠️ Parcial"
        lines = [
            "🤖 **Análisis de IA — Push detectado**",
            f"**Cobertura:** {coverage_label}",
            f"**Razón:** {match.get('reason', '')}",
        ]
        if resolved_ids:
            lines.append(f"\n✅ **Warnings resueltos:** {len(resolved_ids)}")
        if new_warnings:
            lines.append("\n⚠️ **Nuevos warnings:**")
            lines.extend(f"- {w}" for w in new_warnings)

        add_agent_comment(db, story_id, "\n".join(lines))
        logger.info("Story %s moved to Review and comment added.", story_id)


@router.post("/push/")
async def github_push_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    """
    Receives GitHub push webhooks, analyzes code changes with Gemini AI,
    and updates the matching user stories (moves to Review + adds comment).
    """
    payload_bytes = await request.body()

    if _WEBHOOK_SECRET and not _verify_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma de webhook inválida.",
        )

    if x_github_event != "push":
        return {"detail": f"Evento ignorado: {x_github_event}"}

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload JSON inválido.")

    background_tasks.add_task(_process_push, payload, db)

    return {
        "detail": "Push recibido. Analizando con IA en segundo plano...",
        "repository": (payload.get("repository") or {}).get("full_name"),
        "ref": payload.get("ref"),
    }
