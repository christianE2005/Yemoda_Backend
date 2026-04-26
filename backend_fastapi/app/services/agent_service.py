import json
from typing import Any

from app.core.anthropic import generate_content

_PROMPT_TEMPLATE = """\
You are an expert code reviewer and project manager assistant.

## User Stories for this project:
{stories}

## Active warnings on these stories (issues flagged in previous pushes):
{warnings}

## Code changes (diff):
{diff}

## Instructions:
Analyze the code changes and determine which user stories are being addressed.
For each matched story:
1. Assess if it is fully or partially implemented based on the story description.
2. If partial, provide concrete, actionable suggestions about what is missing — these become new warnings.
3. Check the active warnings list: if the new code resolves any existing warning for that story, list its ID in "resolved_warning_ids".
4. Only flag NEW warnings that are not already listed in the active warnings.
5. Extract the most relevant code snippet from the diff that directly addresses this story. Include the file path and the changed lines. Keep it under 300 lines.

Respond ONLY with valid JSON using this exact format:
{{
  "matches": [
    {{
      "story_id": <integer>,
      "story_title": "<string>",
      "coverage": "full",
      "reason": "<why this story is addressed by the diff>",
      "code_snippet": "<relevant diff lines with file path, max 300 lines>",
      "new_warnings": [],
      "resolved_warning_ids": []
    }},
    {{
      "story_id": <integer>,
      "story_title": "<string>",
      "coverage": "partial",
      "reason": "<why this story is only partially addressed>",
      "code_snippet": "<relevant diff lines with file path, max 300 lines>",
      "new_warnings": ["<specific issue 1, e.g. JWT authentication not implemented>", "<specific issue 2>"],
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
) -> dict[str, Any]:
    """Send stories + diff + active warnings to Claude and return structured analysis."""
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

    prompt = _PROMPT_TEMPLATE.format(
        stories=stories_text,
        warnings=warnings_text,
        diff=diff[:_MAX_DIFF_CHARS],
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


# Prompt for analyzing a single story against a diff (returns small JSON)
_STORY_PROMPT_TEMPLATE = """\
You are an expert code reviewer.

User Story:
ID: {story_id}
Title: {title}
Description / Acceptance Criteria: {description}

Active warnings on this story:
{warnings}

Code changes (diff snippet):
{diff}

Instructions:
1) Determine if the provided code changes fully satisfy the acceptance criteria for this single user story.
2) If they fully satisfy the criteria, respond with JSON: {"complies": true, "reason": "<brief explanation>", "new_warnings": [], "resolved_warning_ids": [], "code_snippet": "<relevant lines>"}
3) If they do not satisfy the criteria, respond with JSON: {"complies": false, "reason": "<brief explanation>", "new_warnings": ["<short warning 1>", "<short warning 2>"], "resolved_warning_ids": [], "code_snippet": "<relevant lines>"}

Respond ONLY with valid JSON and nothing else.
"""


def analyze_story(
    story: dict[str, Any],
    diff: str,
    active_warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analyze a single story against a diff using Claude and return structured JSON.

    The returned dict must contain at least: `complies` (bool), `reason` (str),
    `new_warnings` (list[str]), `resolved_warning_ids` (list[int]), `code_snippet` (str).
    """
    warnings_text = "None." if not active_warnings else "\n".join(
        f"- Warning ID {w.get('id')}: {w.get('message')}" for w in active_warnings
    )

    prompt = _STORY_PROMPT_TEMPLATE.format(
        story_id=story.get("id") or story.get("story_id", ""),
        title=story.get("title", "<no title>"),
        description=story.get("description", "No description provided."),
        warnings=warnings_text,
        diff=diff[:_MAX_DIFF_CHARS],
    )

    text = generate_content(prompt, json_mode=True).strip()

    # Strip code fences if any
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:].strip()

    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]

    try:
        parsed = json.loads(text)
    except Exception as exc:
        raise RuntimeError(f"Could not parse JSON from model response: {exc}\nResponse:\n{text}")

    # Normalize fields
    parsed.setdefault("complies", False)
    parsed.setdefault("reason", "")
    parsed.setdefault("new_warnings", [])
    parsed.setdefault("resolved_warning_ids", [])
    parsed.setdefault("code_snippet", None)

    return parsed
