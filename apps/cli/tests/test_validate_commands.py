from __future__ import annotations

import json

from typer.testing import CliRunner

import prism_cli.app as app_module
from prism_cli.app import app
from prism_cli.models import SentinelValidationResult, ValidationQuote, ValidationReceipt

runner = CliRunner()


def sample_quote() -> ValidationQuote:
    return ValidationQuote(
        trace_uri="ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8",
        trace_hash="0x1a750011608a7480e9cb11f1d20587e32efb7a7dd433b85820f0dbfcdee19fdb",
        amount_usdc="0.01",
        amount_units="10000",
        asset="USDC",
        asset_contract="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        scheme="exact",
        network="base-sepolia",
        caip2="eip155:84532",
        facilitator="x402",
        facilitator_mode="public",
        recipient="0x1453000000000000000000000000000000000000",
    )


def test_quote_command_outputs_payment_requirements_json(monkeypatch) -> None:
    async def fake_quote(config, source, trace_hash=None):
        assert config.normalized_sentinel_url().endswith("/mcp/")
        assert source.startswith("ipfs://")
        assert trace_hash is None
        return sample_quote()

    monkeypatch.setattr(app_module, "request_validation_quote", fake_quote)

    result = runner.invoke(
        app,
        ["quote", "ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["amount_usdc"] == "0.01"
    assert payload["caip2"] == "eip155:84532"
    assert payload["recipient"].startswith("0x1453")


def test_validate_without_payment_header_prints_quote_and_exits_nonzero(monkeypatch) -> None:
    async def fake_quote(config, source, trace_hash=None):
        return sample_quote()

    monkeypatch.setattr(app_module, "request_validation_quote", fake_quote)

    result = runner.invoke(
        app,
        ["validate", "ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8"],
    )

    assert result.exit_code == 1
    assert "Payment required" in result.output
    assert "--x-payment-file" in result.output
    assert "0.01 USDC" in result.output


def test_validate_with_external_payment_file_outputs_receipt_json(monkeypatch, tmp_path) -> None:
    payment_file = tmp_path / "x-payment.txt"
    payment_file.write_text("signed-payload\n")

    async def fake_validate(config, source, x_payment_header, trace_hash=None):
        assert x_payment_header == "signed-payload"
        return ValidationReceipt(
            quote=sample_quote(),
            result=SentinelValidationResult(
                request_hash="request-hash",
                trace_id="d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24",
                sentinel_agent_id=2,
                verdict_score=65,
                verdict_label="PASS",
                evidence_challenges=["challenge"],
                thesis_challenges=[],
                calibration_critique="calibrated",
                ipfs_cid="QmVerdict",
                content_hash_hex="abc123",
                tx_hash="0xarc",
                payment_tx_hash="0xbase",
            ),
        )

    monkeypatch.setattr(app_module, "submit_paid_validation", fake_validate)

    result = runner.invoke(
        app,
        [
            "validate",
            "ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8",
            "--x-payment-file",
            str(payment_file),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["result"]["verdict_score"] == 65
    assert payload["result"]["payment_tx_hash"] == "0xbase"


def test_validate_can_sign_with_circle_cli_wallet(monkeypatch) -> None:
    async def fake_quote(config, source, trace_hash=None):
        return sample_quote()

    def fake_sign(quote, *, payer_address, circle_chain=None, max_amount_usdc="0.01"):
        assert quote.amount_usdc == "0.01"
        assert payer_address == "0x1111111111111111111111111111111111111111"
        assert circle_chain == "BASE-SEPOLIA"
        assert max_amount_usdc == "0.01"
        return "circle-signed-payload"

    async def fake_validate(config, source, x_payment_header, trace_hash=None):
        assert x_payment_header == "circle-signed-payload"
        return ValidationReceipt(
            quote=sample_quote(),
            result=SentinelValidationResult(
                request_hash="request-hash",
                trace_id="d6cdd60f-f5e0-43ab-ba2d-7dcab76a8e24",
                sentinel_agent_id=2,
                verdict_score=65,
                verdict_label="PASS",
                evidence_challenges=[],
                thesis_challenges=[],
                calibration_critique="calibrated",
                ipfs_cid="QmVerdict",
                content_hash_hex="abc123",
                tx_hash=None,
                payment_tx_hash="0xbase",
            ),
        )

    monkeypatch.setattr(app_module, "request_validation_quote", fake_quote)
    monkeypatch.setattr(app_module, "sign_x_payment_with_circle_cli", fake_sign)
    monkeypatch.setattr(app_module, "submit_paid_validation", fake_validate)

    result = runner.invoke(
        app,
        [
            "validate",
            "ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8",
            "--circle-address",
            "0x1111111111111111111111111111111111111111",
            "--circle-chain",
            "BASE-SEPOLIA",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["result"]["payment_tx_hash"] == "0xbase"


def test_validate_circle_signing_cap_error_is_clean(monkeypatch) -> None:
    async def fake_quote(config, source, trace_hash=None):
        return sample_quote().model_copy(update={"amount_usdc": "0.02", "amount_units": "20000"})

    monkeypatch.setattr(app_module, "request_validation_quote", fake_quote)

    result = runner.invoke(
        app,
        [
            "validate",
            "ipfs://QmNzqnPEEQUMn3GMbiEZANpKXZRPmTHxVwt5nNevR8iXt8",
            "--circle-address",
            "0x1111111111111111111111111111111111111111",
        ],
    )

    assert result.exit_code == 1
    assert "exceeds max" in result.output
    assert "Traceback" not in result.output
