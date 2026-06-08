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
import os
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

# Model used to SCORE hackathon submissions. Defaults to Haiku 4.5 (cheapest, fast). Reliability
# comes from the strict defects-only prompt + temperature=0 + anchors + verify pass. Set
# HACKATHON_AI_MODEL=claude-sonnet-4-6 if you want stronger instruction-following (fewer
# false/nitpick findings) at ~3x the cost.
_AUDIT_MODEL = os.getenv("HACKATHON_AI_MODEL", "claude-haiku-4-5")

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
    # Migrations are auto-generated historical schema, not the team's code. Auditing them yields
    # noise and false positives — e.g. an old migration's plain CharField reads as "plaintext"
    # even after the live model switched to an encrypted field.
    "migrations/",
)

# Lockfiles never carry meaningful source to score.
_EXCLUDED_FILENAMES: frozenset[str] = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock",
    "poetry.lock", "pipfile.lock", "gemfile.lock", "cargo.lock", "go.sum",
})

_MAX_TARBALL_BYTES = 40 * 1024 * 1024          # hard cap on the streamed download (~40MB)
_MAX_PER_FILE_CHARS = 50_000                   # per-file cap (raised from 20k for fuller coverage of large files)
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
            if len(content) > _MAX_PER_FILE_CHARS:
                # Mark the cut explicitly so the model never mistakes a length-truncated file for
                # "incomplete code" / an unfinished function / a syntax error — a real source of
                # false-positive findings.
                content = (
                    content[:_MAX_PER_FILE_CHARS]
                    + "\n\n# ... [truncated for length — the rest of this file is not shown] ...\n"
                )
            files[rel_path] = content

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

## Scoring anchors — apply the SAME absolute standard every time so scores are comparable across submissions:
- 90-100: no real defects in this slice; solid, idiomatic, handles errors and edge cases.
- 70-89: minor issues only; generally sound.
- 50-69: some real defects or gaps that need attention.
- 30-49: serious defects likely to cause failures.
- 0-29: critical or broken — would fail or be exploitable in production.
Judge each category against THESE anchors, not relative to other submissions. If a category
genuinely cannot be assessed from these files, give a neutral 50.

## Files in this slice:
{source}

## Severity — a finding is ALWAYS a concrete DEFECT (see below). Assign CONSERVATIVELY:
- "critical": a concrete, exploitable security vulnerability, data loss, or a bug that crashes
  or breaks core functionality in production. Only use this if you can name the specific exploit
  or failure scenario in the description.
- "high": a serious bug or security weakness likely to cause incorrect behavior or real risk
  under realistic conditions.
- "medium": a real defect with limited or conditional impact.
- "low": a real but minor defect (a narrow edge case, low-impact missing error handling).

## What IS a finding — report ONLY these:
A concrete DEFECT you can directly SEE in the shown code: a security vulnerability, a
correctness/logic bug, a crash, data loss, an unhandled error that would actually fail, a resource
or connection leak, or an injection. You must be able to name the input or condition that triggers it.

## What is NOT a finding — NEVER report these (they may inform the category SCORE, but stay OUT of the findings list):
- Style, naming, formatting, code organization, magic numbers, duplication, missing comments/docs.
- Missing tests or missing CI (the tdd score already reflects this).
- "Could be refactored / batched / cached / optimized", or any "consider ..." / "should ideally ..."
  suggestion. If it is a preference rather than a bug, it is NOT a finding.

## Hard rules (follow EXACTLY):
- ABSENCE IS NOT A FINDING. You see only ONE SLICE of the project, so you CANNOT verify that
  something is "missing", "not validated", "not invalidated", "not handled", "has no
  endpoint/handler/test", or "lacks" X — that handling may live in files you cannot see. Report
  only a defect directly VISIBLE in the shown code; never report the absence of something.
- Before reporting a bug, check whether the shown code ALREADY prevents it (an existing guard,
  null-check, early return, try/except, or default). If it is already handled, do NOT report it.
- Files may be TRUNCATED (look for a "[truncated ...]" marker). NEVER report code as incomplete,
  cut off, or a "syntax error from an unfinished block" — you are seeing only PART of a file.
