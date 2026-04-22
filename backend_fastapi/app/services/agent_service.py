import json
from typing import Any

from app.core.gemini import generate_content

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
    """Send stories + diff + active warnings to Gemini and return structured analysis."""
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

    text = generate_content(prompt).strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:].strip()

    return json.loads(text)
