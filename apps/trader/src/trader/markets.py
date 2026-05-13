"""Curated list of market questions for autonomous pipeline runs.

Used by the ``/pipeline`` endpoint to pick a random market question
when no specific one is provided.
"""

from __future__ import annotations

import random

MARKET_QUESTIONS: list[dict[str, str]] = [
    {
        "id": "0xfed_rate_june_2026",
        "question": "Will the Federal Reserve cut interest rates at the June 2026 FOMC meeting?",
    },
    {
        "id": "0xbtc_150k_2026",
        "question": "Will Bitcoin exceed $150,000 before the end of 2026?",
    },
    {
        "id": "0xeu_ai_regulation_2026",
        "question": "Will the EU AI Act enforcement actions exceed 50 by end of 2026?",
    },
    {
        "id": "0xai_agent_market_2026",
        "question": "Will AI agent market cap exceed $10B by end of 2026?",
    },
    {
        "id": "0xopen_source_ai_2026",
        "question": "Will an open-source AI model top the LMSYS leaderboard by December 2026?",
    },
    {
        "id": "0xarc_tvl_2026",
        "question": "Will Arc testnet TVL exceed $500M by end of 2026?",
    },
    {
        "id": "0xpolymarket_volume_2026",
        "question": "Will Polymarket monthly volume exceed $1B in 2026?",
    },
    {
        "id": "0xusdc_supply_2026",
        "question": "Will USDC total supply exceed $100B by end of 2026?",
    },
]


def pick_market() -> dict[str, str]:
    """Return a random market question from the curated list."""
    return random.choice(MARKET_QUESTIONS)
