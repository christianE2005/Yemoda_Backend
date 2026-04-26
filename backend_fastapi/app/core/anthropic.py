import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")


def generate_content(prompt: str, model_name: str = _MODEL, json_mode: bool = False) -> str:
    system = "Respond only with valid JSON. Do not include markdown, code fences, or any other text." if json_mode else "You are a helpful assistant."

    message = _client.messages.create(
        model=model_name,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
