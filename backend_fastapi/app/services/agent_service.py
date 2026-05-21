import json
from typing import Any

from app.core.anthropic import generate_content

_STYLE_INSTRUCTIONS: dict[str, str] = {
    "standard": (
        "Apply general best practices: readability, maintainability, naming conventions, "
        "code duplication, and proper error handling."
    ),
    "clean_code": (
        "Apply Clean Code and SOLID principles strictly. Flag violations of Single Responsibility, "
        "Open/Closed, Liskov Substitution, Interface Segregation, and Dependency Inversion. "
        "Flag long methods, large classes, magic numbers, and poor naming."
    ),
    "tdd": (
        "Focus on test coverage. Check whether new code is accompanied by unit or integration tests. "
        "Flag missing test cases, untested edge cases, and poor test structure (e.g. no assertions, "
        "testing implementation details instead of behaviour)."
    ),
    "security": (
        "Apply OWASP Top 10 guidelines. Flag SQL injection risks, missing input validation, "
        "hardcoded secrets, insecure direct object references, improper authentication/authorization, "
        "and exposure of sensitive data."
    ),
    "performance": (
        "Focus on performance and efficiency. Flag N+1 queries, missing indexes, blocking I/O in "
        "async contexts, unnecessary loops, large memory allocations, and missing caching opportunities."
    ),
}

_STRICT_PROMPT = """\
You are a precise code review assistant focused exclusively on user story compliance.

## User Stories for this project:
{stories}

## Active warnings on these stories (issues flagged in previous pushes):
{warnings}

## Code changes (diff):
{diff}

## Instructions:
Your ONLY job is to determine whether each user story is addressed by the code changes, \
based strictly on the story title, description, and acceptance criteria.

Rules:
- Do NOT suggest general code quality improvements, refactors, or best practices.
- Only flag warnings if the code FAILS to implement a specific requirement stated in the story.
- If a story has no explicit acceptance criteria, use the description to judge completeness.
- If the code resolves an existing warning for a story, list its ID in "resolved_warning_ids".
- Extract the most relevant code snippet (file path + changed lines, max 300 lines).

Respond ONLY with valid JSON:
{{
  "matches": [
    {{
      "story_id": <integer>,
      "story_title": "<string>",
      "coverage": "full",
      "reason": "<why the story requirements are fully met>",
      "code_snippet": "<relevant diff lines with file path>",
      "new_warnings": [],
      "resolved_warning_ids": []
    }},
    {{
      "story_id": <integer>,
      "story_title": "<string>",
      "coverage": "partial",
      "reason": "<which specific requirements from the story are not yet implemented>",
      "code_snippet": "<relevant diff lines with file path>",
      "new_warnings": ["<missing requirement 1>", "<missing requirement 2>"],
      "resolved_warning_ids": []
    }}
  ],
  "unaddressed_note": "<optional note>"
}}

If no stories match the changes, return:
{{"matches": [], "unaddressed_note": "No user stories seem to be addressed by these changes."}}
"""

_GENERAL_PROMPT = """\
You are an expert code reviewer and project manager assistant.

## Coding style guidelines for this project:
{style_instructions}

## User Stories for this project:
{stories}

## Active warnings on these stories (issues flagged in previous pushes):
{warnings}

## Code changes (diff):
{diff}

## Instructions:
Analyze the code changes and determine which user stories are being addressed.
For each matched story:
1. Assess if it is fully or partially implemented based on the story description and acceptance criteria.
2. Apply the coding style guidelines above when evaluating code quality.
3. Provide concrete, actionable warnings for: missing story requirements AND code quality issues.
4. If the new code resolves any existing warning, list its ID in "resolved_warning_ids".
5. Only flag NEW warnings not already listed in the active warnings.
6. Extract the most relevant code snippet (file path + changed lines, max 300 lines).

Respond ONLY with valid JSON:
{{
  "matches": [
    {{
      "story_id": <integer>,
      "story_title": "<string>",
      "coverage": "full",
      "reason": "<why this story is addressed>",
      "code_snippet": "<relevant diff lines with file path>",
      "new_warnings": [],
      "resolved_warning_ids": []
    }},
    {{
      "story_id": <integer>,
      "story_title": "<string>",
      "coverage": "partial",
      "reason": "<why this story is only partially addressed>",
      "code_snippet": "<relevant diff lines with file path>",
      "new_warnings": ["<issue 1>", "<issue 2>"],
      "resolved_warning_ids": [<warning_id_if_resolved>]
    }}
  ],
  "unaddressed_note": "<optional general note>"
}}

If no stories match the changes, return:
{{"matches": [], "unaddressed_note": "No user stories seem to be addressed by these changes."}}
"""

_MAX_DIFF_CHARS = 30_000


def analyze_push(
    stories: list[dict[str, Any]],
    diff: str,
    active_warnings: dict[int, list[dict[str, Any]]] | None = None,
    coding_style: str = "standard",
    review_focus: str = "general",
) -> dict[str, Any]:
    """Send stories + diff to Claude and return structured analysis.

    Args:
        stories: List of active user stories with id, title, description.
        diff: Git diff string from the push.
        active_warnings: Existing warnings per story id.
        coding_style: One of standard / clean_code / tdd / security / performance.
        review_focus: 'strict' (story compliance only) or 'general' (story + code quality).
    """
    stories_text = "\n".join(
        f"- ID {s['id']}: {s['title']}\n  Description: {s['description'] or 'No description provided.'}"
        for s in stories
    )

    if active_warnings:
        warnings_lines = []
        for story_id, warns in active_warnings.items():
            for w in warns:
                warnings_lines.append(
                    f"- Warning ID {w['id']} on Story {story_id}: {w['message']}"
                )
        warnings_text = "\n".join(warnings_lines) if warnings_lines else "None."
    else:
        warnings_text = "None."

    truncated_diff = diff[:_MAX_DIFF_CHARS]

    if review_focus == "strict":
        prompt = _STRICT_PROMPT.format(
            stories=stories_text,
            warnings=warnings_text,
            diff=truncated_diff,
        )
    else:
        style_instructions = _STYLE_INSTRUCTIONS.get(coding_style, _STYLE_INSTRUCTIONS["standard"])
        prompt = _GENERAL_PROMPT.format(
            style_instructions=style_instructions,
            stories=stories_text,
            warnings=warnings_text,
            diff=truncated_diff,
        )

    text = generate_content(prompt, json_mode=True).strip()

    # Strip markdown code fences if model ignored json_mode
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:].strip()

    # Find outermost JSON object in case of extra text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]

    return json.loads(text)