- Every finding MUST reference a specific file in THIS slice (put it in "file") and describe the
  concrete failure. Keep "notes" to 1-2 sentences per category. Return AT MOST 15 findings for this
  slice, ordered by severity. Quality over quantity — emit only real, visible defects (it is correct
  to return an empty findings list when the slice has none).

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
    """Clamp a model-provided score into 0..100, tolerating floats/strings/None.

    A non-numeric score (e.g. "N/A" or a dict) defaults to 0 — we keep scoring rather than
    crash the whole audit on one malformed response — but we log it so model-output corruption
    is surfaced instead of hidden.
    """
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        logger.warning("hackathon: non-numeric score %r coerced to 0", value)
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

# Process/quality categories are never an exploitable defect, so their findings are capped here
# regardless of what the model claims: absence of tests or a maintainability nit must not surface
# as critical/high. This is the deterministic backstop behind the prompt's severity rules.
_MAX_SEVERITY_BY_CATEGORY = {"tdd": "medium", "maintainability": "high"}


def _cap_finding_severity(finding: dict[str, str]) -> dict[str, str]:
    """Clamp a finding's severity to its per-category ceiling (e.g. tdd never above medium)."""
    cap = _MAX_SEVERITY_BY_CATEGORY.get(finding.get("category", ""))
    if cap and _SEVERITY_ORDER.get(finding.get("severity", "low"), 3) < _SEVERITY_ORDER[cap]:
        finding["severity"] = cap
    return finding


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

    # Combine findings across slices, then make them reliable:
    #   1) cap process-category severities (tests/maintainability are never critical),
    #   2) dedup repeats across slices by (category, title, file), keeping the most severe,
    #   3) order by severity and cap the total.
    all_findings: list[dict[str, str]] = []
    for result in chunk_results:
        all_findings.extend(_normalize_findings(result.get("findings")))
    for finding in all_findings:
        _cap_finding_severity(finding)
    deduped: dict[tuple[str, str, str], dict[str, str]] = {}
    for finding in all_findings:
        key = (
            finding.get("category", ""),
            " ".join((finding.get("title") or "").lower().split()),
            (finding.get("file") or "").lower(),
        )
        current = deduped.get(key)
        if current is None or (
            _SEVERITY_ORDER.get(finding["severity"], 3)
            < _SEVERITY_ORDER.get(current["severity"], 3)
        ):
            deduped[key] = finding
    findings = sorted(
        deduped.values(), key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "low"), 3)
    )[:_MAX_FINDINGS]

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
# VERIFY (high-fidelity adversarial re-judge of critical/high/medium findings)
# ─────────────────────────────────────────────────────────────────────────────

# Medium is included: the deterministic score is computed from the findings, so a by-design /
# already-handled / outdated MEDIUM that survives the MAP pass directly (and unfairly) drags the
# grade down. Re-reading the cited file is the only thing that reliably refutes those, so high-
# fidelity now re-judges medium too. The file-group cap is raised so medium coverage is broad;
# findings are severity-sorted, so critical/high groups are always verified before mediums.
_VERIFY_MAX_FILES = 20                          # cap on file-groups we spend a call on
_VERIFY_SEVERITIES: tuple[str, ...] = ("critical", "high", "medium")

_VERIFY_PROMPT = """\
You are a skeptical security/code reviewer. For EACH reported finding, decide using ONLY
the source file shown whether it is genuinely valid at the stated severity. Default to downgrading or
dropping when evidence is weak, hypothetical, or not actually present in this file.

Before keeping a finding, check whether the shown code ALREADY handles the described case — an
existing guard, null-check, early return, try/except, default value, or equivalent. If the reported
bug is already prevented by the code, respond "drop". Also "drop" any finding that claims the code is
incomplete, truncated, cut off, or has a "syntax error from an unfinished block": files may be
truncated for length (look for a "[truncated ...]" marker), which is not a real defect.

Also "drop" findings that are NOT concrete defects: pure style/naming/formatting, magic numbers,
missing tests/docs, "could be refactored/batched/optimized", or any "consider/should ideally"
preference. And "drop" any finding that asserts something is "missing", "not validated/handled",
"has no endpoint/test", or otherwise claims an ABSENCE — that cannot be verified from one file.
Keep a finding only if it is a real defect you can point to in the source shown.

## FILE: {path}
{code}

## Reported findings (1-based):
{findings}

For each finding, return a verdict:
- "keep": the finding is genuinely valid at its stated severity.
- "downgrade": the issue is real but overstated — return a lower severity.
- "drop": the issue is refuted, hypothetical, or not present in this file.

Respond ONLY with STRICT JSON in EXACTLY this shape:
{{"verdicts":[{{"index":<1-based int>,"verdict":"keep|downgrade|drop","severity":"critical|high|medium|low"}}]}}
"""


