"""Diagnostics for the Prism CLI developer environment."""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from prism_cli.config import CliConfig

DoctorStatus = Literal["ok", "warn", "fail", "skip"]
OverallStatus = Literal["ok", "warn", "fail"]
RunFn = Callable[..., subprocess.CompletedProcess[str]]


class DoctorCheck(BaseModel):
    """Single Prism doctor check result."""

    id: str
    label: str
    status: DoctorStatus
    detail: str
    remediation: str | None = None


class DoctorReport(BaseModel):
    """Complete Prism doctor report."""

    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    overall_status: OverallStatus
    checks: list[DoctorCheck]


async def run_doctor(config: CliConfig, *, include_circle: bool = True) -> DoctorReport:
    """Run Prism service and local Circle CLI diagnostics."""
    checks: list[DoctorCheck] = []

    service_results = await asyncio.gather(
        _check_dashboard(config),
        _check_sentinel_health(config),
        _check_sentinel_mcp(config),
        _check_polymarket_gateway(config),
    )
    checks.extend(service_results)

    if include_circle:
        checks.extend(await asyncio.to_thread(run_circle_diagnostics, config.timeout_seconds))
    else:
        checks.append(
            DoctorCheck(
                id="circle_checks",
                label="Circle CLI checks",
                status="skip",
                detail="Skipped by --no-circle.",
            )
        )

    return DoctorReport(overall_status=_overall_status(checks), checks=checks)


