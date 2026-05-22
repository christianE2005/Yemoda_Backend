import hashlib
import hmac
import json
import logging
import os
import re

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.agent_service import analyze_push
from app.services.github_service import fetch_push_diff
from app.services.task_service import (
    add_agent_comment,
    create_or_get_push_event,
    create_push_match,
    create_warning,
    get_active_tasks,
    get_active_warnings,
    get_board_review_settings,
    get_project_by_repo,
    get_review_column,
    move_task_to_review,
    resolve_warning,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["agent-webhook"])

limiter = Limiter(key_func=get_remote_address)

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

    # Determine if this is a task-targeted branch ({task_id}-slug or {task_id})
    branch_name = ref.replace("refs/heads/", "").replace("refs/tags/", "")
    task_id_match = re.match(r"^(\d+)(?:-|$)", branch_name)
    is_task_branch = bool(task_id_match)

    # review_branches filter: only applied to non-task branches
    if not is_task_branch and project.review_branches and project.review_branches.strip():
        allowed = {b.strip() for b in project.review_branches.split(",") if b.strip()}
        if branch_name not in allowed:
            logger.info("Branch '%s' not in review_branches (%s) for project %s — skipping", branch_name, project.review_branches, project.id_project)
            return

    tasks = get_active_tasks(db, project.id_project)
    if not tasks:
        logger.info("No active tasks for project %s — skipping analysis", project.id_project)
        return

    # Branch-based task routing: if branch matches {task_id}-... only evaluate that task
    if is_task_branch:
        targeted_id = int(task_id_match.group(1))
        targeted = [t for t in tasks if t.id_task == targeted_id]
        if targeted:
            tasks = targeted
            logger.info("Branch '%s' targets task %d — running targeted single-task analysis", branch_name, targeted_id)

    logger.info("Fetching diff for %s (%s...%s) installation_id=%s", repo_full_name, before[:7], after[:7], installation_id)
    diff = await fetch_push_diff(repo_full_name, before, after, installation_id)
    if not diff:
        logger.warning("Empty diff for %s (%s...%s) — cannot run analysis", repo_full_name, before[:7], after[:7])
        return

    logger.info("Got diff (%d chars) — sending to Claude", len(diff))

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

    active_warnings_map: dict[int, list[dict]] = {}
    for t in tasks:
        warnings = get_active_warnings(db, t.id_task)
        if warnings:
            active_warnings_map[t.id_task] = [
                {"id": w.id_warning, "message": w.message} for w in warnings
            ]

    try:
        coding_style, review_focus, tech_stack, naming_convention, response_language, custom_instructions = get_board_review_settings(db, project.id_project)
        analysis = analyze_push(stories, diff, active_warnings=active_warnings_map, coding_style=coding_style, review_focus=review_focus, tech_stack=tech_stack, naming_convention=naming_convention, response_language=response_language, custom_instructions=custom_instructions)
        logger.info("Analysis complete for project %s (style=%s, focus=%s, stack=%s, naming=%s, lang=%s, custom=%s): %d matches", project.id_project, coding_style, review_focus, tech_stack, naming_convention, response_language, bool(custom_instructions), len(analysis.get("matches", [])))
    except Exception as exc:
        logger.error("Claude analysis failed: %s", exc)
        return

    review_column = get_review_column(db, project.id_project)
    review_column_id = review_column.id_column if review_column else None

    for match in analysis.get("matches", []):
        story_id = match.get("story_id")
        task = next((t for t in tasks if t.id_task == story_id), None)
        if not task:
            continue

        if review_column_id:
            move_task_to_review(db, task, review_column_id)

        resolved_ids = match.get("resolved_warning_ids") or []
        task_warns = get_active_warnings(db, story_id)
        for w in task_warns:
            if w.id_warning in resolved_ids:
                resolve_warning(db, w)
                logger.info("Warning %s resolved for story %s.", w.id_warning, story_id)

        new_warnings = match.get("new_warnings") or []
        for w in new_warnings:
            if isinstance(w, dict):
                msg = w.get("message", "")
                sev = w.get("severity", "warning")
                if sev not in ("critical", "warning", "info"):
                    sev = "warning"
            else:
                msg = str(w)
                sev = "warning"
            if msg:
                create_warning(db, story_id, msg, push_id=push_event.id_push, severity=sev)
                logger.info("New warning created for story %s [%s]: %s", story_id, sev, msg)

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

        coverage_label = "Completa" if coverage == "full" else "Parcial"
        lines = [
            "🤖 **Análisis de IA — Push detectado**",
            f"**Cobertura:** {coverage_label}",
            f"**Razón:** {match.get('reason', '')}",
        ]
        if resolved_ids:
            lines.append(f"\n**Warnings resueltos:** {len(resolved_ids)}")
        if new_warnings:
            lines.append("\n**Nuevos warnings:**")
            for w in new_warnings:
                if isinstance(w, dict):
                    badge = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(w.get("severity", "warning"), "🟡")
                    lines.append(f"- {badge} {w.get('message', '')}")
                else:
                    lines.append(f"- 🟡 {w}")

        add_agent_comment(db, story_id, "\n".join(lines))
        logger.info("Story %s moved to Review and comment added.", story_id)


async def _process_push(payload: dict) -> None:
    db: Session = SessionLocal()
    try:
        await _run_push_analysis(payload, db)
    finally:
        db.close()


@router.post("/push/")
@limiter.limit("120/minute")
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

