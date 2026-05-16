"""Typer application for the Prism CLI."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from prism_cli.client import (
    PrismCliError,
    dashboard_from_trace_url,
    fetch_markets,
    fetch_public_history,
    fetch_public_report,
    fetch_public_stats,
    load_trace,
    resolve_market,
)
from prism_cli.config import (
    BASE_SEPOLIA_EXPLORER,
    BASE_SEPOLIA_USDC,
    CIRCLE_FAUCET_URL,
    DEFAULT_DASHBOARD_URL,
    DEFAULT_IPFS_GATEWAY,
    DEFAULT_POLYMARKET_GATEWAY_URL,
    DEFAULT_SENTINEL_MCP_URL,
    CliConfig,
)
from prism_cli.metrics import inspect_trace
from prism_cli.rendering import (
    console,
    print_history,
    print_inspect,
    print_json_model,
    print_market_resolution,
    print_markets,
    print_report,
    print_stats,
)

app = typer.Typer(
    name="prism",
    help="Inspect Prism traces and read public validation reports.",
    no_args_is_help=True,
)
wallet_app = typer.Typer(help="Read-only wallet setup helpers.", no_args_is_help=True)
market_app = typer.Typer(help="Polymarket market resolution helpers.", no_args_is_help=True)
app.add_typer(wallet_app, name="wallet")
app.add_typer(market_app, name="market")

DashboardOpt = Annotated[
    str,
    typer.Option("--dashboard-url", help="Prism dashboard base URL."),
]
IpfsGatewayOpt = Annotated[
    str,
    typer.Option("--ipfs-gateway", help="IPFS gateway base URL."),
]
PolymarketGatewayOpt = Annotated[
    str,
    typer.Option("--polymarket-gateway-url", help="Prism Polymarket gateway base URL."),
]
TimeoutOpt = Annotated[float, typer.Option("--timeout", help="HTTP timeout in seconds.")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]


def _config(
    *,
    dashboard_url: str = DEFAULT_DASHBOARD_URL,
    ipfs_gateway: str = DEFAULT_IPFS_GATEWAY,
    polymarket_gateway_url: str = DEFAULT_POLYMARKET_GATEWAY_URL,
    timeout: float = 30.0,
) -> CliConfig:
    """Build a CLI config from command options."""
    return CliConfig(
        dashboard_url=dashboard_url,
        sentinel_url=DEFAULT_SENTINEL_MCP_URL,
        ipfs_gateway=ipfs_gateway,
        polymarket_gateway_url=polymarket_gateway_url,
        timeout_seconds=timeout,
    )


def _run(coro):  # type: ignore[no-untyped-def]
    """Run an async command and convert PrismCliError into a clean exit."""
    try:
        return asyncio.run(coro)
    except PrismCliError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


@app.command("inspect")
def inspect_command(
    source: Annotated[
        str,
        typer.Argument(help="Local trace JSON file, ipfs://CID, or raw IPFS CID."),
    ],
    dashboard_url: DashboardOpt = DEFAULT_DASHBOARD_URL,
    ipfs_gateway: IpfsGatewayOpt = DEFAULT_IPFS_GATEWAY,
    timeout: TimeoutOpt = 30.0,
    json_output: JsonOpt = False,
) -> None:
    """Inspect a trace locally without payment or LLM calls."""

    async def _inner() -> None:
        trace = await load_trace(
            source,
            _config(
                dashboard_url=dashboard_url,
                ipfs_gateway=ipfs_gateway,
                timeout=timeout,
            ),
        )
        result = inspect_trace(trace)
        if json_output:
            print_json_model(result)
        else:
            print_inspect(result)

    _run(_inner())


@app.command("stats")
def stats_command(
    dashboard_url: DashboardOpt = DEFAULT_DASHBOARD_URL,
    timeout: TimeoutOpt = 30.0,
    json_output: JsonOpt = False,
) -> None:
    """Show public Prism stats from the dashboard API."""

    async def _inner() -> None:
        response = await fetch_public_stats(_config(dashboard_url=dashboard_url, timeout=timeout))
        if json_output:
            print_json_model(response)
        else:
            print_stats(response)

    _run(_inner())


@app.command("history")
def history_command(
    limit: Annotated[int, typer.Option("--limit", help="Number of recent validations.")] = 10,
    dashboard_url: DashboardOpt = DEFAULT_DASHBOARD_URL,
    timeout: TimeoutOpt = 30.0,
    json_output: JsonOpt = False,
) -> None:
    """Show recent public Prism validations."""

    async def _inner() -> None:
        response = await fetch_public_history(
            _config(dashboard_url=dashboard_url, timeout=timeout),
            limit=limit,
        )
        if json_output:
            print_json_model(response)
        else:
            print_history(response)

    _run(_inner())


@app.command("markets")
def markets_command(
    limit: Annotated[int, typer.Option("--limit", help="Number of recommended markets.")] = 10,
    polymarket_gateway_url: PolymarketGatewayOpt = DEFAULT_POLYMARKET_GATEWAY_URL,
    timeout: TimeoutOpt = 30.0,
    json_output: JsonOpt = False,
) -> None:
    """Show fresh binary Polymarket markets with resolved token IDs."""

    async def _inner() -> None:
        response = await fetch_markets(
            _config(polymarket_gateway_url=polymarket_gateway_url, timeout=timeout),
            limit=limit,
        )
        if json_output:
            print_json_model(response)
        else:
            print_markets(response)

    _run(_inner())


@market_app.command("resolve")
def market_resolve_command(
    query: Annotated[
        str, typer.Argument(help="Market question, alias, condition ID, or token ID.")
    ],
    polymarket_gateway_url: PolymarketGatewayOpt = DEFAULT_POLYMARKET_GATEWAY_URL,
    timeout: TimeoutOpt = 30.0,
    json_output: JsonOpt = False,
) -> None:
    """Resolve a market query to an explicit Polymarket token ID."""

    async def _inner() -> None:
        response = await resolve_market(
            _config(polymarket_gateway_url=polymarket_gateway_url, timeout=timeout),
            query=query,
        )
        if json_output:
            print_json_model(response)
        else:
            print_market_resolution(response)

    _run(_inner())


@app.command("report")
def report_command(
    trace: Annotated[str, typer.Argument(help="Trace UUID or dashboard /trace/<id> URL.")],
    dashboard_url: DashboardOpt = DEFAULT_DASHBOARD_URL,
    timeout: TimeoutOpt = 30.0,
    json_output: JsonOpt = False,
) -> None:
    """Fetch a public trace report with metrics, verdict, and receipts."""

    async def _inner() -> None:
        effective_dashboard = dashboard_from_trace_url(trace) or dashboard_url
        response = await fetch_public_report(
            _config(dashboard_url=effective_dashboard, timeout=timeout),
            trace,
        )
        if json_output:
            print_json_model(response)
        else:
            print_report(response)

    _run(_inner())


@wallet_app.command("fund-link")
def wallet_fund_link() -> None:
    """Print Base Sepolia USDC funding instructions."""
    console.print("[bold]Prism testnet funding[/bold]")
    console.print("Network: Base Sepolia")
    console.print(f"Token:   USDC ({BASE_SEPOLIA_USDC})")
    console.print(f"Faucet:  {CIRCLE_FAUCET_URL}")
    console.print("Use testnet funds only. Prism CLI v0 does not custody keys.")


@wallet_app.command("status")
def wallet_status(
    address: Annotated[
        str | None,
        typer.Option("--address", help="Wallet address to link."),
    ] = None,
) -> None:
    """Show read-only wallet/network expectations for Prism x402 calls."""
    console.print("[bold]Prism wallet status helper[/bold]")
    console.print("Expected network: Base Sepolia")
    console.print(f"USDC contract:    {BASE_SEPOLIA_USDC}")
    console.print(f"Faucet:           {CIRCLE_FAUCET_URL}")
    if address:
        console.print(f"Explorer:         {BASE_SEPOLIA_EXPLORER}/address/{address}")
    console.print("No private key is required for read-only CLI commands.")


def main() -> None:
    """Console entrypoint."""
    app()