def run_circle_diagnostics(
    timeout_seconds: float = 10.0,
    *,
    run: RunFn = subprocess.run,
) -> list[DoctorCheck]:
    """Run local Circle CLI checks for Prism's Base Sepolia x402 payment path."""
    checks: list[DoctorCheck] = []

    try:
        status_result = run(
            ["circle", "wallet", "status", "--type", "agent", "--output", "json"],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return [
            DoctorCheck(
                id="circle_cli",
                label="Circle CLI",
                status="fail",
                detail="circle command not found.",
                remediation="Install Circle CLI, then run `circle wallet status`.",
            )
        ]
    except subprocess.TimeoutExpired:
        return [
            DoctorCheck(
                id="circle_cli",
                label="Circle CLI",
                status="fail",
                detail=f"circle wallet status timed out after {timeout_seconds:g}s.",
                remediation="Run `circle wallet status` in an interactive terminal.",
            )
        ]

    status_payload = _parse_json_payload(status_result.stdout)
    email = _email_from_status(status_payload)
    if status_result.returncode != 0:
        checks.append(
            DoctorCheck(
                id="circle_cli",
                label="Circle CLI",
                status="fail",
                detail=_command_error_detail(status_result, "Circle agent wallet status failed."),
                remediation="Run `circle wallet login <email> --testnet` and retry.",
            )
        )
        return checks

    session_detail = (
        f"Agent wallet session found for {email}." if email else "Agent wallet session found."
    )
    checks.append(
        DoctorCheck(
            id="circle_cli",
            label="Circle CLI",
            status="ok",
            detail=session_detail,
        )
    )

    try:
        list_result = run(
            [
                "circle",
                "wallet",
                "list",
                "--chain",
                "BASE-SEPOLIA",
                "--type",
                "agent",
                "--output",
                "json",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        checks.append(
            DoctorCheck(
                id="circle_base_sepolia_login",
                label="Circle Base Sepolia login",
                status="fail",
                detail="circle command disappeared before Base Sepolia wallet check.",
                remediation="Install Circle CLI, then run `circle wallet status`.",
            )
        )
        return checks
    except subprocess.TimeoutExpired:
        checks.append(
            DoctorCheck(
                id="circle_base_sepolia_login",
                label="Circle Base Sepolia login",
                status="fail",
                detail=f"circle wallet list BASE-SEPOLIA timed out after {timeout_seconds:g}s.",
                remediation="Run `circle wallet status --type agent --output json` interactively.",
            )
        )
        return checks

    list_payload = _parse_json_payload(list_result.stdout)
    error_code = _nested_str(list_payload, "error", "code")
    error_message = _nested_str(list_payload, "error", "message")
    login_command = (
        f"circle wallet login {email} --testnet"
        if email
        else "circle wallet login <email> --testnet"
    )

    if list_result.returncode != 0:
        if error_code == "AUTH_REQUIRED":
            checks.append(
                DoctorCheck(
                    id="circle_base_sepolia_login",
                    label="Circle Base Sepolia login",
                    status="fail",
                    detail=error_message or "Base Sepolia/testnet Circle session is missing.",
                    remediation=login_command,
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    id="circle_base_sepolia_login",
                    label="Circle Base Sepolia login",
                    status="fail",
                    detail=_command_error_detail(
                        list_result,
                        "Could not list Base Sepolia wallets.",
                    ),
                    remediation=login_command,
                )
            )
        return checks

    checks.append(
        DoctorCheck(
            id="circle_base_sepolia_login",
            label="Circle Base Sepolia login",
            status="ok",
            detail="Circle testnet session can list Base Sepolia agent wallets.",
        )
    )

    wallets = _wallets_from_list_payload(list_payload)
    if wallets:
        checks.append(
            DoctorCheck(
                id="circle_base_sepolia_wallet",
                label="Circle Base Sepolia wallet",
                status="ok",
                detail=f"Found {len(wallets)} Base Sepolia agent wallet(s).",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                id="circle_base_sepolia_wallet",
                label="Circle Base Sepolia wallet",
                status="fail",
                detail="No Base Sepolia agent wallets found; paid validation cannot run yet.",
                remediation=(
                    "Run `circle wallet create --output json`, then fund Base Sepolia USDC."
                ),
            )
        )

    return checks


async def _check_dashboard(config: CliConfig) -> DoctorCheck:
    """Check the public dashboard stats API."""
    url = f"{config.normalized_dashboard_url()}/api/public/stats"
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.get(url)
        if response.status_code == 200:
            return DoctorCheck(
                id="dashboard_api",
                label="Dashboard public API",
                status="ok",
                detail="/api/public/stats returned 200.",
            )
        return DoctorCheck(
            id="dashboard_api",
            label="Dashboard public API",
            status="fail",
            detail=f"/api/public/stats returned HTTP {response.status_code}.",
        )
    except httpx.HTTPError as exc:
        return DoctorCheck(
            id="dashboard_api",
            label="Dashboard public API",
            status="fail",
            detail=f"Dashboard request failed: {exc}",
        )


async def _check_sentinel_health(config: CliConfig) -> DoctorCheck:
    """Check sentinel liveness."""
    url = f"{_sentinel_origin(config)}/health"
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.get(url)
        if response.status_code == 200:
            return DoctorCheck(
                id="sentinel_health",
                label="Sentinel health",
                status="ok",
                detail="/health returned 200.",
            )
        return DoctorCheck(
            id="sentinel_health",
            label="Sentinel health",
            status="fail",
            detail=f"/health returned HTTP {response.status_code}.",
        )
    except httpx.HTTPError as exc:
        return DoctorCheck(
            id="sentinel_health",
            label="Sentinel health",
            status="fail",
            detail=f"Sentinel health request failed: {exc}",
        )


async def _check_sentinel_mcp(config: CliConfig) -> DoctorCheck:
    """Check the free MCP initialize path without making a paid tools/call."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(config.timeout_seconds),
        ) as client:
            init_response = await client.post(
                config.normalized_sentinel_url(),
                json={
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"experimental": {}, "sampling": {}},
                        "clientInfo": {"name": "prism-doctor", "version": "0.1.0"},
                    },
                },
                headers=_mcp_headers(),
            )
            session_id = init_response.headers.get("mcp-session-id")
            if init_response.status_code != 200 or not session_id:
                return DoctorCheck(
                    id="sentinel_mcp",
                    label="Sentinel MCP handshake",
                    status="fail",
                    detail=(
                        f"MCP initialize returned HTTP {init_response.status_code} "
                        "without a session."
                    ),
                    remediation="Use the canonical /mcp/ URL with trailing slash.",
                )
            initialized_response = await client.post(
                config.normalized_sentinel_url(),
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers={**_mcp_headers(), "mcp-session-id": session_id},
            )
        if initialized_response.status_code in (200, 202):
            return DoctorCheck(
                id="sentinel_mcp",
                label="Sentinel MCP handshake",
                status="ok",
                detail="MCP initialize + notifications/initialized succeeded.",
            )
        return DoctorCheck(
            id="sentinel_mcp",
            label="Sentinel MCP handshake",
            status="fail",
            detail=f"notifications/initialized returned HTTP {initialized_response.status_code}.",
        )
    except httpx.HTTPError as exc:
        return DoctorCheck(
            id="sentinel_mcp",
            label="Sentinel MCP handshake",
            status="fail",
            detail=f"MCP handshake failed: {exc}",
        )


async def _check_polymarket_gateway(config: CliConfig) -> DoctorCheck:
    """Check Polymarket gateway liveness."""
    url = f"{config.normalized_polymarket_gateway_url()}/health"
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.get(url)
        if response.status_code == 200:
            return DoctorCheck(
                id="polymarket_gateway",
                label="Polymarket gateway",
                status="ok",
                detail="/health returned 200.",
            )
        return DoctorCheck(
            id="polymarket_gateway",
            label="Polymarket gateway",
            status="fail",
            detail=f"/health returned HTTP {response.status_code}.",
        )
    except httpx.HTTPError as exc:
        return DoctorCheck(
            id="polymarket_gateway",
            label="Polymarket gateway",
            status="fail",
            detail=f"Gateway request failed: {exc}",
        )


def _overall_status(checks: list[DoctorCheck]) -> OverallStatus:
    """Reduce individual check statuses to an overall status."""
    if any(check.status == "fail" for check in checks):
        return "fail"
    if any(check.status == "warn" for check in checks):
        return "warn"
    return "ok"


def _sentinel_origin(config: CliConfig) -> str:
    """Return the scheme+host origin from the sentinel MCP URL."""
    parsed = urlparse(config.normalized_sentinel_url())
    return f"{parsed.scheme}://{parsed.netloc}"


def _mcp_headers() -> dict[str, str]:
    """Headers accepted by the streamable HTTP MCP transport."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }


def _parse_json_payload(raw: str) -> dict[str, Any]:
    """Parse JSON from command stdout, tolerating leading non-JSON noise."""
    if not raw.strip():
        return {}
    start = raw.find("{")
    if start < 0:
        return {}
    try:
        parsed = json.loads(raw[start:])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _email_from_status(payload: dict[str, Any]) -> str | None:
    """Extract Circle account email from wallet status JSON."""
    return _nested_str(payload, "data", "email")


def _wallets_from_list_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract wallet list from Circle wallet list JSON."""
    data = payload.get("data")
    wallets = data.get("wallets") if isinstance(data, dict) else []
    if not isinstance(wallets, list):
        return []
    return [wallet for wallet in wallets if isinstance(wallet, dict)]


def _nested_str(payload: dict[str, Any], *keys: str) -> str | None:
    """Return a nested string value from a mapping."""
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, str) else None


def _command_error_detail(result: subprocess.CompletedProcess[str], fallback: str) -> str:
    """Return a useful command error message."""
    payload = _parse_json_payload(result.stdout)
    message = _nested_str(payload, "error", "message")
    if message:
        return message
    return (result.stderr or result.stdout or fallback).strip() or fallback
