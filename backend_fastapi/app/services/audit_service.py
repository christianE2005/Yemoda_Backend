"""
Hackathon Robustness Score — repo fetch + AI scoring service.

A single bounded pass for the MVP: download a public repo tarball in one request,
keep only source files (capped), send them to Claude with a fixed rubric, and compute
the weighted overall score in code. No map-reduce; big repos are truncated.
"""
import io
import json
import logging
import tarfile
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.anthropic import generate_content
from app.services.github_service import (
    GITHUB_API_URL,
    _generate_app_jwt,
)

logger = logging.getLogger(__name__)

# Fixed categories scored by the AI (the rubric only weights them).
CATEGORIES: tuple[str, ...] = (
    "security",
    "performance",
    "robustness",
    "correctness",
    "maintainability",
    "tdd",
)

# Source-file extensions we keep; everything else (assets, binaries) is dropped.
_SOURCE_EXTENSIONS: tuple[str, ...] = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".rb", ".php",
    ".c", ".cpp", ".cs", ".rs", ".kt", ".swift", ".scala", ".sql", ".sh",
    ".html", ".css", ".vue", ".svelte",
)

# Path fragments that mark vendored / generated / VCS dirs we never analyze.
_EXCLUDED_DIRS: tuple[str, ...] = (
    "node_modules/", "vendor/", "dist/", "build/", ".git/",
)

# Lockfiles never carry meaningful source to score.
_EXCLUDED_FILENAMES: frozenset[str] = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock",
    "poetry.lock", "pipfile.lock", "gemfile.lock", "cargo.lock", "go.sum",
})

_MAX_TARBALL_BYTES = 40 * 1024 * 1024          # hard cap on the streamed download (~40MB)
_MAX_TOTAL_CONTENT_CHARS = 150_000             # cap on concatenated source sent to the model
_MAX_PER_FILE_CHARS = 20_000                   # per-file cap so one huge file can't dominate


# ─────────────────────────────────────────────────────────────────────────────
# Repo fetch
# ─────────────────────────────────────────────────────────────────────────────

def _parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL (or 'owner/repo' shorthand)."""
    cleaned = (repo_url or "").strip()
    if cleaned.startswith(("http://", "https://", "git@", "ssh://")):
        path = urlparse(cleaned.replace("git@github.com:", "https://github.com/")).path
    else:
        path = cleaned
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"No se pudo extraer owner/repo de la URL: {repo_url!r}")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def _resolve_app_token(owner: str, repo: str) -> str | None:
    """Best-effort GitHub App installation token (sync) for higher rate limits.

    Reuses the App JWT minted by github_service; falls back to None (unauthenticated)
    if the App is not configured or not installed on the repo.
    """
    try:
        app_jwt = _generate_app_jwt()
    except Exception as exc:  # App not configured / bad key — go unauthenticated.
        logger.info("GitHub App JWT unavailable, fetching tarball unauthenticated: %s", exc)
        return None

    headers = {"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"}
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            inst = client.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/installation", headers=headers)
            if inst.status_code != 200:
                return None
            installation_id = inst.json().get("id")
            if not installation_id:
                return None
            token_resp = client.post(
                f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
                headers=headers,
            )
            if token_resp.status_code not in (200, 201):
                return None
            return token_resp.json().get("token")
    except Exception as exc:
        logger.info("Could not resolve GitHub App token for %s/%s: %s", owner, repo, exc)
        return None


def _is_source_path(path: str) -> bool:
    """Decide whether a tar member path is a source file worth keeping."""
    lower = path.lower()
    if any(frag in lower for frag in _EXCLUDED_DIRS):
        return False
    name = lower.rsplit("/", 1)[-1]
    if name in _EXCLUDED_FILENAMES:
        return False
    if ".min." in name:  # minified bundles
        return False
    return lower.endswith(_SOURCE_EXTENSIONS)


def fetch_repo_source(repo_url: str, ref: str) -> dict[str, str]:
    """Download a public repo tarball in ONE request and return {relative_path: content}.

    Uses the GitHub App token when available (higher rate limits), else unauthenticated.
    Streams with a hard ~40MB cap, extracts in memory, and keeps only source files.
    """
    owner, repo = _parse_owner_repo(repo_url)
    ref = (ref or "main").strip() or "main"

    headers = {"Accept": "application/vnd.github+json"}
    token = _resolve_app_token(owner, repo)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/tarball/{ref}"

    buffer = io.BytesIO()
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code != 200:
                raise ValueError(
                    f"No se pudo descargar el repositorio {owner}/{repo}@{ref} "
                    f"(HTTP {response.status_code})."
                )
            for chunk in response.iter_bytes():
                buffer.write(chunk)
                if buffer.tell() > _MAX_TARBALL_BYTES:
                    raise ValueError(
                        f"El repositorio supera el límite de {_MAX_TARBALL_BYTES // (1024 * 1024)}MB."
                    )

    buffer.seek(0)
    files: dict[str, str] = {}
    with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            # GitHub tarballs nest everything under a top-level "{owner}-{repo}-{sha}/" dir;
            # strip it so paths read naturally.
            rel_path = member.name.split("/", 1)[1] if "/" in member.name else member.name
            if not rel_path or not _is_source_path(rel_path):
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            try:
                content = extracted.read().decode("utf-8", errors="replace")
            except Exception:
                continue
            files[rel_path] = content[:_MAX_PER_FILE_CHARS]

    return files


# ─────────────────────────────────────────────────────────────────────────────
# AI scoring
# ─────────────────────────────────────────────────────────────────────────────

_RUBRIC_PROMPT = """\
You are a strict, fair hackathon judge scoring a single code submission for ROBUSTNESS.

