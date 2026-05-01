import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.agent_service import analyze_story
from app.services.github_service import fetch_push_diff, post_commit_comment
from app.services.ml_service import ML_EMBED_MODEL, ML_MIN_SIM, match_stories
from app.services.task_service import (
    add_agent_comment,
    create_or_get_push_event,
    create_push_match,
    create_warning,
    get_active_warnings,
    get_branch_link,
    get_project_by_repo,
    get_review_status,
    get_task_by_id,
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


# ── Shared LLM evaluation helper ─────────────────────────────────────────────

async def _evaluate_story_with_llm(
    db: Session,
    task,
    diff: str,
    push_event,
    review_status_id: int | None,
    similarity: float | None,
    installation_id: int | None,
    repo_full_name: str,
    head_commit_sha: str,
) -> None:
    """Run the LLM acceptance-criteria check for *task* against *diff*.

    Handles warning resolution/creation, push-match persistence, task-status
    promotion, and human-readable comments (DB + GitHub commit comment).

    *similarity* is ``None`` for Path A (known branch) and a float for Path B
    (ML-discovered story).
    """
    active_warnings = get_active_warnings(db, task.id_task)
    warnings_list = [{"id": w.id_warning, "message": w.message} for w in active_warnings]

    story = {"id": task.id_task, "title": task.title, "description": task.description}
    result = analyze_story(story, diff, active_warnings=warnings_list)

    complies: bool = bool(result.get("complies"))
    reason: str = result.get("reason", "")
    new_warnings: list = result.get("new_warnings") or []
    resolved_ids: list = result.get("resolved_warning_ids") or []
    code_snippet: str | None = result.get("code_snippet")

    # Resolve existing warnings flagged by the LLM
    for rid in resolved_ids:
        for w in active_warnings:
            if w.id_warning == rid:
                resolve_warning(db, w)
                logger.info("Warning %s resolved for story %s", rid, task.id_task)

    # Create new warnings flagged by the LLM
    for msg in new_warnings:
        create_warning(db, task.id_task, msg, push_id=push_event.id_push)
        logger.info("New warning for story %s: %s", task.id_task, msg)

    model_label = f"ml+llm:{ML_EMBED_MODEL}" if similarity is not None else "llm-direct"
    create_push_match(
        db,
        task_id=task.id_task,
        push_id=push_event.id_push,
        coverage="full" if complies else "partial",
        reason=reason,
        code_snippet=code_snippet,
        similarity=similarity,
        model_name=model_label,
    )

    # Build board comment
    if complies:
        if review_status_id:
            move_task_to_review(db, task, review_status_id)
        lines = [
            "🤖 **Análisis IA — Criterios de aceptación cumplidos**",
            "**Cobertura:** ✅ Completa",
            f"**Razón:** {reason}",
        ]
        if similarity is not None:
            lines.insert(1, f"**Confianza ML:** {similarity:.2f}")
        if resolved_ids:
            lines.append(f"\n✅ **Warnings resueltos:** {len(resolved_ids)}")
    else:
        lines = [
            "🤖 **Análisis IA — Criterios de aceptación incompletos**",
            "**Cobertura:** ⚠️ Parcial",
            f"**Razón:** {reason}",
        ]
        if similarity is not None:
            lines.insert(1, f"**Confianza ML:** {similarity:.2f}")
        if new_warnings:
            lines.append("\n⚠️ **Lo que falta:**")
            lines.extend(f"- {w}" for w in new_warnings)

        # Notify the developer directly on the GitHub commit
        commit_lines = [
            f"⚠️ **Story #{task.id_task} — Criterios de aceptación incompletos**",
            f"**Razón:** {reason}",
        ]
        if new_warnings:
            commit_lines.append("**Lo que falta:**")
            commit_lines.extend(f"- {w}" for w in new_warnings)

        await post_commit_comment(
            repo_full_name, head_commit_sha, "\n".join(commit_lines), installation_id
        )

    add_agent_comment(db, task.id_task, "\n".join(lines))
    logger.info(
        "Story %s processed (complies=%s, similarity=%s)",
        task.id_task, complies, similarity,
    )


# ── Main push-analysis logic ──────────────────────────────────────────────────

async def _run_push_analysis(payload: dict, db: Session) -> None:
    repo_full_name: str = (payload.get("repository") or {}).get("full_name", "")
    before: str = payload.get("before", "")
    after: str = payload.get("after", "")
    ref: str = payload.get("ref", "")
    pusher: str | None = (payload.get("pusher") or {}).get("name")
    commits: list = payload.get("commits") or []
    installation_id: int | None = (payload.get("installation") or {}).get("id")
    head_commit_sha: str = after  # SHA of the latest commit in this push

    if not repo_full_name:
        return

    # Extract branch name from ref (e.g. "refs/heads/feature/story-42" → "feature/story-42")
    branch_name = ref.removeprefix("refs/heads/")

    logger.info(
        "Push received: repo=%s branch=%s before=%s after=%s",
        repo_full_name, branch_name, before[:7], after[:7],
    )

    project = get_project_by_repo(db, repo_full_name)
    if not project:
        logger.info("No project found for repo: %s", repo_full_name)
        return

    # Fetch diff — needed in both paths
    diff = await fetch_push_diff(repo_full_name, before, after, installation_id)
    if not diff:
        logger.warning("Empty diff for %s (%s...%s)", repo_full_name, before[:7], after[:7])
        return

    logger.info("Got diff (%d chars)", len(diff))

    push_event = create_or_get_push_event(
        db,
        project_id=project.id_project,
        repo_full_name=repo_full_name,
        ref=ref,
        pusher=pusher,
        commits=commits,
    )

    review_status = get_review_status(db)
    review_status_id = review_status.id_status if review_status else None

    # ── Dispatch: known branch vs. unknown branch ─────────────────────────────
    branch_link = get_branch_link(db, repo_full_name, branch_name)

    if branch_link:
        # ── PATH A: Known branch — skip ML entirely ───────────────────────────
        logger.info(
            "Known branch '%s' linked to story %s — sending directly to LLM",
            branch_name, branch_link.id_task,
        )
        task = get_task_by_id(db, branch_link.id_task)
        if not task:
            logger.warning("Branch link points to missing task %s", branch_link.id_task)
            return

        try:
            await _evaluate_story_with_llm(
                db, task, diff, push_event, review_status_id,
                similarity=None,
                installation_id=installation_id,
                repo_full_name=repo_full_name,
                head_commit_sha=head_commit_sha,
            )
        except Exception as exc:
            logger.error("LLM evaluation failed for story %s: %s", branch_link.id_task, exc)

    else:
        # ── PATH B: Unknown branch — run ML to identify the story ─────────────
        logger.info("Unknown branch '%s' — running ML to find related story", branch_name)

        try:
            matches = match_stories(db, repo_full_name, diff, top_k=1, min_sim=None)
        except Exception as exc:
            logger.error("ML matching failed: %s", exc)
            return

        top_match = matches[0] if matches else None
        similarity = float(top_match.get("similarity", 0.0)) if top_match else 0.0

        if not top_match or similarity < ML_MIN_SIM:
            # ML not confident enough — notify developer, do NOT call LLM
            logger.info(
                "ML top similarity %.2f below threshold %.2f — notifying developer on branch '%s'",
                similarity, ML_MIN_SIM, branch_name,
            )
            message = (
                f"🔍 **No se encontró una historia relacionada con la rama `{branch_name}`**\n\n"
                f"El análisis ML no encontró una historia de usuario con suficiente confianza "
                f"(similitud más alta: **{similarity:.2f}**, umbral mínimo: **{ML_MIN_SIM}**).\n\n"
                "**Acción requerida:** Vincula esta rama a una historia existente usando "
                "`POST /branches/create` o crea una nueva historia en el tablero."
            )
            await post_commit_comment(repo_full_name, head_commit_sha, message, installation_id)
            logger.info("Developer notified (no confident ML match) for branch '%s'", branch_name)
            return

        story_id = top_match.get("story_id")
        task = get_task_by_id(db, story_id)
        if not task:
            logger.warning("ML matched task %s not found in active tasks list", story_id)
            return

        logger.info(
            "ML matched story %s with similarity %.2f — sending to LLM for evaluation",
            story_id, similarity,
        )

        try:
            await _evaluate_story_with_llm(
                db, task, diff, push_event, review_status_id,
                similarity=similarity,
                installation_id=installation_id,
                repo_full_name=repo_full_name,
                head_commit_sha=head_commit_sha,
            )
        except Exception as exc:
            logger.error("LLM evaluation failed for ML-matched story %s: %s", story_id, exc)


async def _process_push(payload: dict) -> None:
    db: Session = SessionLocal()
    try:
        await _run_push_analysis(payload, db)
    finally:
        db.close()


# ── FastAPI endpoint ──────────────────────────────────────────────────────────

@router.post("/push/")
async def github_push_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    """Receives GitHub push webhooks and routes them through the ML + LLM analysis pipeline."""
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload JSON inválido.",
        )

    background_tasks.add_task(_process_push, payload)

    return {
        "detail": "Push recibido. Analizando en segundo plano...",
        "repository": (payload.get("repository") or {}).get("full_name"),
        "ref": payload.get("ref"),
    }