def build_verify_prompt(path: str, code: str, group: list[dict]) -> str:
    """Build the adversarial verification prompt for one file's critical/high findings.

    Embeds the source file and a numbered (1-based) list of the group's findings, and asks the
    model to keep / downgrade / drop each one, justifying only from the shown source.
    """
    findings = "\n".join(
        f"{i}. [{(f.get('severity') or '').strip()}] "
        f"{(f.get('title') or '').strip()} — {(f.get('description') or '').strip()}"
        for i, f in enumerate(group, start=1)
    )
    return _VERIFY_PROMPT.format(path=path, code=code, findings=findings)


def _downgrade_severity(current: str, target: str) -> str:
    """Return the new severity for a 'downgrade' verdict.

    Use `target` if it's strictly less severe than `current` (per _SEVERITY_ORDER); otherwise
    drop `current` exactly one level. Never goes below "low".
    """
    cur_rank = _SEVERITY_ORDER.get(current, 3)
    tgt_rank = _SEVERITY_ORDER.get(target, None)
    if tgt_rank is not None and tgt_rank > cur_rank:
        return target
    new_rank = min(cur_rank + 1, _SEVERITY_ORDER["low"])
    for sev, rank in _SEVERITY_ORDER.items():
        if rank == new_rank:
            return sev
    return "low"


def verify_findings_pass(files: dict[str, str], findings: list[dict]) -> list[dict]:
    """Adversarially re-judge critical/high/medium findings against their cited source file.

    Splits findings into to_verify (severity in _VERIFY_SEVERITIES) and passthrough (low only).
    Groups to_verify by cited file and, for up to _VERIFY_MAX_FILES groups with available source,
    asks the model to keep/downgrade/drop each finding — re-reading the code refutes by-design /
    already-handled / outdated claims the MAP pass got wrong. low findings pass through untouched;
    numeric scores are never changed. On any call/parse failure a group is kept as-is (verify never
    loses findings to an error). Returns passthrough + kept verified findings, severity-sorted and
    capped at _MAX_FINDINGS.
    """
    to_verify: list[dict] = []
    passthrough: list[dict] = []
    for finding in findings or []:
        if (finding.get("severity") or "") in _VERIFY_SEVERITIES:
            to_verify.append(finding)
        else:
            passthrough.append(finding)

    if not to_verify:
        return findings

    # Group the to-verify findings by their cited file (deterministic, severity-sorted order).
    groups: dict[str, list[dict]] = {}
    for finding in to_verify:
        path = finding.get("file") or ""
        groups.setdefault(path, []).append(finding)

    kept: list[dict] = []
    for i, (path, group) in enumerate(groups.items()):
        # Beyond the cap, or no source to judge against -> keep the group as-is (can't verify).
        if i >= _VERIFY_MAX_FILES or not files.get(path):
            kept.extend(group)
            continue

        try:
            text = generate_content(
                build_verify_prompt(path, files[path], group),
                model_name=_AUDIT_MODEL,
                json_mode=True,
                label="hackathon_verify",
                max_tokens=2048,
                temperature=0,
            )
            parsed = _parse_model_json(text)
        except Exception:
            # On call/parse failure, keep the group as-is — verify never loses real findings.
            kept.extend(group)
            continue

        verdicts: dict[int, dict[str, Any]] = {}
        for v in (parsed.get("verdicts") if isinstance(parsed, dict) else None) or []:
            if not isinstance(v, dict):
                continue
            try:
                verdicts[int(v.get("index"))] = v
            except (TypeError, ValueError):
                continue

        for idx, finding in enumerate(group, start=1):
            verdict = verdicts.get(idx)
            if verdict is not None:
                decision = str(verdict.get("verdict", "")).strip().lower()
                if decision == "drop":
                    continue
                if decision == "downgrade":
                    finding["severity"] = _downgrade_severity(
                        finding.get("severity", "low"),
                        str(verdict.get("severity", "")).strip().lower(),
                    )
                # "keep" (or anything else) -> unchanged.
            # verdict missing -> finding unchanged. Re-apply the per-category ceiling either way.
            kept.append(_cap_finding_severity(finding))

    combined = passthrough + kept
    return sorted(
        combined, key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "low"), 3)
    )[:_MAX_FINDINGS]


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
            prompt, model_name=_AUDIT_MODEL, json_mode=True, label="hackathon_audit",
            max_tokens=_BATCH_MAX_TOKENS, temperature=0,
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
# CLEANUP — final pass: drop non-defects/noise + merge duplicates (one cheap call)
# ─────────────────────────────────────────────────────────────────────────────

