"""
Hackathon Robustness Score — repo fetch + AI scoring service.

Map-reduce: download a public repo tarball in one request, keep only source files,
greedily pack them into bounded chunks, score each chunk with Claude against the fixed
rubric (MAP), then deterministically combine the per-chunk scores/findings in code
(REDUCE). Two execution paths share the same chunking + reduce:
  - normal: score every chunk synchronously in a loop (low latency, full price).
  - batch:  submit one Anthropic Message Batch request per chunk (cheaper, async);
            a poller later finalizes the batch and runs the same reduce.
"""
import io
import json
import logging
import tarfile
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.anthropic import _MODEL, generate_content
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
_MAX_PER_FILE_CHARS = 20_000                   # per-file cap so one huge file can't dominate
_MAX_CHUNK_CHARS = 120_000                     # per-chunk cap on concatenated source sent to the model
_MAX_FINDINGS = 50                             # cap on combined findings after reduce
_BATCH_MAX_TOKENS = 4096                       # output cap per chunk request (normal + batch)


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
# Chunking (MAP input)
# ─────────────────────────────────────────────────────────────────────────────

def chunk_files(
    files: dict[str, str], max_chars: int = _MAX_CHUNK_CHARS
) -> list[list[tuple[str, str]]]:
    """Greedily pack source files into chunks, each <= max_chars total content.

    A single file larger than max_chars gets its own chunk, truncated to max_chars.
    Returns a list of chunks; each chunk is a list of (path, content) tuples.
    Iteration is over sorted paths for deterministic chunk membership across runs.
    """
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_len = 0

    for path in sorted(files):
        content = files[path] or ""
        if len(content) > max_chars:
            # Flush whatever is buffered, then give this giant file its own truncated chunk.
            if current:
                chunks.append(current)
                current = []
                current_len = 0
            chunks.append([(path, content[:max_chars])])
            continue
        if current and current_len + len(content) > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
        current.append((path, content))
        current_len += len(content)

    if current:
        chunks.append(current)
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# AI scoring (MAP per chunk)
# ─────────────────────────────────────────────────────────────────────────────

_CHUNK_PROMPT = """\
You are a strict, fair hackathon judge scoring ONE SLICE of a code submission for ROBUSTNESS.
You are seeing only a subset of the project's source files (the rest are scored separately and
combined later), so judge ONLY the files shown below.

Score EACH of these six categories independently on a 0-100 scale (0 = terrible, 100 = excellent),
based solely on the files in this slice:
- security: injection, auth/secret handling, XSS/CSRF, dependency/supply-chain risk, data exposure.
- performance: algorithmic efficiency, N+1 queries, blocking I/O, caching, memory use.
- robustness: error handling, input validation, edge cases, graceful degradation, resource cleanup.
- correctness: does the code do what it claims; logic bugs; off-by-one; incorrect API usage.
- maintainability: readability, structure, naming, duplication, documentation, modularity.
- tdd: presence and quality of automated tests, coverage of edge cases, test structure.

If a category cannot be assessed from these files, give a neutral 50 rather than 0.

## Files in this slice:
{source}

## Instructions:
- Be evidence-based: cite concrete files in findings.
- Severity scale for findings: "critical" | "high" | "medium" | "low".
- Keep "notes" to 1-2 sentences per category.
- Return AT MOST 25 findings for this slice, ordered by severity.

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
  ]
}}
"""


def build_chunk_prompt(chunk: list[tuple[str, str]]) -> str:
    """Build the per-chunk MAP prompt: score the six categories for THIS chunk's files.

    Files are concatenated, each prefixed with '// FILE: path'.
    """
    source = "\n".join(f"// FILE: {path}\n{content}\n" for path, content in chunk)
    return _CHUNK_PROMPT.format(source=source)


def _chunk_char_len(chunk: list[tuple[str, str]]) -> int:
    """Total content characters in a chunk (the REDUCE weight for that chunk)."""
    return sum(len(content or "") for _path, content in chunk)


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


def _normalize_weight(value: Any) -> int:
    """Coerce a rubric weight into a non-negative int, tolerating floats/strings/None."""
    try:
        weight = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, weight)


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


def _parse_chunk_result(text: str) -> dict[str, Any]:
    """Parse one chunk's model output into {categories, findings}, tolerating malformed JSON.

    On any parse failure, returns a neutral/empty chunk result so a single bad chunk can't
    sink the whole reduce.
    """
    try:
        parsed = _parse_model_json(text)
    except Exception:
        return {"categories": {}, "findings": []}
    if not isinstance(parsed, dict):
        return {"categories": {}, "findings": []}
    return {
        "categories": parsed.get("categories") or {},
        "findings": parsed.get("findings") or [],
    }


