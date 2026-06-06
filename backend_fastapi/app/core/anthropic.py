import os

import anthropic
from dotenv import load_dotenv

from app.core.ai_cost import log_usage

load_dotenv()

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

_MODEL = "claude-haiku-4-5"


def generate_content(prompt: str, model_name: str = _MODEL, json_mode: bool = False, label: str = "generate_content", max_tokens: int = 4096) -> str:
    system = "Respond only with valid JSON. Do not include markdown, code fences, or any other text." if json_mode else "You are a helpful assistant."

    message = _client.messages.create(
        model=model_name,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    # Record exact token usage + estimated cost (used to derive C = cost per review).
    usage = getattr(message, "usage", None)
    if usage is not None:
        log_usage(label, model_name, usage.input_tokens, usage.output_tokens)
    return message.content[0].text
