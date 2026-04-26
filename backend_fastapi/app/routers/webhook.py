import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.agent_service import analyze_push, analyze_story
from app.services.ml_service import match_stories
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


async def _run_push_analysis(payload: dict, db: Session) -> None:
    repo_full_name: str = (payload.get("repository") or {}).get("full_name", "")
    before: str = payload.get("before", "")
    after: str = payload.get("after", "")
    ref: str = payload.get("ref", "")
    pusher: str | None = (payload.get("pusher") or {}).get("name")
    commits: list = payload.get("commits") or []
    installation_id: int | None = (payload.get("installation") or {}).get("id")

    logger.info("Push received: repo=%s ref=%s before=%s after=%s installation_id=%s", repo_full_name, ref, before[:7], after[:7], installation_id)

    if not repo_full_name:
        return

    project = get_project_by_repo(db, repo_full_name)
    if not project:
        logger.info("No project found for repo: %s", repo_full_name)
        return

    tasks = get_active_tasks(db, project.id_project)
    if not tasks:
        logger.info("No active tasks for project %s — skipping analysis", project.id_project)
        return

    logger.info("Fetching diff for %s (%s...%s) installation_id=%s", repo_full_name, before[:7], after[:7], installation_id)
    diff = await fetch_push_diff(repo_full_name, before, after, installation_id)
    if not diff:
        logger.warning("Empty diff for %s (%s...%s) — cannot run analysis", repo_full_name, before[:7], after[:7])
        return

    logger.info("Got diff (%d chars)", len(diff))

    # Create or fetch push event record
    push_event = create_or_get_push_event(
        db,
        project_id=project.id_project,
        repo_full_name=repo_full_name,
        ref=ref,
        pusher=pusher,
        commits=commits,
    )

    # Use ML matcher to find candidate stories
    try:
        matches = match_stories(db, repo_full_name, diff, top_k=3, min_sim=0.55)
    except Exception as exc:
        logger.error("ML matching failed: %s", exc)
        matches = []

    # Prepare active warnings map
    active_warnings_map: dict[int, list[dict]] = {}
    for t in tasks:
        warnings = get_active_warnings(db, t.id_task)
        if warnings:
            active_warnings_map[t.id_task] = [
                {"id": w.id_warning, "message": w.message} for w in warnings
            ]

    review_status = get_review_status(db)
    review_status_id = review_status.id_status if review_status else None

    # If no ML matches, fallback to full Claude analysis
    if not matches:
        logger.info("No ML matches found — falling back to full Claude analysis")
        try:
            stories = [
                {"id": t.id_task, "title": t.title, "description": t.description}
                for t in tasks
            ]
            analysis = analyze_push(stories, diff, active_warnings=active_warnings_map)
        except Exception as exc:
            logger.error("Claude analysis failed: %s", exc)
            return

        for match in analysis.get("matches", []):
            story_id = match.get("story_id")
            task = next((t for t in tasks if t.id_task == story_id), None)
            if not task:
                continue

            if review_status_id:
                move_task_to_review(db, task, review_status_id)

            resolved_ids = match.get("resolved_warning_ids") or []
            task_warns = get_active_warnings(db, story_id)
            for w in task_warns:
                if w.id_warning in resolved_ids:
                    resolve_warning(db, w)
                    logger.info("Warning %s resolved for story %s.", w.id_warning, story_id)

            new_warnings = match.get("new_warnings") or []
            for msg in new_warnings:
                create_warning(db, story_id, msg, push_id=push_event.id_push)
                logger.info("New warning created for story %s: %s", story_id, msg)

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

        return

    # Process ML matches — only call Claude per-story when needed
    HIGH_SIM = 0.75
    for m in matches:
        story_id = m.get("story_id")
        similarity = m.get("similarity", 0.0)
        task = next((t for t in tasks if t.id_task == story_id), None)
        if not task:
            continue

        if similarity >= HIGH_SIM:
            # High confidence: mark as full coverage and move to review without warnings
            if review_status_id:
                move_task_to_review(db, task, review_status_id)

            create_push_match(
                db,
                task_id=story_id,
                push_id=push_event.id_push,
                coverage="full",
                reason=f"Matched by ML (similarity={similarity:.2f})",
                code_snippet=None,
            )
            add_agent_comment(
                db,
                story_id,
                "\n".join(
                    [
                        "🤖 **Análisis ML — Push detectado**",
                        "**Cobertura:** ✅ Completa",
                        f"**Confianza ML:** {similarity:.2f}",
                        "No se detectaron warnings automáticos.",
                    ]
                ),
            )
            logger.info("Task %s matched with high confidence (%.2f). Moved to Review.", story_id, similarity)
            continue

        # Zone gray: ask Claude to evaluate this specific story
        try:
            story_obj = {"id": story_id, "title": m.get("title"), "description": m.get("description")}
            awarnings = active_warnings_map.get(story_id, [])
            result = analyze_story(story_obj, diff, active_warnings=awarnings)
        except Exception as exc:
            logger.error("Story analysis failed for %s: %s", story_id, exc)
            continue

        complies = bool(result.get("complies"))
        reason = result.get("reason", "")
        new_warnings = result.get("new_warnings") or []
        resolved_ids = result.get("resolved_warning_ids") or []
        code_snippet = result.get("code_snippet")

        if review_status_id:
            move_task_to_review(db, task, review_status_id)

        for rid in resolved_ids:
            # resolve if exists
            task_warns = get_active_warnings(db, story_id)
            for w in task_warns:
                if w.id_warning == rid:
                    resolve_warning(db, w)
                    logger.info("Warning %s resolved for story %s.", rid, story_id)

        for msg in new_warnings:
            create_warning(db, story_id, msg, push_id=push_event.id_push)
            logger.info("New warning created for story %s: %s", story_id, msg)

        coverage_label = "✅ Completa" if complies else "⚠️ Parcial"
        create_push_match(
            db,
            task_id=story_id,
            push_id=push_event.id_push,
            coverage="full" if complies else "partial",
            reason=reason,
            code_snippet=code_snippet,
        )

        lines = [
            "🤖 **Análisis ML + LLM — Push detectado**",
            f"**Cobertura estimada:** {coverage_label}",
            f"**Confianza ML:** {similarity:.2f}",
            f"**Razón:** {reason}",
        ]
        if resolved_ids:
            lines.append(f"\n✅ **Warnings resueltos:** {len(resolved_ids)}")
        if new_warnings:
            lines.append("\n⚠️ **Nuevos warnings:**")
            lines.extend(f"- {w}" for w in new_warnings)

        add_agent_comment(db, story_id, "\n".join(lines))
        logger.info("Story %s processed (similarity=%.2f). Moved to Review and comment added.", story_id, similarity)


async def _process_push(payload: dict) -> None:
    db: Session = SessionLocal()
    try:
        await _run_push_analysis(payload, db)
    finally:
        db.close()


@router.post("/push/")
async def github_push_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    """
    Receives GitHub push webhooks, analyzes code changes with Claude AI,
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

    background_tasks.add_task(_process_push, payload)

    return {
        "detail": "Push recibido. Analizando con IA en segundo plano...",
        "repository": (payload.get("repository") or {}).get("full_name"),
        "ref": payload.get("ref"),
    }