Score EACH of these six categories independently on a 0-100 scale (0 = terrible, 100 = excellent):
- security: injection, auth/secret handling, XSS/CSRF, dependency/supply-chain risk, data exposure.
- performance: algorithmic efficiency, N+1 queries, blocking I/O, caching, memory use.
- robustness: error handling, input validation, edge cases, graceful degradation, resource cleanup.
- correctness: does the code do what it claims; logic bugs; off-by-one; incorrect API usage.
- maintainability: readability, structure, naming, duplication, documentation, modularity.
- tdd: presence and quality of automated tests, coverage of edge cases, test structure.

## Judge rubric weights (a weight of 0 means the category is IGNORED in the OVERALL score,
## but you MUST still score it 0-100 honestly):
{rubric_text}

Prioritize your scrutiny toward the higher-weighted categories, but score all six.

## Submission source files (truncated){truncation_note}:
{source}

## Instructions:
- Be evidence-based: cite concrete files in findings.
- Severity scale for findings: "critical" | "high" | "medium" | "low".
- Keep "notes" to 1-2 sentences per category and "summary" to 3-5 sentences.
- Return AT MOST 25 findings, ordered by severity.

Respond ONLY with valid JSON in EXACTLY this shape:
{{
  "categories": {{
    "security": {{"score": <int 0-100>, "notes": "<string>"}},
    "performance": {{"score": <int 0-100>, "notes": "<string>"}},
    "robustness": {{"score": <int 0-100>, "notes": "<string>"}},
    "correctness": {{"score": <int 0-100>, "notes": "<string>"}},
    "maintainability": {{"score": <int 0-100>, "notes": "<string>"}},
    "tdd": {{"score": <int 0-100>, "notes": "<string>"}}
  }},
  "findings": [
    {{"category": "<one of the six>", "severity": "critical|high|medium|low",
      "title": "<short string>", "file": "<path or empty>", "description": "<1-2 sentences>"}}
  ],
  "summary": "<3-5 sentence overall assessment>"
}}
"""


def _build_source_block(files: dict[str, str]) -> tuple[str, int]:
    """Concatenate source files (each prefixed with '// FILE: path') under the global cap.

    Returns (concatenated_text, dropped_file_count).
    """
    chunks: list[str] = []
    total = 0
    dropped = 0
    # Sort for deterministic truncation behavior across runs.
    for path in sorted(files):
        block = f"// FILE: {path}\n{files[path]}\n"
        if total + len(block) > _MAX_TOTAL_CONTENT_CHARS:
            dropped += 1
            continue
        chunks.append(block)
        total += len(block)
    return "\n".join(chunks), dropped


def _coerce_score(value: Any) -> int:
    """Clamp a model-provided score into 0..100, tolerating floats/strings/None."""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, n))


def _parse_model_json(text: str) -> dict[str, Any]:
    """Robustly parse the model's JSON, tolerating code fences / surrounding prose."""
    text = (text or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


def _compute_overall(categories: dict[str, dict[str, Any]], rubric: dict[str, int]) -> tuple[int, dict[str, dict[str, int]]]:
    """Weighted overall + per-category breakdown.

    overall = round(sum(cat_score * weight) / sum(weight)), ignoring weight==0.
    If all weights are 0 (or missing), fall back to equal weights across the six categories.
    """
    breakdown: dict[str, dict[str, int]] = {}
    for cat in CATEGORIES:
        cat_score = _coerce_score((categories.get(cat) or {}).get("score"))
        weight = rubric.get(cat, 0)
        try:
            weight = int(weight)
        except (TypeError, ValueError):
            weight = 0
        if weight < 0:
            weight = 0
        breakdown[cat] = {"score": cat_score, "weight": weight}

    total_weight = sum(b["weight"] for b in breakdown.values())
    if total_weight > 0:
        weighted_sum = sum(b["score"] * b["weight"] for b in breakdown.values())
        overall = round(weighted_sum / total_weight)
    else:
        # All weights zero: fall back to a plain average of the six categories.
        overall = round(sum(b["score"] for b in breakdown.values()) / len(CATEGORIES))

    return overall, breakdown


def _normalize_findings(raw: Any) -> list[dict[str, str]]:
    """Coerce the model's findings into the contract shape, dropping malformed entries."""
    allowed_sev = {"critical", "high", "medium", "low"}
    findings: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "")).strip()
        if category not in CATEGORIES:
            category = ""
        severity = str(item.get("severity", "")).strip().lower()
        if severity not in allowed_sev:
            severity = "low"
        findings.append({
            "category": category,
            "severity": severity,
            "title": str(item.get("title", "")).strip()[:300],
            "file": str(item.get("file", "")).strip()[:500],
            "description": str(item.get("description", "")).strip()[:1000],
        })
    return findings