_CLEANUP_PROMPT = """\
You are doing a FINAL cleanup of a code-review findings list before it is shown to a team. The list
was produced by analyzing the repo in slices, so it may contain duplicates and items that are not
real defects. Produce a cleaned list.

REMOVE an entry if ANY of these is true:
- It is NOT a concrete defect: style/naming/formatting, magic numbers, missing docs/tests, or a
  "could be refactored/optimized/batched" / "consider ..." / "should ideally ..." preference.
- Its OWN description admits it is fine: e.g. "this is correct", "is safe", "no real impact",
  "but confusing", "unlikely", "theoretical", "for clarity", "for maintainability".
- It asserts an ABSENCE ("missing", "not validated/handled", "no endpoint/test") — that cannot be a
  verified defect from a static slice review.
Then MERGE entries describing the SAME underlying issue into one (keep the highest severity, the
clearest title, a combined description, the most relevant file).

Rules:
- KEEP every genuine, concrete defect. When UNSURE whether something is a real defect, KEEP it.
- Do NOT invent new findings. Do NOT raise any severity.

## Findings (1-based):
{findings}

Respond ONLY with STRICT JSON (the cleaned list; an empty list is valid if nothing is a real defect):
{{"findings":[{{"category":"security|performance|robustness|correctness|maintainability|tdd","severity":"critical|high|medium|low","title":"<string>","file":"<path or empty>","description":"<1-2 sentences>"}}]}}
"""


def cleanup_findings(findings: list[dict]) -> list[dict]:
    """Final pass over the WHOLE findings list (one cheap LLM call at temp 0): drop non-defects,
    self-acknowledged-fine items, absence claims, and style noise; merge duplicates.

    Guarded so it can only SHRINK/merge — never invent or escalate. On any call/parse failure, or a
    result LONGER than the input, the original findings are returned unchanged; severities are
    re-capped and can never exceed the worst input severity. An empty result is accepted (a slice
    of all-noise legitimately cleans to nothing). No-op for an empty input.
    """
    if not findings:
        return findings
    listing = "\n".join(
        f"{i}. [{f.get('severity', 'low')}] ({f.get('category', '')}) {f.get('title', '')}"
        f" — file: {f.get('file') or 'n/a'} — {f.get('description', '')}"
        for i, f in enumerate(findings, 1)
    )
    try:
        text = generate_content(
            _CLEANUP_PROMPT.format(findings=listing),
            model_name=_AUDIT_MODEL,
            json_mode=True,
            label="hackathon_cleanup",
            max_tokens=2048,
            temperature=0,
        )
        parsed = _parse_model_json(text)
        cleaned = _normalize_findings(parsed.get("findings") if isinstance(parsed, dict) else None)
    except Exception:
        return findings
    # The pass may only shrink/merge. A list LONGER than the input means it misbehaved — keep original.
    if len(cleaned) > len(findings):
        return findings
    # Anti-erasure: one misbehaving cleanup response must not silently delete every high-severity
    # finding. If the input had critical/high items and none survive the cleanup, distrust it and
    # keep the original list — losing a team's real critical defect is far worse than some noise.
    high = ("critical", "high")
    if any(f.get("severity") in high for f in findings) and not any(
        f.get("severity") in high for f in cleaned
    ):
        return findings
    # Anti-escalation: never produce a severity worse than the worst input.
    worst_rank = min(
        (_SEVERITY_ORDER.get(f.get("severity", "low"), 3) for f in findings), default=3
    )
    worst_sev = next((s for s, r in _SEVERITY_ORDER.items() if r == worst_rank), "low")
    for finding in cleaned:
        if _SEVERITY_ORDER.get(finding.get("severity", "low"), 3) < worst_rank:
            finding["severity"] = worst_sev
        _cap_finding_severity(finding)
    cleaned.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "low"), 3))
    return cleaned[:_MAX_FINDINGS]


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC RELIABILITY LAYER — noise backstop + score-from-findings
# ─────────────────────────────────────────────────────────────────────────────

