"""Startup environment validation — backward-compatible re-export.

The canonical implementations live in prism_schemas.startup.
This module re-exports them so that existing ``from trader.config import ...``
calls continue to work without changes.
"""

from __future__ import annotations

# Re-export everything from the shared package for backward compatibility.
from prism_schemas.startup import (  # noqa: F401
    POLYMARKET_RESTRICTED_COUNTRIES,
    REQUIRED_COMMON,
    REQUIRED_ORACLE,
    REQUIRED_SENTINEL,
    REQUIRED_TRADER,
    _is_claude_family,
    _is_gpt_family,
    _validate_llm_family,
    check_geofence,
    startup_check,
    validate_env,
)
