"""Token pricing as data + INR cost derivation.

All monetary cost in the system derives from this one table and the single
``usd_to_inr`` rate carried on :class:`~backend.config.settings.Settings`. No
cost may be computed from constants defined elsewhere.
"""

from __future__ import annotations

# USD per 1M tokens, keyed by model id.
# Rates are the published prices for the pinned ANTHROPIC_MODEL (thinking disabled).
# Claude Sonnet 4.6: $3.00 / 1M input, $15.00 / 1M output.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
}

# USD per 1M tokens, keyed by embedding model id.
# OpenAI text-embedding-3-large: $0.13 / 1M tokens.
EMBEDDING_PRICING: dict[str, float] = {
    "text-embedding-3-large": 0.13,
}

_TOKENS_PER_MILLION = 1_000_000


def cost_inr(
    model: str,
    input_tokens: int,
    output_tokens: int,
    usd_to_inr: float,
) -> float:
    """Return the INR cost for a single model call.

    ``(input_tokens/1e6 * input_rate + output_tokens/1e6 * output_rate) * usd_to_inr``

    Raises ``KeyError`` if ``model`` is absent from :data:`MODEL_PRICING` — a
    missing rate is a bug, not a silent zero.
    """

    rates = MODEL_PRICING[model]
    usd = (
        input_tokens / _TOKENS_PER_MILLION * rates["input"]
        + output_tokens / _TOKENS_PER_MILLION * rates["output"]
    )
    return usd * usd_to_inr
