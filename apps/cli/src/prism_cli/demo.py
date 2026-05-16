"""One-command Prism developer demo and receipt helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from prism_cli.models import PublicTraceReport, SentinelValidationResult, ValidationQuote

DEFAULT_DEMO_TRACE_ID = "d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24"
DEFAULT_DEMO_TRACE_URI = "ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8"
DEFAULT_DEMO_TRACE_HASH = "0x1a750011608a7480e9cb11f1d20587e32efb7a7dd433b85820f0dbfcdee19fdb"
DEFAULT_RECEIPTS_DIR = Path(".prism") / "receipts"

DemoMode = Literal["dry_run", "paid"]


class DemoReceiptPaths(BaseModel):
    """Filesystem paths written by a demo receipt save."""

    json_path: Path
    markdown_path: Path


class DemoReceipt(BaseModel):
    """Self-contained receipt for a Prism CLI demo run."""

    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    mode: DemoMode
    trace_id: str
    trace_uri: str
    trace_hash: str
    dashboard_report_url: str | None = None
    market_question: str | None = None
    readiness: str | None = None
    existing_verdict_score: int | None = None
    existing_verdict_label: str | None = None
    quote: ValidationQuote
    validation_result: SentinelValidationResult | None = None
    next_commands: list[str] = Field(default_factory=list)

    @classmethod
    def from_parts(
        cls,
        *,
        mode: DemoMode,
        trace_id: str,
        trace_uri: str,
        trace_hash: str,
        dashboard_report_url: str | None,
        report: PublicTraceReport,
        quote: ValidationQuote,
        validation_result: SentinelValidationResult | None,
    ) -> DemoReceipt:
        """Build a receipt from public report, quote, and optional paid result."""
        validation = report.validation or {}
        return cls(
            mode=mode,
            trace_id=trace_id,
            trace_uri=trace_uri,
            trace_hash=trace_hash,
            dashboard_report_url=dashboard_report_url,
            market_question=str(report.trace.get("market_question") or "") or None,
            readiness=report.readiness,
            existing_verdict_score=_int_or_none(validation.get("verdict_score")),
            existing_verdict_label=(
                str(validation.get("verdict_label")) if validation.get("verdict_label") else None
            ),
            quote=quote,
            validation_result=validation_result,
            next_commands=_next_commands(trace_uri=trace_uri, trace_hash=trace_hash),
        )


def save_demo_receipt(receipt: DemoReceipt, receipts_dir: Path) -> DemoReceiptPaths:
    """Write JSON and Markdown demo receipts to disk."""
    receipts_dir.mkdir(parents=True, exist_ok=True)
    stamp = receipt.generated_at.replace(":", "").replace("-", "")
    safe_stamp = stamp.replace("+00:00", "Z")
    stem = f"{safe_stamp}-{receipt.mode}-{receipt.trace_id[:8]}"
    json_path = receipts_dir / f"{stem}.json"
    markdown_path = receipts_dir / f"{stem}.md"
    json_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_demo_markdown(receipt), encoding="utf-8")
    return DemoReceiptPaths(json_path=json_path, markdown_path=markdown_path)


def render_demo_markdown(receipt: DemoReceipt) -> str:
    """Render a human-readable Markdown demo receipt."""
    lines = [
        "# Prism demo receipt",
        "",
        f"- **Mode:** {receipt.mode}",
        f"- **Generated:** {receipt.generated_at}",
        f"- **Trace:** `{receipt.trace_id}`",
        f"- **Trace URI:** `{receipt.trace_uri}`",
        f"- **Trace hash:** `{receipt.trace_hash}`",
    ]
    if receipt.dashboard_report_url:
        lines.append(f"- **Dashboard report:** {receipt.dashboard_report_url}")
    if receipt.market_question:
        lines.append(f"- **Market:** {receipt.market_question}")
    if receipt.readiness:
        lines.append(f"- **Readiness:** {receipt.readiness}")
    if receipt.existing_verdict_score is not None:
        lines.append(
            f"- **Existing public verdict:** {receipt.existing_verdict_score} "
            f"{receipt.existing_verdict_label or ''}".rstrip()
        )

    lines.extend(
        [
            "",
            "## x402 quote",
            "",
            f"- **Amount:** {receipt.quote.amount_usdc} {receipt.quote.asset}",
            f"- **Network:** {receipt.quote.network}"
            + (f" / `{receipt.quote.caip2}`" if receipt.quote.caip2 else ""),
            f"- **Asset:** `{receipt.quote.asset_contract or 'unknown'}`",
            f"- **Recipient:** `{receipt.quote.recipient or 'unknown'}`",
        ]
    )

    if receipt.validation_result:
        result = receipt.validation_result
        lines.extend(
            [
                "",
                "## Paid validation result",
                "",
                f"- **Verdict:** {result.verdict_score} {result.verdict_label}",
                f"- **Verdict IPFS:** `ipfs://{result.ipfs_cid}`",
                f"- **Payment tx:** `{result.payment_tx_hash or 'none'}`",
                f"- **Arc tx:** `{result.tx_hash or 'none'}`",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Next paid command",
                "",
                "```bash",
                *receipt.next_commands,
                "```",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def _next_commands(*, trace_uri: str, trace_hash: str) -> list[str]:
    """Return copy-paste command lines for the paid demo."""
    return [
        "uv run prism validate \\",
        f"  {trace_uri} \\",
        f"  --trace-hash {trace_hash} \\",
        "  --circle-address 0xYOUR_BASE_SEPOLIA_WALLET \\",
        "  --circle-chain BASE-SEPOLIA \\",
        "  --max-amount-usdc 0.01",
    ]


def _int_or_none(value: object) -> int | None:
    """Coerce an optional integer-like value."""
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
