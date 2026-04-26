import os
import time
import threading
from datetime import datetime

import httpx
import jwt as pyjwt

GITHUB_API_URL = "https://api.github.com"

_GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
_raw_pk = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
if "\\n" in _raw_pk:
    _raw_pk = _raw_pk.replace("\\n", "\n")
_GITHUB_APP_PRIVATE_KEY = _raw_pk.strip('"').strip("'")

# Cache installation tokens in-memory to avoid requesting a new token for every push.
# Map: installation_id -> (token, expires_ts)
_INSTALL_TOKEN_CACHE: dict[int, tuple[str, float]] = {}
_TOKEN_LOCK = threading.Lock()


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
    """Exchange a GitHub App JWT for an installation access token.

    This function caches tokens in-memory keyed by `installation_id`. The
    GitHub installation token includes an `expires_at` field which we use to
    avoid refreshing too often.
    """
    now = time.time()
    with _TOKEN_LOCK:
        cached = _INSTALL_TOKEN_CACHE.get(installation_id)
        if cached and cached[1] > now + 30:  # still valid with small margin
            return cached[0]

    app_jwt = _generate_app_jwt()
    url = f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, headers=headers)

    response.raise_for_status()
    data = response.json()
    token = data.get("token")
    expires_at = data.get("expires_at")
    if expires_at:
        try:
            # GitHub returns ISO8601 like '2026-04-25T12:34:56Z'
            expires_ts = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            expires_ts = now + 3600
    else:
        expires_ts = now + 3600

    with _TOKEN_LOCK:
        _INSTALL_TOKEN_CACHE[installation_id] = (token, expires_ts)

    return token


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
    if not installation_id:
        installation_id = await _get_installation_id_for_repo(repo_full_name)
    token = await _get_installation_token(installation_id) if installation_id else None

    headers: dict[str, str] = {"Accept": "application/vnd.github.v3.diff"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API_URL}/repos/{repo_full_name}/compare/{base_sha}...{head_sha}"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)

    if response.status_code == 200:
        return response.text
    return ""
