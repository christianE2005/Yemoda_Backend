import os
import time
import base64

import httpx
import jwt as pyjwt

GITHUB_API_URL = "https://api.github.com"

_GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")


def _normalize_private_key(raw: str) -> str:
    """Normalize a PEM private key from an env var into canonical PEM form.

    Handles both `\\n`-escaped single-line values (common in CI/secret stores) and
    real multi-line PEMs, plus optional surrounding quotes and CRLF line endings.
    Never logs the key material.
    """
    if not raw:
        return ""
    # Strip a single pair of surrounding quotes if the whole value is quoted.
    stripped = raw.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ("'", '"'):
        stripped = stripped[1:-1]
    # Turn escaped newlines into real ones and normalize CRLF/CR.
    text = stripped.replace("\\r\\n", "\n").replace("\\n", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "BEGIN" not in text:
        return text
    # Re-join non-empty, trimmed lines so a canonical PEM survives stray whitespace.
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines) + "\n"


_GITHUB_APP_PRIVATE_KEY = _normalize_private_key(os.getenv("GITHUB_APP_PRIVATE_KEY", ""))


def _generate_app_jwt() -> str:
    """Generate a short-lived JWT signed with the GitHub App private key."""
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": _GITHUB_APP_ID,
    }
    return pyjwt.encode(payload, _GITHUB_APP_PRIVATE_KEY, algorithm="RS256")


def _coerce_installation_id(installation_id: int) -> int:
    """Validate that an installation id is a positive int before using it in a URL."""
    try:
        coerced = int(installation_id)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid GitHub installation id: {installation_id!r}")
    if coerced <= 0:
        raise ValueError(f"Invalid GitHub installation id: {installation_id!r}")
    return coerced


async def _get_installation_token(installation_id: int) -> str:
    """Exchange a GitHub App JWT for an installation access token."""
    installation_id = _coerce_installation_id(installation_id)
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
    if not isinstance(data, dict) or not data.get("token"):
        raise ValueError("GitHub access_tokens response missing 'token'")
    return data["token"]


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


async def fetch_file_content_at_ref(
    repo_full_name: str,
    file_path: str,
    ref: str,
    installation_id: int | None = None,
) -> str | None:
    """Fetch text file content from GitHub Contents API at a specific ref (sha/branch/tag)."""
    import logging as _logging

    _log = _logging.getLogger(__name__)
    if not repo_full_name or not file_path or not ref:
        return None

    if not installation_id:
        installation_id = await _get_installation_id_for_repo(repo_full_name)

    token: str | None = None
    if installation_id:
        try:
            token = await _get_installation_token(installation_id)
        except Exception as exc:
            _log.warning(
                "Could not get installation token for file content %s (id=%s): %s",
                repo_full_name,
                installation_id,
                exc,
            )
            token = None

    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API_URL}/repos/{repo_full_name}/contents/{file_path}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, headers=headers, params={"ref": ref})

    if response.status_code != 200:
        return None

    data = response.json()
    if not isinstance(data, dict) or data.get("type") != "file":
        return None

    raw_content = str(data.get("content") or "").replace("\n", "")
    if not raw_content:
        return ""

    try:
        return base64.b64decode(raw_content).decode("utf-8", errors="replace")
    except Exception:
        return None