def score_submission(files: dict[str, str], rubric: dict[str, int]) -> dict[str, Any]:
    """Score a submission in a single bounded AI pass and compute the weighted overall.

    Returns {score, score_breakdown, findings, summary}.
    """
    if not files:
        # Nothing to score — return a deterministic zero result rather than calling the model.
        _, breakdown = _compute_overall({}, rubric or {})
        return {
            "score": 0,
            "score_breakdown": breakdown,
            "findings": [],
            "summary": "No se encontraron archivos de código fuente analizables en el repositorio.",
        }

    source_block, dropped = _build_source_block(files)
    truncation_note = (
        f" — {dropped} archivo(s) omitido(s) por límite de tamaño" if dropped else ""
    )

    rubric_text = "\n".join(
        f"- {cat}: weight {int(rubric.get(cat, 0) or 0)}" for cat in CATEGORIES
    )

    prompt = _RUBRIC_PROMPT.format(
        rubric_text=rubric_text,
        truncation_note=truncation_note,
        source=source_block,
    )

    text = generate_content(prompt, json_mode=True, label="hackathon_audit", max_tokens=4096)
    parsed = _parse_model_json(text)

    categories = parsed.get("categories") or {}
    overall, breakdown = _compute_overall(categories, rubric or {})
    findings = _normalize_findings(parsed.get("findings"))
    summary = str(parsed.get("summary", "")).strip()

    return {
        "score": overall,
        "score_breakdown": breakdown,
        "findings": findings,
        "summary": summary,
    }
