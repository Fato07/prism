from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import prism_cli.app as app_module
from prism_cli.app import app
from prism_cli.demo import DemoReceipt, save_demo_receipt
from prism_cli.models import (
    PublicTraceReport,
    SentinelValidationResult,
    ValidationQuote,
    ValidationReceipt,
)

runner = CliRunner()

TRACE_ID = "d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24"
TRACE_URI = "ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8"
TRACE_HASH = "0x1a750011608a7480e9cb11f1d20587e32efb7a7dd433b85820f0dbfcdee19fdb"


def sample_quote() -> ValidationQuote:
    return ValidationQuote(
        trace_uri=TRACE_URI,
        trace_hash=TRACE_HASH,
        amount_usdc="0.01",
        amount_units="10000",
        asset="USDC",
        asset_contract="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        scheme="exact",
        network="base-sepolia",
        caip2="eip155:84532",
        facilitator="x402",
        facilitator_mode="public",
        recipient="0xaf131B054B08E57c20b31080A1Ffd406e429db6F",
    )


def sample_report() -> PublicTraceReport:
    return PublicTraceReport(
        generated_at="2026-05-16T17:00:00Z",
        trace={
            "trace_id": TRACE_ID,
            "market_id": "0xmarket",
            "market_question": "Will ETH exceed $5k by end of 2026?",
            "action": "BUY",
        },
        validation={"verdict_score": 65, "verdict_label": "PASS"},
        reasoning_metrics=None,
        readiness="usable",
        warnings=[],
        receipts={"dashboard_url": f"https://example.com/trace/{TRACE_ID}"},
    )


def sample_validation_result() -> SentinelValidationResult:
    return SentinelValidationResult(
        request_hash="request-hash",
        trace_id=TRACE_ID,
        sentinel_agent_id=2,
        verdict_score=66,
        verdict_label="PASS",
        evidence_challenges=["challenge"],
        thesis_challenges=[],
        calibration_critique="calibrated",
        ipfs_cid="QmVerdict",
        content_hash_hex="abc123",
        tx_hash="0xarc",
        payment_tx_hash="0xbase",
    )


def test_save_demo_receipt_writes_json_and_markdown(tmp_path: Path) -> None:
    receipt = DemoReceipt.from_parts(
        mode="dry_run",
        trace_id=TRACE_ID,
        trace_uri=TRACE_URI,
        trace_hash=TRACE_HASH,
        dashboard_report_url=f"https://example.com/trace/{TRACE_ID}",
        report=sample_report(),
        quote=sample_quote(),
        validation_result=None,
    )

    paths = save_demo_receipt(receipt, tmp_path)

    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    payload = json.loads(paths.json_path.read_text())
    assert payload["mode"] == "dry_run"
    assert payload["quote"]["amount_usdc"] == "0.01"
    markdown = paths.markdown_path.read_text()
    assert "Prism demo receipt" in markdown
    assert "0.01 USDC" in markdown
    assert "X-PAYMENT" not in markdown


def test_demo_dry_run_saves_receipt_without_payment(monkeypatch, tmp_path: Path) -> None:
    async def fake_fetch_report(config, trace_source):
        assert trace_source == TRACE_ID
        return sample_report()

    async def fake_quote(config, source, trace_hash=None):
        assert source == TRACE_URI
        assert trace_hash == TRACE_HASH
        return sample_quote()

    async def forbidden_paid(*args, **kwargs):
        raise AssertionError("dry-run demo must not submit payment")

    def forbidden_sign(*args, **kwargs):
        raise AssertionError("dry-run demo must not sign payment")

    monkeypatch.setattr(app_module, "fetch_public_report", fake_fetch_report)
    monkeypatch.setattr(app_module, "request_validation_quote", fake_quote)
    monkeypatch.setattr(app_module, "submit_paid_validation", forbidden_paid)
    monkeypatch.setattr(app_module, "sign_x_payment_with_circle_cli", forbidden_sign)

    result = runner.invoke(app, ["demo", "--receipts-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "dry_run" in result.output
    assert "prism validate" in result.output
    assert list(tmp_path.glob("*.json"))
    assert list(tmp_path.glob("*.md"))


def test_demo_pay_requires_circle_address(monkeypatch, tmp_path: Path) -> None:
    result = runner.invoke(app, ["demo", "--pay", "--receipts-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "--circle-address is required" in result.output


def test_demo_canonicalizes_dashboard_trace_url(monkeypatch, tmp_path: Path) -> None:
    seen_trace_sources: list[str] = []

    async def fake_fetch_report(config, trace_source):
        seen_trace_sources.append(trace_source)
        return sample_report()

    async def fake_quote(config, source, trace_hash=None):
        return sample_quote()

    monkeypatch.setattr(app_module, "fetch_public_report", fake_fetch_report)
    monkeypatch.setattr(app_module, "request_validation_quote", fake_quote)

    result = runner.invoke(
        app,
        [
            "demo",
            "--trace-id",
            f"https://prism.example/trace/{TRACE_ID}",
            "--receipts-dir",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen_trace_sources == [TRACE_ID]
    payload = json.loads(result.output)
    assert payload["receipt"]["trace_id"] == TRACE_ID
    assert Path(payload["paths"]["json_path"]).exists()


def test_demo_pay_signs_with_circle_and_saves_paid_receipt(monkeypatch, tmp_path: Path) -> None:
    async def fake_fetch_report(config, trace_source):
        return sample_report()

    async def fake_quote(config, source, trace_hash=None):
        return sample_quote()

    def fake_sign(quote, *, payer_address, circle_chain=None, max_amount_usdc="0.01"):
        assert payer_address == "0x1111111111111111111111111111111111111111"
        assert circle_chain == "BASE-SEPOLIA"
        assert max_amount_usdc == "0.01"
        return "signed-payload"

    async def fake_paid(config, source, x_payment_header, trace_hash=None):
        assert x_payment_header == "signed-payload"
        return ValidationReceipt(quote=sample_quote(), result=sample_validation_result())

    monkeypatch.setattr(app_module, "fetch_public_report", fake_fetch_report)
    monkeypatch.setattr(app_module, "request_validation_quote", fake_quote)
    monkeypatch.setattr(app_module, "sign_x_payment_with_circle_cli", fake_sign)
    monkeypatch.setattr(app_module, "submit_paid_validation", fake_paid)

    result = runner.invoke(
        app,
        [
            "demo",
            "--pay",
            "--circle-address",
            "0x1111111111111111111111111111111111111111",
            "--circle-chain",
            "BASE-SEPOLIA",
            "--receipts-dir",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["receipt"]["mode"] == "paid"
    assert payload["receipt"]["validation_result"]["payment_tx_hash"] == "0xbase"
    assert "signed-payload" not in result.output
    json_path = Path(payload["paths"]["json_path"])
    markdown_path = Path(payload["paths"]["markdown_path"])
    assert json_path.exists()
    assert "signed-payload" not in json_path.read_text()
    assert "signed-payload" not in markdown_path.read_text()
