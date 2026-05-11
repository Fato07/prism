"""Startup environment validation module.

Validates that all required environment variables are present and
produces clear error messages naming the specific missing var.
Each service should call validate_env() at startup.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = structlog.get_logger("prism.trader.config")

# Required env vars per service role
REQUIRED_COMMON = [
    "DATABASE_URL",
    "CIRCLE_API_KEY",
    "CIRCLE_ENTITY_SECRET",
    "CIRCLE_WALLET_SET_ID",
    "PINATA_JWT",
    "ARC_RPC_URL",
]

REQUIRED_TRADER = REQUIRED_COMMON + [
    "ANTHROPIC_API_KEY",
    "CIRCLE_WALLET_TRADER_ID",
    "CIRCLE_WALLET_TRADER_ADDRESS",
]

REQUIRED_SENTINEL = REQUIRED_COMMON + [
    "OPENAI_API_KEY",
    "CIRCLE_WALLET_SENTINEL_ID",
    "CIRCLE_WALLET_SENTINEL_ADDRESS",
]

REQUIRED_ORACLE = REQUIRED_COMMON + [
    "CIRCLE_WALLET_ORACLE_ID",
    "CIRCLE_WALLET_ORACLE_ADDRESS",
]

# Polymarket's restricted countries (33 total, as of April 2026).
# Source: https://help.polymarket.com/en/articles/13364163-geographic-restrictions
# Estonia (EE) is NOT in this list — it is explicitly allowed per MISSION.md.
POLYMARKET_RESTRICTED_COUNTRIES = frozenset(
    {
        "AU",  # Australia
        "BE",  # Belgium
        "BY",  # Belarus
        "BI",  # Burundi
        "CF",  # Central African Republic
        "CD",  # Congo (Kinshasa)
        "CU",  # Cuba
        "DE",  # Germany
        "ET",  # Ethiopia
        "FR",  # France
        "GB",  # United Kingdom
        "IR",  # Iran
        "IQ",  # Iraq
        "IT",  # Italy
        "JP",  # Japan
        "KP",  # North Korea
        "LB",  # Lebanon
        "LY",  # Libya
        "MM",  # Myanmar
        "NI",  # Nicaragua
        "PL",  # Poland
        "RU",  # Russia
        "SG",  # Singapore
        "SO",  # Somalia
        "SS",  # South Sudan
        "SD",  # Sudan
        "SY",  # Syria
        "TH",  # Thailand
        "TW",  # Taiwan
        "US",  # United States
        "VE",  # Venezuela
        "YE",  # Yemen
        "ZW",  # Zimbabwe
    }
)


def validate_env(
    role: str = "trader",
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Validate required environment variables for the given role.

    Returns a list of missing variable names. Empty list = all present.
    """
    env = env or os.environ
    required_map = {
        "trader": REQUIRED_TRADER,
        "sentinel": REQUIRED_SENTINEL,
        "oracle": REQUIRED_ORACLE,
    }
    required = required_map.get(role, REQUIRED_COMMON)
    missing = [var for var in required if not env.get(var)]
    return missing


def startup_check(role: str = "trader") -> None:
    """Run full startup validation. Exits with non-zero code on failure."""
    missing = validate_env(role)
    if missing:
        logger.error(
            "missing_required_env_vars",
            role=role,
            missing=missing,
        )
        print(
            f"FATAL: Missing required environment variables for {role}: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.info("env_validation_passed", role=role)

    # Validate LLM family separation
    _validate_llm_family(role)


def _validate_llm_family(role: str) -> None:
    """Ensure the configured model matches the expected LLM family."""
    trader_model = os.environ.get("TRADER_MODEL", "claude-sonnet-4-20250514")
    sentinel_model = os.environ.get("SENTINEL_MODEL", "gpt-4o-mini")

    if role == "trader":
        if not _is_claude_family(trader_model):
            logger.error(
                "llm_family_mismatch",
                role=role,
                model=trader_model,
                expected_family="anthropic-claude",
            )
            print(
                f"FATAL: Trader model '{trader_model}' is not in the "
                "anthropic-claude family. Trader must use Claude models.",
                file=sys.stderr,
            )
            sys.exit(1)
        logger.info("llm_family_validated", role=role, family="anthropic-claude")

    if role == "sentinel":
        if not _is_gpt_family(sentinel_model):
            logger.error(
                "llm_family_mismatch",
                role=role,
                model=sentinel_model,
                expected_family="openai-gpt",
            )
            print(
                f"FATAL: Sentinel model '{sentinel_model}' is not in the "
                "openai-gpt family. Sentinel must use GPT models.",
                file=sys.stderr,
            )
            sys.exit(1)
        logger.info("llm_family_validated", role=role, family="openai-gpt")


def _is_claude_family(model: str) -> bool:
    """Check if a model name belongs to the Claude family."""
    model_lower = model.lower()
    return any(k in model_lower for k in ("claude", "anthropic"))


def _is_gpt_family(model: str) -> bool:
    """Check if a model name belongs to the GPT family."""
    model_lower = model.lower()
    return any(k in model_lower for k in ("gpt", "o1", "o3", "o4"))


def check_geofence(locale: str | None = None) -> bool:
    """Check if the configured locale is allowed for Polymarket.

    Returns True if allowed, exits immediately if restricted.
    """
    locale = locale or os.environ.get("LOCALE", "")
    if not locale:
        logger.warning("geofence_check_skipped", reason="LOCALE not set")
        return True

    if locale.upper() in POLYMARKET_RESTRICTED_COUNTRIES:
        logger.error(
            "geofence_check_failed",
            locale=locale.upper(),
        )
        return False

    logger.info("geofence_check_passed", locale=locale.upper())
    return True