def _empty_result(rubric: dict[str, int]) -> dict[str, Any]:
    """Deterministic zero result when there's nothing to score (no model call)."""
    breakdown = {
        cat: {"score": 0, "weight": _normalize_weight((rubric or {}).get(cat, 0))}
        for cat in CATEGORIES
    }
    return {
        "score": 0,
        "score_breakdown": breakdown,
        "findings": [],
        "summary": "No se encontraron archivos de código fuente analizables en el repositorio.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# REDUCE (deterministic — shared by normal + batch)
# ─────────────────────────────────────────────────────────────────────────────

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def reduce_chunk_scores(
    chunk_results: list[dict[str, Any]],
    weights: list[int],
    rubric: dict[str, int],
) -> dict[str, Any]:
    """Combine per-chunk MAP results into the final audit result (deterministic).

    - Per category: overall_cat_score = round(weighted average of chunk scores by char_len).
    - Findings: concatenation of all chunk findings, sorted critical>high>medium>low, capped 50.
    - Overall: round(sum(cat_score * rubric_weight) / sum(rubric_weight)) ignoring weight 0;
      if all rubric weights are 0, fall back to a plain average of the six categories.
    Returns {score, score_breakdown, findings, summary} — the same shape audit writes.
    """
    rubric = rubric or {}
    n_chunks = len(chunk_results)
    # Normalize weights: any missing/non-positive char_len falls back to 1 so a chunk still counts.
    safe_weights = [w if isinstance(w, int) and w > 0 else 1 for w in weights]
    # Pad/trim weights to match chunk_results length defensively.
    if len(safe_weights) < n_chunks:
        safe_weights = safe_weights + [1] * (n_chunks - len(safe_weights))

    breakdown: dict[str, dict[str, int]] = {}
    for cat in CATEGORIES:
        weighted_sum = 0
        weight_total = 0
        for result, w in zip(chunk_results, safe_weights):
            categories = result.get("categories") or {}
            entry = categories.get(cat)
            if not isinstance(entry, dict) or entry.get("score") is None:
                continue  # chunk didn't score this category — skip it from the average.
            weighted_sum += _coerce_score(entry.get("score")) * w
            weight_total += w
        cat_score = round(weighted_sum / weight_total) if weight_total > 0 else 0
        breakdown[cat] = {"score": cat_score, "weight": _normalize_weight(rubric.get(cat, 0))}

    total_weight = sum(b["weight"] for b in breakdown.values())
    if total_weight > 0:
        overall = round(
            sum(b["score"] * b["weight"] for b in breakdown.values()) / total_weight
        )
    else:
        # All rubric weights zero: fall back to a plain average of the six categories.
        overall = round(sum(b["score"] for b in breakdown.values()) / len(CATEGORIES))

    # Concatenate, normalize, and order findings; cap at _MAX_FINDINGS.
    all_findings: list[dict[str, str]] = []
    for result in chunk_results:
        all_findings.extend(_normalize_findings(result.get("findings")))
    all_findings.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "low"), 3))
    findings = all_findings[:_MAX_FINDINGS]

    # _n_files is set by the normal MAP driver; batch results don't carry it, so fall back to
    # describing chunk coverage only.
    n_files = sum(int(result.get("_n_files") or 0) for result in chunk_results)
    if n_files > 0:
        summary = f"Analyzed {n_files} files in {n_chunks} chunks."
    else:
        summary = f"Analyzed {n_chunks} chunks."

    return {
        "score": overall,
        "score_breakdown": breakdown,
        "findings": findings,
        "summary": summary,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAP driver — normal (synchronous loop)
# ─────────────────────────────────────────────────────────────────────────────

def score_submission_normal(files: dict[str, str], rubric: dict[str, int]) -> dict[str, Any]:
    """Score a submission via map-reduce in a synchronous loop, then reduce.

    Chunks the source, scores each chunk with one Claude call, parses each robustly, and
    deterministically reduces. Returns {score, score_breakdown, findings, summary}.
    """
    if not files:
        return _empty_result(rubric or {})

    chunks = chunk_files(files)
    chunk_results: list[dict[str, Any]] = []
    weights: list[int] = []
    for chunk in chunks:
        prompt = build_chunk_prompt(chunk)
        text = generate_content(
            prompt, json_mode=True, label="hackathon_audit", max_tokens=_BATCH_MAX_TOKENS
        )
        result = _parse_chunk_result(text)
        result["_n_files"] = len(chunk)
        chunk_results.append(result)
        weights.append(_chunk_char_len(chunk))

    return reduce_chunk_scores(chunk_results, weights, rubric or {})


# Backwards-compatible alias: the original single-pass entry point now runs map-reduce.
def score_submission(files: dict[str, str], rubric: dict[str, int]) -> dict[str, Any]:
    """Deprecated alias for score_submission_normal (kept for callers/imports)."""
    return score_submission_normal(files, rubric)


# ─────────────────────────────────────────────────────────────────────────────
# BATCH (Anthropic Message Batches) — submit + finalize
# ─────────────────────────────────────────────────────────────────────────────

def submit_batch(
    files: dict[str, str], rubric: dict[str, int]
) -> tuple[str | None, dict[str, Any]]:
    """Submit one Anthropic Message Batch request per chunk and return (batch_id, batch_meta).

    batch_meta = {"n_chunks":N, "chunks":[{"idx":i,"char_len":len}], "rubric":rubric}.
    Uses the SAME model string as core/anthropic.generate_content. If there are no files,
    returns (None, meta) with n_chunks=0 so the caller can short-circuit.
    """
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    rubric = rubric or {}
    chunks = chunk_files(files)
    meta_chunks = [{"idx": i, "char_len": _chunk_char_len(chunk)} for i, chunk in enumerate(chunks)]
    batch_meta: dict[str, Any] = {
        "n_chunks": len(chunks),
        "chunks": meta_chunks,
        "rubric": rubric,
    }
    if not chunks:
        return None, batch_meta

    requests = [
        Request(
            custom_id=f"chunk-{i}",
            params=MessageCreateParamsNonStreaming(
                model=_MODEL,
                max_tokens=_BATCH_MAX_TOKENS,
                system=(
                    "Respond only with valid JSON. Do not include markdown, "
                    "code fences, or any other text."
                ),
                messages=[{"role": "user", "content": build_chunk_prompt(chunk)}],
            ),
        )
        for i, chunk in enumerate(chunks)
    ]

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)
    return batch.id, batch_meta


