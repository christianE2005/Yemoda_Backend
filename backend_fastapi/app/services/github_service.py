import os
import time

import httpx
import jwt as pyjwt

GITHUB_API_URL = "https://api.github.com"

_GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
_raw_pk = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
if "\\n" in _raw_pk:
    _raw_pk = _raw_pk.replace("\\n", "\n")
_raw_pk = _raw_pk.strip('"').strip("'").strip()
_raw_pk = _raw_pk.replace("\r\n", "\n").replace("\r", "\n")
if "BEGIN" in _raw_pk:
    _pk_lines = [line.strip() for line in _raw_pk.splitlines()]
    _pk_lines = [line for line in _pk_lines if line]
    _raw_pk = "\n".join(_pk_lines) + "\n"
_GITHUB_APP_PRIVATE_KEY = _raw_pk


def _generate_app_jwt() -> str:
    """Generate a short-lived JWT signed with the GitHub App private key."""
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": _GITHUB_APP_ID,
    }
    return pyjwt.encode(payload, _GITHUB_APP_PRIVATE_KEY, algorithm="RS256")


async def _get_installation_token(installation_id: int) -> str:
    """Exchange a GitHub App JWT for an installation access token."""
    app_jwt = _generate_app_jwt()
    url = f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, headers=headers)
    response.raise_for_status()
    return response.json()["token"]


async def _get_installation_id_for_repo(repo_full_name: str) -> int | None:
    """Discover the GitHub App installation ID for a given repo via the App JWT."""
    try:
        app_jwt = _generate_app_jwt()
        url = f"{GITHUB_API_URL}/repos/{repo_full_name}/installation"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("id")
    except Exception:
        pass
    return None


async def fetch_push_diff(repo_full_name: str, base_sha: str, head_sha: str, installation_id: int | None = None) -> str:
    """Fetch unified diff between two commits using the GitHub App installation token."""
    import logging as _logging
    _log = _logging.getLogger(__name__)
    if not installation_id:
        installation_id = await _get_installation_id_for_repo(repo_full_name)
    token: str | None = None
    if installation_id:
        try:
            token = await _get_installation_token(installation_id)
        except Exception as exc:
            _log.warning("Could not get installation token for %s (id=%s): %s", repo_full_name, installation_id, exc)
            token = None

    headers: dict[str, str] = {"Accept": "application/vnd.github.v3.diff"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API_URL}/repos/{repo_full_name}/compare/{base_sha}...{head_sha}"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)

    if response.status_code == 200:
        return response.text
    return ""
