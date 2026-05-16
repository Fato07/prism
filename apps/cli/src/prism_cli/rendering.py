"""Human-readable rendering for Prism CLI commands."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from prism_cli.models import (
    InspectResult,
    MarketListResponse,
    MarketResolveResponse,
    PublicHistoryResponse,
    PublicStatsResponse,
    PublicTraceReport,
    ValidationQuote,
    ValidationReceipt,
)

console = Console()


def print_json_model(model: Any) -> None:
    """Print a Pydantic model or mapping as valid, unwrapped JSON."""
    payload = model.model_dump(mode="json") if hasattr(model, "model_dump") else model
    print(json.dumps(payload, indent=2, sort_keys=True))


def print_inspect(result: InspectResult) -> None:
    """Render `prism inspect` output."""
    metrics = result.reasoning_metrics
    console.print("[bold]Prism trace inspection[/bold]")
    console.print(f"Trace:      {result.trace_id}")
    console.print(f"Market:     {result.market_question}")
    console.print(f"Action:     {result.action}")
    console.print(f"Readiness:  [bold]{result.readiness}[/bold]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Evidence count", str(metrics.evidence_count))
    table.add_row("Source diversity", str(metrics.source_diversity))
    table.add_row("Thesis steps", str(metrics.thesis_steps))
    table.add_row("Evidence coverage", f"{metrics.evidence_coverage:.0%}")
    table.add_row("Invalid evidence refs", str(metrics.invalid_evidence_refs))
    table.add_row("Unsupported thesis steps", str(metrics.unsupported_thesis_steps))
    table.add_row("Risk factors", str(metrics.risk_factor_count))
    table.add_row("Avg evidence confidence", f"{metrics.avg_evidence_confidence:.2f}")
    table.add_row("Probability delta", f"{metrics.probability_delta:.2f}")
    table.add_row(
        "Falsification language",
        "yes" if metrics.has_falsification_language else "no",
    )
    console.print(table)

    if result.warnings:
        console.print("[bold yellow]Warnings[/bold yellow]")
        for warning in result.warnings:
            console.print(f"- {warning}")


def print_stats(response: PublicStatsResponse) -> None:
    """Render public stats output."""
    stats = response.stats
    console.print("[bold]Prism public stats[/bold]")
    console.print(f"Generated: {response.generated_at}")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key in [
        "tracesValidated",
        "verdictsIssued",
        "onChainAnchors",
        "externalX402Calls",
        "avgVerdictScore",
        "calibrationGap",
    ]:
        if key in stats:
            table.add_row(key, str(stats[key]))
    console.print(table)


def print_history(response: PublicHistoryResponse) -> None:
    """Render recent public history output."""
    console.print("[bold]Recent Prism validations[/bold]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Label")
    table.add_column("Trace")
    table.add_column("Created")
    for entry in response.entries:
        table.add_row(
            str(entry.verdict_score),
            entry.verdict_label,
            entry.dashboard_url,
            entry.created_at,
        )
    console.print(table)


def print_markets(response: MarketListResponse) -> None:
    """Render recommended markets."""
    console.print("[bold]Recommended Polymarket markets[/bold]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Question")
    table.add_column("Yes token")
    table.add_column("End date")
    for market in response.markets:
        token = market.yes_token_id or "—"
        table.add_row(
            str(market.surface_score),
            market.question,
            token[:18] + "…" if len(token) > 20 else token,
            market.end_date or "—",
        )
    console.print(table)


def print_market_resolution(response: MarketResolveResponse) -> None:
    """Render market token resolution."""
    resolution = response.resolution
    console.print("[bold]Market token resolution[/bold]")
    console.print(f"Query:      {response.query}")
    console.print(f"Status:     {resolution.status}")
    console.print(f"Source:     {resolution.source}")
    console.print(f"Confidence: {resolution.confidence}")
    if resolution.token_id:
        console.print(f"Token ID:   {resolution.token_id}")
    if resolution.condition_id:
        console.print(f"Condition:  {resolution.condition_id}")
    if resolution.matched_question:
        console.print(f"Matched:    {resolution.matched_question}")
    if resolution.reason:
        console.print(f"Reason:     {resolution.reason}")


def print_validation_quote(quote: ValidationQuote) -> None:
    """Render an x402 quote for sentinel validation."""
    console.print("[bold]Prism sentinel validation quote[/bold]")
    console.print(f"Trace URI:  {quote.trace_uri}")
    console.print(f"Trace hash: {quote.trace_hash}")
    console.print(f"Amount:     {quote.amount_usdc} {quote.asset} ({quote.amount_units} units)")
    console.print(f"Network:    {quote.network}" + (f" / {quote.caip2}" if quote.caip2 else ""))
    if quote.asset_contract:
        console.print(f"Asset:      {quote.asset_contract}")
    if quote.recipient:
        console.print(f"Recipient:  {quote.recipient}")
    if quote.facilitator:
        console.print(f"Facilitator:{quote.facilitator}")
    console.print("Signing is external: Prism CLI does not custody keys or private-key files.")


def print_validation_receipt(receipt: ValidationReceipt) -> None:
    """Render a paid sentinel validation receipt."""
    result = receipt.result
    console.print("[bold]Prism sentinel validation receipt[/bold]")
    console.print(f"Trace:      {result.trace_id}")
    console.print(f"Verdict:    {result.verdict_score} {result.verdict_label}")
    console.print(f"Verdict IPFS: ipfs://{result.ipfs_cid}")
    if result.payment_tx_hash:
        console.print(f"Payment tx: {result.payment_tx_hash}")
    if result.tx_hash:
        console.print(f"Arc tx:     {result.tx_hash}")
    if result.evidence_challenges:
        console.print("[bold]Evidence challenges[/bold]")
        for challenge in result.evidence_challenges:
            console.print(f"- {challenge}")
    if result.thesis_challenges:
        console.print("[bold]Thesis challenges[/bold]")
        for challenge in result.thesis_challenges:
            console.print(f"- {challenge}")


def print_report(report: PublicTraceReport) -> None:
    """Render a public trace report."""
    console.print("[bold]Prism trace report[/bold]")
    console.print(f"Generated: {report.generated_at}")
    console.print(f"Trace:     {report.trace.get('trace_id')}")
    market = report.trace.get("market_question") or report.trace.get("market_id")
    console.print(f"Market:    {market}")
    if report.validation:
        console.print(
            f"Verdict:   {report.validation.get('verdict_score')} "
            f"{report.validation.get('verdict_label')}"
        )
    if report.readiness:
        console.print(f"Readiness: {report.readiness}")
    if report.reasoning_metrics:
        console.print()
        print_inspect(
            InspectResult(
                trace_id=str(report.trace.get("trace_id")),
                market_id=str(report.trace.get("market_id")),
                market_question=str(report.trace.get("market_question") or ""),
                action=str(report.trace.get("action") or ""),
                readiness=report.readiness or "needs_review",
                reasoning_metrics=report.reasoning_metrics,
                warnings=report.warnings,
            )
        )
    console.print("[bold]Receipts[/bold]")
    for key, value in report.receipts.items():
        console.print(f"- {key}: {value or '—'}")