def _custom_id_index(custom_id: str) -> int:
    """Extract the integer chunk index from a 'chunk-{i}' custom_id (large fallback if malformed)."""
    try:
        return int(str(custom_id).rsplit("-", 1)[-1])
    except (ValueError, IndexError):
        return 1_000_000


def finalize_batch(
    client: Any, batch_id: str, batch_meta: dict[str, Any], rubric: dict[str, int]
) -> dict[str, Any] | None:
    """Retrieve a Message Batch and reduce its results, or None if not finished.

    If the batch's processing_status is not "ended", returns None (caller leaves the row
    as batch_pending). Otherwise streams results, parses each succeeded message as a chunk
    result (errored/expired/canceled results are zeroed), orders by custom_id chunk idx,
    rebuilds weights from batch_meta, and runs the shared reduce.
    """
    rubric = rubric or {}
    batch_meta = batch_meta or {}

    batch = client.messages.batches.retrieve(batch_id)
    if getattr(batch, "processing_status", None) != "ended":
        return None

    n_chunks = int(batch_meta.get("n_chunks") or 0)
    # char_len per chunk idx, defaulting to 1 when absent.
    char_lens: dict[int, int] = {}
    for c in batch_meta.get("chunks") or []:
        try:
            char_lens[int(c.get("idx"))] = int(c.get("char_len") or 1)
        except (TypeError, ValueError):
            continue

    if n_chunks <= 0:
        return _empty_result(rubric)

    # Collect parsed results keyed by chunk idx (default to empty/zero result).
    parsed_by_idx: dict[int, dict[str, Any]] = {}
    for entry in client.messages.batches.results(batch_id):
        idx = _custom_id_index(getattr(entry, "custom_id", ""))
        result_obj = getattr(entry, "result", None)
        result_type = getattr(result_obj, "type", None)
        if result_type != "succeeded":
            # errored | expired | canceled — zero this chunk and keep going.
            parsed_by_idx[idx] = {"categories": {}, "findings": []}
            continue
        message = getattr(result_obj, "message", None)
        text = "".join(
            getattr(block, "text", "") or "" for block in (getattr(message, "content", None) or [])
        )
        parsed_by_idx[idx] = _parse_chunk_result(text)

    # Order by chunk idx; fill any gaps (missing results) with zeroed chunks.
    chunk_results: list[dict[str, Any]] = []
    weights: list[int] = []
    for idx in range(n_chunks):
        chunk_results.append(parsed_by_idx.get(idx, {"categories": {}, "findings": []}))
        weights.append(char_lens.get(idx, 1))

    return reduce_chunk_scores(chunk_results, weights, rubric)
