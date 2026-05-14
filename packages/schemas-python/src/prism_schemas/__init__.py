"""Prism shared Pydantic schemas and startup validation."""

from prism_schemas.agent_card import AgentCard, AgentCardService, X402Support
from prism_schemas.startup import (
    POLYMARKET_RESTRICTED_COUNTRIES,
    REQUIRED_COMMON,
    REQUIRED_ORACLE,
    REQUIRED_SENTINEL,
    REQUIRED_TRADER,
    check_geofence,
    startup_check,
    validate_env,
)
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.treasury import TreasuryEvent, TreasuryEventCreate, TreasuryEventResult
from prism_schemas.verdict import SentinelVerdict

__all__ = [
    # Agent card
    "AgentCard",
    "AgentCardService",
    "X402Support",
    # Startup validation
    "POLYMARKET_RESTRICTED_COUNTRIES",
    "REQUIRED_COMMON",
    "REQUIRED_ORACLE",
    "REQUIRED_SENTINEL",
    "REQUIRED_TRADER",
    "check_geofence",
    "startup_check",
    "validate_env",
    # Trace
    "Evidence",
    "ThesisStep",
    "TradingR1Trace",
    # Treasury
    "TreasuryEvent",
    "TreasuryEventCreate",
    "TreasuryEventResult",
    # Verdict
    "SentinelVerdict",
]
