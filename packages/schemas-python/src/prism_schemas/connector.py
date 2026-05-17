"""Connector Passport v1 schemas for Prism Tool Connectors."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


ToolConnectorTransport = Literal[
    "mcp_http",
    "x402_http",
    "custom_webhook",
    "direct_adapter",
]
ToolConnectorSmokeStatus = Literal["not_run", "passed", "failed"]


class ToolConnectorSmokeReceipt(BaseModel):
    """Redacted proof that a connector passed or failed a smoke check."""

    status: ToolConnectorSmokeStatus
    checked_at: datetime
    transport_ok: bool
    tool_reachable: bool
    schema_ok: bool
    mapper_ok: bool
    fail_closed_ok: bool
    cost_cap_ok: bool
    evidence_count: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_message: str | None = None


class ToolConnector(BaseModel):
    """Database row for a Connector Passport v1 record."""

    id: UUID
    owner_scope: Literal["workspace"] = "workspace"
    connector_kind: Literal["evidence"] = "evidence"
    name: str
    transport: ToolConnectorTransport
    provider: str = "mcp"
    server_url: str | None = None
    tool_name: str | None = None
    input_mapper: str = "query"
    result_mapper: str = "generic_search"
    allowed_tools: list[str] = Field(default_factory=list)
    timeout_seconds: Decimal = Field(gt=0)
    max_results: int = Field(ge=1, le=20)
    max_usdc: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    auth_secret_ciphertext: str | None = None
    auth_secret_hint: str | None = None
    smoke_status: ToolConnectorSmokeStatus = "not_run"
    smoke_receipt: ToolConnectorSmokeReceipt | None = None
    armed: bool = False
    fail_closed: bool = True
    created_at: datetime
    updated_at: datetime
