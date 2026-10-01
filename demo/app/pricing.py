"""Model prices for cost_usd, USD per million tokens (base input / output, no caching, no batch).

Source: https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-09-30.
Prices change: re-check before recording lesson 7 and before every cohort.
"""

from __future__ import annotations

PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """None for a model that is not in the table: an unknown price is reported as unknown, not as zero."""
    price = PRICES_PER_MTOK.get(model)
    if price is None:
        return None
    return round((input_tokens * price[0] + output_tokens * price[1]) / 1_000_000, 6)