# Rule-based (no LLM) drop of near-certain non-defects the LLM cleanup may miss. SAFETY FIRST: this
# filter ONLY ever drops LOW-severity findings, so it can never hide a real critical/high defect.
# Developer-motive words ("by design", "intentionally", "for clarity") were deliberately removed —
# they explain WHY buggy code exists and routinely appear inside descriptions of real defects; keying
# on them silently deleted genuine criticals. We keep only unambiguous self-cancellations.
# Only EXPLICIT "this is not a defect" declarations — these cannot describe a real bug (a genuine
# bug is never phrased "not a real defect"). Magnitude qualifiers like "no real impact" / "purely
# theoretical" were removed: a model naturally appends them to REAL minor bugs ("an off-by-one with
# no functional impact"), so keying on them dropped genuine low defects.
_NOISE_PHRASES: tuple[str, ...] = (
    "not a real defect", "not a real issue", "not a real bug", "not a defect",
    "not actually a defect", "not actually a bug", "not actually an issue",
    "cosmetic only", "purely cosmetic",
)

# If a finding mentions a concrete consequence, it is NOT noise no matter what else it says — veto the
# drop even at low severity and let the context-aware LLM cleanup decide instead. Deliberately broad
# (incl. functional-defect words like "wrong"/"incorrect"/"silently"/"truncat"): erring toward KEEPING
# a finding is the safe direction — the worst outcome here is showing a low nit, never hiding a bug.
_IMPACT_TOKENS: tuple[str, ...] = (
    "attacker", "inject", "rce", "remote code", "bypass", "leak", "exploit", "overflow",
    "traversal", "dos", "denial of service", "escalat", "takeover", "csrf", "xss", "sqli",
    "ssrf", "arbitrary", "unauthorized", "data loss", "data integrity", "corrupt", "crash", "hijack",
    "truncat", "silently", "race condition", "deadlock", "off-by-one", "incorrect", "wrong",
    "memory leak", "infinite loop", "uninitialized",
)

# Pure style markers; only used to drop a LOW-severity maintainability nit with no concrete impact.
_STYLE_TOKENS: tuple[str, ...] = (
    "naming", "indentation", "whitespace", "typo", "rename", "inconsistent", "readability",
    "docstring", "formatting", "code style", "magic number",
)


def _is_noise(finding: dict[str, str]) -> bool:
    """True only for LOW-severity findings that unambiguously cancel themselves (and mention no
    concrete impact). Critical/high/medium are NEVER dropped here: clearing a real defect to tidy the
    list is far worse than showing the occasional low nit, and medium+ noise is left to the
    context-aware LLM cleanup, which can read the whole sentence.
    """
    if finding.get("severity") != "low":
        return False
    text = ((finding.get("title") or "") + " " + (finding.get("description") or "")).lower()
    if any(tok in text for tok in _IMPACT_TOKENS):
        return False
    if any(phrase in text for phrase in _NOISE_PHRASES):
        return True
    # A LOW maintainability item that reads like pure style (and has no concrete impact) is a nit.
    if finding.get("category") == "maintainability" and any(t in text for t in _STYLE_TOKENS):
        return True
    return False


def apply_noise_backstop(findings: list[dict]) -> list[dict]:
    """Deterministically drop only LOW-severity, self-cancelling noise (see _is_noise). High
    precision by design — never drops a real critical/high/medium defect; never raises."""
    return [f for f in (findings or []) if not _is_noise(f)]


def _env_penalty(name: str, default: str) -> float:
    """Read a tunable penalty from env, tolerating a non-numeric value (falls back + warns) so a typo
    can never crash app import — mirrors _coerce_score/_normalize_weight hardening of external input."""
    try:
        return max(0.0, float(os.getenv(name, default)))
    except (TypeError, ValueError):
        logger.warning("hackathon: invalid %s=%r, using default %s", name, os.getenv(name), default)
        return float(default)


