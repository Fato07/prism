"""Treasury event schema for USYC park/unpark tracking."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TreasuryEvent(BaseModel):
    """A treasury event recording a USDC↔USYC park or unpark operation."""

    id: UUID
    agent_id: int = Field(ge=0)
    wallet_address: str
    event_type: Literal["park", "unpark"]
    usdc_amount: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    usyc_amount: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    rationale: str | None = None
    tx_hash: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class TreasuryEventCreate(BaseModel):
    """Payload for creating a new treasury event (id and created_at are DB-generated)."""

    agent_id: int = Field(ge=0)
    wallet_address: str
    event_type: Literal["park", "unpark"]
    usdc_amount: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    usyc_amount: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    rationale: str | None = None
    tx_hash: str | None = None


class TreasuryEventResult(BaseModel):
    """Result of a treasury park/unpark operation, returned by the treasury module."""

    event_id: str
    event_type: Literal["park", "unpark"]
    usdc_amount: Decimal = Field(max_digits=20, decimal_places=6)
    tx_hash: str | None = None
    rationale: str
    dry_run: bool = False
