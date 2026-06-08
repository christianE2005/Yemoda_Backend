import os

import anthropic
from dotenv import load_dotenv

from app.core.ai_cost import log_usage

load_dotenv()

# Survive transient per-minute rate-limit (429) spikes on low tiers: the SDK honors the
# retry-after header and backs off exponentially (~1s,2s,4s,8s,16s,32s), so a single audit whose
# chunks briefly exceed the per-minute token quota waits out the reset instead of failing the
# submission. Sustained load still needs a higher tier or batch mode. Tunable via ANTHROPIC_MAX_RETRIES.
_client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    max_retries=int(os.getenv("ANTHROPIC_MAX_RETRIES", "6")),
)

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
    # The first block isn't guaranteed to be text (e.g. tool_use); concatenate all text
    # blocks and tolerate empty content.
    return "".join(getattr(block, "text", "") or "" for block in (message.content or []))