# Points each finding subtracts from its category's 100-point base, by severity. Tunable via env so
# overall strictness can be dialed without code changes. The values are CLAMPED into severity order
# (critical >= high >= medium >= low >= 0) so a misordered override can't break the monotonicity
# guarantee — downgrading a finding must never raise its penalty.
_pen_low = _env_penalty("HACKATHON_PENALTY_LOW", "3")
_pen_med = max(_env_penalty("HACKATHON_PENALTY_MEDIUM", "8"), _pen_low)
_pen_high = max(_env_penalty("HACKATHON_PENALTY_HIGH", "18"), _pen_med)
_pen_crit = max(_env_penalty("HACKATHON_PENALTY_CRITICAL", "30"), _pen_high)
_FINDING_PENALTY: dict[str, float] = {
    "critical": _pen_crit, "high": _pen_high, "medium": _pen_med, "low": _pen_low,
}


def _effective_category(category: str) -> str:
    """The category a finding is scored under: itself if one of the six, else 'correctness' (so an
    unknown/hallucinated category still lands in a real, visible bucket)."""
    return category if category in CATEGORIES else "correctness"


def _drop_unweighted_findings(findings: list[dict], rubric: dict[str, int]) -> list[dict]:
    """Drop findings whose scoring category has rubric weight 0. A team that weights a dimension at 0
    has explicitly chosen not to grade it, so those findings neither move the score (the weighted
    average already excludes weight-0 categories) nor belong in the displayed list. No-op when the
    rubric has no positive weights at all (score then falls back to a plain six-category average)."""
    rubric = rubric or {}
    if not any(_normalize_weight(w) > 0 for w in rubric.values()):
        return findings
    return [
        f for f in findings
        if _normalize_weight(rubric.get(_effective_category(f.get("category", "")), 0)) > 0
    ]


def score_from_findings(
    findings: list[dict],
    rubric: dict[str, int],
    model_breakdown: dict[str, Any] | None = None,
) -> tuple[int, dict[str, dict[str, int]]]:
    """Compute the OFFICIAL score from the final findings, bounded by the model's holistic read.

    Per category: start at 100, subtract _FINDING_PENALTY per finding by severity, then cap at the
    model's own category score (the holistic CEILING). The overall is the rubric-weighted average of
    the six category scores (plain average if all weights are 0).

    Why the ceiling: a pure 100-minus-penalties score reads an empty findings list as a perfect 100,
    which would inflate a mediocre or mostly-FAILED analysis (the model scored low but found nothing
    concrete) to 100. Capping at the model's score prevents that. It still preserves the two
    properties we care about — the ceiling is fixed w.r.t. the findings, so:
      * MONOTONIC: removing or downgrading a finding lowers its penalty -> (100-penalty) rises ->
        min(ceiling, rises) can only rise or stay. Fixing a defect never lowers the grade.
      * TRANSPARENT: the overall is exactly the rubric-weighted average of the displayed per-category
        scores (no hidden term), so a team can reconcile its grade with the breakdown.
    An unknown finding category folds into 'correctness' so its penalty stays visible and diluted.
    Returns (overall, score_breakdown).
    """
    rubric = rubric or {}
    model_breakdown = model_breakdown or {}
    penalties: dict[str, float] = {cat: 0.0 for cat in CATEGORIES}
    for finding in findings or []:
        pen = _FINDING_PENALTY.get(finding.get("severity", "low"), _FINDING_PENALTY["low"])
        penalties[_effective_category(finding.get("category", ""))] += pen

    breakdown: dict[str, dict[str, int]] = {}
    for cat in CATEGORIES:
        penalty_score = max(0, min(100, round(100 - penalties[cat])))
        ceiling = 100
        entry = model_breakdown.get(cat)
        if isinstance(entry, dict) and entry.get("score") is not None:
            ceiling = _coerce_score(entry.get("score"))
        cat_score = min(penalty_score, ceiling)
        breakdown[cat] = {"score": cat_score, "weight": _normalize_weight(rubric.get(cat, 0))}

    total_weight = sum(b["weight"] for b in breakdown.values())
    if total_weight > 0:
        overall = sum(b["score"] * b["weight"] for b in breakdown.values()) / total_weight
    else:
        overall = sum(b["score"] for b in breakdown.values()) / len(CATEGORIES)
    return max(0, min(100, round(overall))), breakdown


