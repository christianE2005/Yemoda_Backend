"""
AI usage / cost instrumentation.

Every Claude call records its exact token counts and an estimated USD cost as a
structured log line:

    AI_USAGE label=push_review model=claude-haiku-4-5 input_tokens=8123 output_tokens=412 cost_usd=0.010183

The token counts come straight from the Anthropic API response (`message.usage`) and
are EXACT. The dollar figure is derived from the price table below — verify the current
prices at https://www.anthropic.com/pricing and override per-model at runtime with env
vars (USD per 1M tokens):

    AI_PRICE_CLAUDE_HAIKU_4_5_INPUT=1.0
    AI_PRICE_CLAUDE_HAIKU_4_5_OUTPUT=5.0

To get C (average cost per code review) once a handful of real reviews have run, average
`cost_usd` over the lines with `label=push_review` (see the project README / notes).
"""
import logging
import os

logger = logging.getLogger("ai.usage")

# USD per 1,000,000 tokens, as (input, output). UPDATE to match anthropic.com/pricing.
# Only currently-served models: claude-haiku-4-5 is the product-wide default; the others stay
# listed so an env override (HACKATHON_VERIFY_MODEL etc.) is still costed correctly.
_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6": (5.0, 25.0),
}
# Fallback if an unknown model is used (assume Haiku-tier so we don't under-count badly).
_DEFAULT_PRICE: tuple[float, float] = (1.0, 5.0)


def _price_for(model: str) -> tuple[float, float]:
    """(input, output) USD per 1M tokens, with optional env override per model."""
    base = _PRICING.get(model, _DEFAULT_PRICE)
    key = model.upper().replace("-", "_").replace(".", "_")
    env_in = os.getenv(f"AI_PRICE_{key}_INPUT")
    env_out = os.getenv(f"AI_PRICE_{key}_OUTPUT")
    try:
        price_in = float(env_in) if env_in else base[0]
        price_out = float(env_out) if env_out else base[1]
    except ValueError:
        price_in, price_out = base
    return price_in, price_out


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated USD cost of one Claude call from its token usage."""
    price_in, price_out = _price_for(model)
    return (input_tokens / 1_000_000) * price_in + (output_tokens / 1_000_000) * price_out


def log_usage(label: str, model: str, input_tokens: int, output_tokens: int, **extra: object) -> float:
    """Record exact token usage + estimated cost for one Claude call. Returns the cost."""
    estimated = cost_usd(model, input_tokens, output_tokens)
    extra_fields = " ".join(f"{k}={v}" for k, v in extra.items())
    logger.info(
        "AI_USAGE label=%s model=%s input_tokens=%s output_tokens=%s cost_usd=%.6f %s",
        label,
        model,
        input_tokens,
        output_tokens,
        estimated,
        extra_fields,
    )
    return estimated
