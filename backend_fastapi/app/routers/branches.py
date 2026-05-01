import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.github_service import create_github_branch
from app.services.task_service import create_branch_link, get_branch_link, get_task_by_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/branches", tags=["branches"])


class CreateBranchRequest(BaseModel):
    repo_full_name: str
    branch_name: str
    story_id: int
    base_branch: str = "main"


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_branch_endpoint(
    payload: CreateBranchRequest,
    db: Session = Depends(get_db),
):
    """Create a GitHub branch and link it to a user story.

    - Verifies the story exists in the DB.
    - Rejects duplicate links for the same branch.
    - Creates the branch on GitHub via the App installation token.
    - Persists the branch → story mapping so the webhook can skip ML later.
    """
    # Verify the target story exists
    task = get_task_by_id(db, payload.story_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story {payload.story_id} not found.",
        )

    # Reject if branch is already linked to a story
    existing = get_branch_link(db, payload.repo_full_name, payload.branch_name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Branch '{payload.branch_name}' is already linked to story {existing.id_task}."
            ),
        )

    # Create the branch on GitHub
    try:
        github_result = await create_github_branch(
            repo_full_name=payload.repo_full_name,
            branch_name=payload.branch_name,
            base_branch=payload.base_branch,
        )
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        # 422 from GitHub usually means the branch already exists remotely
        detail = (
            f"Branch '{payload.branch_name}' already exists on GitHub."
            if status_code == 422
            else f"GitHub API error {status_code}: {exc.response.text}"
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    except Exception as exc:
        logger.exception("Unexpected error creating branch on GitHub: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {exc}",
        )

    # Persist the branch → story link
    link = create_branch_link(db, payload.repo_full_name, payload.branch_name, payload.story_id)

    logger.info(
        "Branch '%s' created on %s and linked to story %s",
        payload.branch_name, payload.repo_full_name, payload.story_id,
    )

    return {
        "branch": payload.branch_name,
        "story_id": payload.story_id,
        "repo": payload.repo_full_name,
        "base_branch": payload.base_branch,
        "github_ref": github_result.get("ref"),
        "link_id": link.id_link,
    }