def _was_analyzed(result: dict[str, Any]) -> bool:
    """True if the audit produced real signal — at least one scored category or any finding.

    Distinguishes a CLEAN repo (no findings but the model scored its categories → grade it, capped at
    the model's holistic read) from NO-SOURCE / total failure (all category scores 0 and no findings
    → keep the zero result). Combined with the model-score ceiling in score_from_findings, an empty
    findings list can never inflate a low or failed analysis to 100.
    """
    breakdown = result.get("score_breakdown") or {}
    for entry in breakdown.values():
        if isinstance(entry, dict):
            score = entry.get("score")
            if isinstance(score, (int, float)) and score > 0:
                return True
    return bool(result.get("findings"))


def finalize_result(result: dict[str, Any], rubric: dict[str, int]) -> dict[str, Any]:
    """Shared final stage for normal + batch. Cleans the findings (LLM cleanup -> deterministic
    noise backstop) and OVERRIDES score/score_breakdown with the deterministic score-from-findings.

    Only runs when the audit produced real signal (see _was_analyzed); a no-source/total-failure
    result is returned unchanged so its zero score is preserved. Mutates and returns `result`.
    """
    if not _was_analyzed(result):
        return result
    # Capture the model's holistic per-category scores BEFORE overwriting — they become the ceiling.
    model_breakdown = result.get("score_breakdown") or {}
    # Defensive: every real pipeline result carries a populated breakdown (reduce_chunk_scores emits
    # all six categories). If findings exist with no breakdown, the ceiling would default to 100 and
    # could inflate — surface the anomaly rather than silently grade high.
    if result.get("findings") and not model_breakdown:
        logger.warning("hackathon: findings present but score_breakdown empty — score ceiling unbounded")
    findings = apply_noise_backstop(cleanup_findings(result.get("findings") or []))
    # A category weighted 0 in the rubric isn't graded, so drop its findings entirely — they neither
    # affect the score nor belong in the list (the displayed findings then match what's scored).
    findings = _drop_unweighted_findings(findings, rubric or {})
    score, breakdown = score_from_findings(findings, rubric or {}, model_breakdown)
    result["findings"] = findings
    result["score"] = score
    result["score_breakdown"] = breakdown
    return result


# ─────────────────────────────────────────────────────────────────────────────
# BATCH (Anthropic Message Batches) — submit + finalize
# ─────────────────────────────────────────────────────────────────────────────

def submit_batch(
    files: dict[str, str],
    rubric: dict[str, int],
    *,
    verify: bool = False,
    repo_url: str = "",
    ref: str = "main",
) -> tuple[str | None, dict[str, Any]]:
    """Submit one Anthropic Message Batch request per chunk and return (batch_id, batch_meta).

    batch_meta = {"n_chunks":N, "chunks":[{"idx":i,"char_len":len}], "rubric":rubric,
                  "verify":bool, "repo_url":str, "ref":str}.
    The verify/repo_url/ref keys let finalize_batch re-fetch the source and run the high-fidelity
    verification pass later. Uses the configured _AUDIT_MODEL. If there are no files, returns
    (None, meta) with n_chunks=0 so the caller can short-circuit.
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
        "verify": bool(verify),
        "repo_url": repo_url,
        "ref": ref,
    }
    if not chunks:
        return None, batch_meta

    requests = [
        Request(
            custom_id=f"chunk-{i}",
            params=MessageCreateParamsNonStreaming(
                model=_AUDIT_MODEL,
                max_tokens=_BATCH_MAX_TOKENS,
                temperature=0,  # reproducible, comparable grades across submissions
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

    result = reduce_chunk_scores(chunk_results, weights, rubric)

    # High-fidelity verification: re-fetch the source and adversarially re-judge critical/high
    # findings. Scores are untouched; on any fetch/verify failure we keep the reduced findings.
    if batch_meta.get("verify"):
        try:
            files = fetch_repo_source(
                batch_meta.get("repo_url", ""), batch_meta.get("ref", "main")
            )
            result["findings"] = verify_findings_pass(files, result["findings"])
        except Exception as exc:
            logger.info("Batch verify skipped for %s: %s", batch_id, exc)

    # Final stage: LLM cleanup + deterministic noise backstop, then recompute the OFFICIAL score
    # deterministically from the cleaned findings (monotonic, reproducible, traceable).
    return finalize_result(result, rubric)
