import json
from typing import Any

from app.core.gemini import get_gemini_model

_PROMPT_TEMPLATE = """\
You are an expert code reviewer and project manager assistant.

## User Stories for this project:
{stories}

## Code changes (diff):
{diff}

## Instructions:
Analyze the code changes and determine which user stories are being addressed.
For each matched story:
1. Assess if it is fully or partially implemented based on the story description.
2. If partial, provide concrete, actionable suggestions about what is missing.

Respond ONLY with valid JSON using this exact format:
{{
  "matches": [
    {{
      "story_id": <integer>,
      "story_title": "<string>",
      "coverage": "full",
      "reason": "<why this story is addressed by the diff>",
      "suggestions": []
    }},
    {{
      "story_id": <integer>,
      "story_title": "<string>",
      "coverage": "partial",
      "reason": "<why this story is only partially addressed>",
      "suggestions": ["<actionable suggestion 1>", "<actionable suggestion 2>"]
    }}
  ],
  "unaddressed_note": "<optional general note>"
}}

If no stories match the changes, return:
{{"matches": [], "unaddressed_note": "No user stories seem to be addressed by these changes."}}
"""

# Max diff size sent to Gemini to stay within token limits
_MAX_DIFF_CHARS = 10_000


def analyze_push(stories: list[dict[str, Any]], diff: str) -> dict[str, Any]:
    """Send stories + diff to Gemini and return structured analysis."""
    stories_text = "\n".join(
        f"- ID {s['id']}: {s['title']}\n  Description: {s['description'] or 'No description provided.'}"
        for s in stories
    )

    prompt = _PROMPT_TEMPLATE.format(
        stories=stories_text,
        diff=diff[:_MAX_DIFF_CHARS],
    )

    model = get_gemini_model()
    response = model.generate_content(prompt)

    text = response.text.strip()
    # Strip markdown code fences if Gemini wraps the JSON
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:].strip()

    return json.loads(text)
