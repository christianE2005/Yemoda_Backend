import asyncio
import hashlib
import hmac
import json
import logging
import os
import re

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.deps import require_internal_token
from app.models.models import GithubPushEvent, PendingAiReview, TaskWarning
from app.services.agent_service import analyze_push
from app.services import metering
from app.services.github_service import fetch_file_content_at_ref, fetch_push_diff
from app.services.task_service import (
    add_agent_comment,
    all_subtasks_complete,
    build_story_tree,
    create_or_get_push_event,
    create_push_match,
    create_warning,
    filter_task_subtree,
    get_active_tasks,
    get_blocked_parent_ids,
    get_board_review_settings,
    get_latest_push_with_diff,
    get_project,
    get_project_by_repo,
    get_review_column,
    get_subtasks,
    get_task,
    move_task_to_review,
    resolve_warning,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["agent-webhook"])

limiter = Limiter(key_func=get_remote_address)

_WEBHOOK_SECRET = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")
_MAX_CONTEXT_FILES = 8
_MAX_FILE_SNAPSHOT_CHARS = 2500


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "\n... [truncado]"


def _extract_changed_paths(commits: list[dict]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for commit in commits or []:
        for key in ("added", "modified", "removed"):
            for path in commit.get(key) or []:
                if not isinstance(path, str):
                    continue
                normalized = path.strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                ordered.append(normalized)
    return ordered


def _verify_signature(payload: bytes, signature: str) -> bool:
    # Fail closed: with no configured secret we cannot authenticate the webhook, so reject.
    if not _WEBHOOK_SECRET:
        return False
    expected = "sha256=" + hmac.new(
        _WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


# Distinct return states for _analyze_and_apply so callers (especially drain_pending_reviews)
# can tell "review actually ran" from "model failed, keep the queued row for retry".
_REVIEW_DONE = "done"          # review ran (success) — quota consumed
_REVIEW_NO_QUOTA = "no_quota"  # quota exhausted up front — queued or skipped, not consumed
_REVIEW_FAILED = "failed"      # model raised — NOT consumed, do not delete pending


def _active_warnings_by_task(db: Session, task_ids: list[int]) -> dict[int, list[TaskWarning]]:
    """Fetch all active warnings for the given tasks in a single IN-query, keyed by id_task.

    Avoids the N+1 of calling get_active_warnings() once per task.
    """
    result: dict[int, list[TaskWarning]] = {}
    if not task_ids:
        return result
    rows = (
        db.query(TaskWarning)
        .filter(TaskWarning.id_task.in_(task_ids), TaskWarning.status == "active")
        .all()
    )
    for w in rows:
        result.setdefault(w.id_task, []).append(w)
    return result


def _analyze_and_apply(
    db: Session,
    project,
    analyze_tasks: list,
    lookup_tasks: list,
    diff: str,
    code_context: str,
    push_event,
    trigger: str = "push",
    allow_queue: bool = True,
) -> str:
    """Run Claude on the task tree and apply results (move to review, warnings, comment).

    analyze_tasks: tasks sent to the model (nested into a story tree for context).
    lookup_tasks:  tasks for which matches are actually applied. On a push this equals
                   analyze_tasks; on an on-demand parent review it is only the parent,
                   so already-reviewed subtasks are not touched again.

    Returns one of _REVIEW_DONE / _REVIEW_NO_QUOTA / _REVIEW_FAILED.
    """
    # Quota: count this review against the project's monthly allowance. Pre-check only here;
    # the unit is consumed AFTER a successful model call so a failure doesn't burn quota. If
    # exhausted, queue the push for later retry (automatic trigger) or skip (manual trigger).
    period = metering.current_period()
    allowed, used, q = metering.has_quota(db, project.id_project, "reviews", period=period)
    if not allowed:
        will_queue = trigger == "push" and allow_queue and push_event is not None
        logger.info(
            "Review quota reached for project %s (%d/%d) — %s",
            project.id_project, used, q, "queuing push" if will_queue else "skipping",
        )
        if will_queue:
            try:
                db.add(PendingAiReview(id_project=project.id_project, id_push=push_event.id_push, trigger=trigger))
                db.commit()
            except Exception:
                db.rollback()
        return _REVIEW_NO_QUOTA

    stories = build_story_tree(analyze_tasks)

    # Fetch active warnings for all analyzed tasks in one query (avoids per-task N+1), then
    # reuse the map both for the model prompt and for resolving warnings on matched stories.
    warnings_by_task = _active_warnings_by_task(db, [t.id_task for t in analyze_tasks])
    active_warnings_map: dict[int, list[dict]] = {
        task_id: [{"id": w.id_warning, "message": w.message} for w in warns]
        for task_id, warns in warnings_by_task.items()
        if warns
    }

    try:
        coding_style, review_focus, tech_stack, naming_convention, response_language, custom_instructions = get_board_review_settings(db, project.id_project)
        logger.info("Board settings for project %s: style=%s, focus=%s, stack=%s, naming=%s, lang=%s, custom=%s", project.id_project, coding_style, review_focus, tech_stack, naming_convention, response_language, bool(custom_instructions))
        analysis = analyze_push(
            stories,
            diff,
            active_warnings=active_warnings_map,
            coding_style=coding_style,
            review_focus=review_focus,
            tech_stack=tech_stack,
            naming_convention=naming_convention,
            response_language=response_language,
            custom_instructions=custom_instructions,
            code_context=code_context,
        )
        logger.info("Analysis complete for project %s (%s): %d matches", project.id_project, trigger, len(analysis.get("matches", [])))
    except Exception as exc:
        logger.error("Claude analysis failed: %s", exc)
        # Model failed: do NOT consume quota and signal failure so a queued review is kept for retry.
        return _REVIEW_FAILED

    # The model call succeeded — count this review against the project's monthly allowance.
    metering.consume(db, project.id_project, "reviews", period=period)

    review_column = get_review_column(db, project.id_project)
    review_column_id = review_column.id_column if review_column else None

    allowed_ids = {t.id_task for t in lookup_tasks}
    header = "🤖 **Análisis de IA — Revisión de tarea completada**" if trigger == "ondemand" else "🤖 **Análisis de IA — Push detectado**"

    for match in analysis.get("matches", []):
        story_id = match.get("story_id")
        if story_id not in allowed_ids:
            continue
        task = next((t for t in lookup_tasks if t.id_task == story_id), None)
        if not task:
            continue

        if review_column_id:
            move_task_to_review(db, task, review_column_id)

        resolved_ids = match.get("resolved_warning_ids") or []
        task_warns = warnings_by_task.get(story_id, [])
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
        # Safety net: cap the stored snippet to ~40 lines in case the model over-produces.
        if isinstance(code_snippet, str):
            _snippet_lines = code_snippet.splitlines()
            if len(_snippet_lines) > 40:
                code_snippet = "\n".join(_snippet_lines[:40]) + "\n… (truncated)"
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
            header,
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
        logger.info("Story %s moved to Review and comment added (%s).", story_id, trigger)

    return _REVIEW_DONE


def drain_pending_reviews(db: Session, project_id: int, max_items: int = 20) -> int:
    """Re-run queued push reviews for a project while review quota remains.

    Called lazily on the next push (e.g. after the monthly quota reset) and via the
    internal /webhook/drain-pending/ endpoint (e.g. on plan upgrade). Reuses each push's
    stored diff; file snapshots are not re-fetched. Returns how many were drained.
    """
    # The project (and therefore its plan/seat-derived quota) is the same for every queued
    # item, so resolve it once up front instead of per iteration.
    project = get_project(db, project_id)
    if project is None:
        return 0

    pendings = (
        db.query(PendingAiReview)
        .filter(PendingAiReview.id_project == project_id)
        .order_by(PendingAiReview.created_at)
        .limit(max_items)
        .all()
    )
    drained = 0
    for pending in pendings:
        # has_quota re-reads the live usage counter each loop (it grows as we consume), but the
        # plan/seat-based quota ceiling it compares against is fixed for this project.
        ok, _, _ = metering.has_quota(db, project_id, "reviews")
        if not ok:
            break  # no quota left — leave the rest queued
        push = db.query(GithubPushEvent).filter(GithubPushEvent.id_push == pending.id_push).first()
        if push is None or not push.diff_text:
            db.delete(pending)  # stale / unusable — drop it
            db.commit()
            continue
        tasks = get_active_tasks(db, project_id)
        blocked = get_blocked_parent_ids(tasks)
        analyze_tasks = [t for t in tasks if t.id_task not in blocked]
        if not analyze_tasks:
            db.delete(pending)
            db.commit()
            continue
        outcome = _analyze_and_apply(
            db,
            project=project,
            analyze_tasks=analyze_tasks,
            lookup_tasks=analyze_tasks,
            diff=push.diff_text,
            code_context="",
            push_event=push,
            trigger="push",
            allow_queue=False,  # never re-queue while draining
        )
        if outcome == _REVIEW_DONE:
            db.delete(pending)
            db.commit()
            drained += 1
        elif outcome == _REVIEW_NO_QUOTA:
            break  # quota ran out mid-drain — leave this and the rest queued
        else:  # _REVIEW_FAILED — keep the pending row so it can be retried later
            break
    if drained:
        logger.info("Drained %d pending review(s) for project %s", drained, project_id)
    return drained


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
    _review_branches = getattr(project, 'review_branches', '') or ''
    if not is_task_branch and _review_branches.strip():
        allowed = {b.strip() for b in _review_branches.split(",") if b.strip()}
        if branch_name not in allowed:
            logger.info("Branch '%s' not in review_branches (%s) for project %s — skipping", branch_name, _review_branches, project.id_project)
            return

    tasks = get_active_tasks(db, project.id_project)
    if not tasks:
        logger.info("No active tasks for project %s — skipping analysis", project.id_project)
        return

    # Gating: a parent task with unfinished subtasks is NOT reviewed on push — only its
    # subtasks are (each gives its dev feedback). The parent is reviewed once all subtasks
    # are checked, triggered explicitly via the on-demand endpoint below.
    blocked_parent_ids = get_blocked_parent_ids(tasks)

    # Branch-based task routing: if branch matches {task_id}-... only evaluate that task.
    # When the targeted task is a parent, its active subtasks are pulled in too so the
    # agent reviews the whole breakdown together.
    if is_task_branch:
        targeted_id = int(task_id_match.group(1))
        if any(t.id_task == targeted_id for t in tasks):
            tasks = filter_task_subtree(tasks, targeted_id)
            logger.info("Branch '%s' targets task %d — running targeted analysis on %d task(s) (incl. subtasks)", branch_name, targeted_id, len(tasks))

    if blocked_parent_ids:
        before_count = len(tasks)
        tasks = [t for t in tasks if t.id_task not in blocked_parent_ids]
        if len(tasks) != before_count:
            logger.info("Gating: skipped %d parent task(s) pending subtasks for project %s", before_count - len(tasks), project.id_project)
        if not tasks:
            logger.info("Only parents pending subtasks remain for project %s — skipping analysis", project.id_project)
            return

    logger.info("Fetching diff for %s (%s...%s) installation_id=%s", repo_full_name, before[:7], after[:7], installation_id)
    diff = await fetch_push_diff(repo_full_name, before, after, installation_id)
    if not diff:
        logger.warning("Empty diff for %s (%s...%s) — cannot run analysis", repo_full_name, before[:7], after[:7])
        return

    logger.info("Got diff (%d chars) — sending to Claude", len(diff))

    changed_paths = _extract_changed_paths(commits)[:_MAX_CONTEXT_FILES]
    code_context_chunks: list[str] = []
    for path in changed_paths:
        old_content: str | None = None
        new_content: str | None = None

        if before and before != "0" * 40:
            old_content = await fetch_file_content_at_ref(
                repo_full_name=repo_full_name,
                file_path=path,
                ref=before,
                installation_id=installation_id,
            )

        if after and after != "0" * 40:
            new_content = await fetch_file_content_at_ref(
                repo_full_name=repo_full_name,
                file_path=path,
                ref=after,
                installation_id=installation_id,
            )

        if old_content is None and new_content is None:
            continue

        section_lines = [f"### Archivo: {path}"]
        if old_content is not None:
            section_lines.append("#### Antes")
            section_lines.append("```")
            section_lines.append(_truncate_text(old_content, _MAX_FILE_SNAPSHOT_CHARS))
            section_lines.append("```")
        if new_content is not None:
            section_lines.append("#### Después")
            section_lines.append("```")
            section_lines.append(_truncate_text(new_content, _MAX_FILE_SNAPSHOT_CHARS))
            section_lines.append("```")
        code_context_chunks.append("\n".join(section_lines))

    code_context = "\n\n".join(code_context_chunks)

    push_event = create_or_get_push_event(
        db,
        project_id=project.id_project,
        repo_full_name=repo_full_name,
        ref=ref,
        pusher=pusher,
        commits=commits,
        diff_text=diff,
    )

    # Nest subtasks under their parent so the agent sees the task hierarchy, then
    # analyze and apply results. Matches can target any node in `tasks`.
    _analyze_and_apply(
        db,
        project=project,
        analyze_tasks=tasks,
        lookup_tasks=tasks,
        diff=diff,
        code_context=code_context,
        push_event=push_event,
        trigger="push",
    )

    # Drain any reviews that were queued earlier (e.g. now that the monthly quota reset).
    try:
        drain_pending_reviews(db, project.id_project)
    except Exception as exc:
        logger.warning("Pending-review drain failed for project %s: %s", project.id_project, exc)


def _process_push(payload: dict) -> None:
    # IMPORTANT: this is a plain `def`, so Starlette runs it in a threadpool (off the event loop).
    # The push analysis calls the BLOCKING Anthropic SDK + synchronous DB I/O; running it on the
    # main event loop would freeze the entire FastAPI process for the multi-second model call.
    # asyncio.run gives the async file-fetch steps their own loop inside this worker thread.
    db: Session = SessionLocal()
    try:
        asyncio.run(_run_push_analysis(payload, db))
    finally:
        db.close()


def _run_task_review(db: Session, project_id: int, task_id: int) -> None:
    """On-demand review of a parent task once all its subtasks are checked.

    Reuses the project's most recent stored push diff (the dev is reminded to push
    before triggering this). Only the parent task is updated; its subtasks were already
    reviewed individually on their own pushes.
    """
    parent = get_task(db, task_id)
    if not parent or parent.id_project != project_id:
        logger.info("Task review: task %s not found in project %s — skipping", task_id, project_id)
        return

    if not all_subtasks_complete(db, task_id):
        logger.info("Task review: task %s still has incomplete subtasks — skipping", task_id)
        return

    project = get_project(db, project_id)
    if not project:
        logger.info("Task review: project %s not found — skipping", project_id)
        return

    push_event = get_latest_push_with_diff(db, project_id)
    if not push_event or not push_event.diff_text:
        logger.warning("Task review: no stored push diff for project %s — cannot review task %s", project_id, task_id)
        return

    # Parent + its subtasks give the model the full breakdown; only the parent is applied.
    subtasks = get_subtasks(db, task_id)
    analyze_tasks = [parent, *subtasks]

    logger.info("On-demand review of task %s using push %s (%d chars)", task_id, push_event.id_push, len(push_event.diff_text))
    _analyze_and_apply(
        db,
        project=project,
        analyze_tasks=analyze_tasks,
        lookup_tasks=[parent],
        diff=push_event.diff_text,
        code_context="",
        push_event=push_event,
        trigger="ondemand",
    )


def _process_review_task(project_id: int, task_id: int) -> None:
    db: Session = SessionLocal()
    try:
        _run_task_review(db, project_id, task_id)
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

    # Fail closed: reject if the signature is invalid OR the secret is not configured.
    if not _verify_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma de webhook inválida o secret no configurado.",
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


@router.post("/review-task/", dependencies=[Depends(require_internal_token)])
@limiter.limit("60/minute")
async def review_task_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    On-demand review of a parent task once all its subtasks are checked.
    Called server-to-server by the Django API (not by GitHub). Analyzes the parent
    against the project's latest stored push diff and applies the result.
    Auth: the shared internal token (FASTAPI_INTERNAL_TOKEN) via require_internal_token.
    """
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload JSON inválido.")

    project_id = payload.get("project_id")
    task_id = payload.get("task_id")
    if not project_id or not task_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project_id y task_id son requeridos.")

    background_tasks.add_task(_process_review_task, int(project_id), int(task_id))

    return {"detail": "Revisión de tarea encolada. Analizando con IA en segundo plano...", "task_id": int(task_id)}


@router.post("/drain-pending/", dependencies=[Depends(require_internal_token)])
@limiter.limit("30/minute")
async def drain_pending_webhook(
    request: Request,
):
    """Retry queued push reviews. Server-to-server: called by Django on plan upgrade or a
    monthly-reset cron. Optional body {"project_id": N} limits it to one project.
    Auth: the shared internal token (FASTAPI_INTERNAL_TOKEN) via require_internal_token."""
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        payload = {}

    total = 0
    project_ids: list[int] = []
    db: Session = SessionLocal()
    try:
        explicit = payload.get("project_id") if isinstance(payload, dict) else None
        if explicit:
            project_ids = [int(explicit)]
        else:
            project_ids = [row[0] for row in db.query(PendingAiReview.id_project).distinct().all()]
        for pid in project_ids:
            total += drain_pending_reviews(db, pid)
    finally:
        db.close()

    return {"detail": "Drain complete.", "drained": total, "projects": len(project_ids)}

