from __future__ import annotations

import base64
import json
import subprocess

import pytest

from prism_cli.models import ValidationQuote
from prism_cli.x402_signing import (
    X402SigningError,
    build_eip3009_typed_data,
    build_x_payment_header,
    sign_x_payment_with_circle_cli,
)


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
        recipient="0xaf131B054B08E57c20b31080A1Ffd406e429db6F",
    )


def test_build_eip3009_typed_data_for_circle_wallet_signing() -> None:
    typed_data, authorization = build_eip3009_typed_data(
        sample_quote(),
        payer_address="0x1111111111111111111111111111111111111111",
        nonce="0x" + "ab" * 32,
        valid_after=1770000000,
        valid_before=1770000120,
    )

    assert typed_data["primaryType"] == "TransferWithAuthorization"
    assert typed_data["domain"] == {
        "name": "USDC",
        "version": "2",
        "chainId": 84532,
        "verifyingContract": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    }
    assert typed_data["types"]["TransferWithAuthorization"][-1] == {
        "name": "nonce",
        "type": "bytes32",
    }
    assert typed_data["message"] == {
        "from": "0x1111111111111111111111111111111111111111",
        "to": "0xaf131B054B08E57c20b31080A1Ffd406e429db6F",
        "value": 10000,
        "validAfter": 1770000000,
        "validBefore": 1770000120,
        "nonce": "0x" + "ab" * 32,
    }
    assert authorization["value"] == "10000"
    assert authorization["validBefore"] == "1770000120"


def test_build_x_payment_header_is_x402_v2_base64_json() -> None:
    quote = sample_quote()
    header = build_x_payment_header(
        quote,
        authorization={
            "from": "0x1111111111111111111111111111111111111111",
            "to": quote.recipient,
            "value": quote.amount_units,
            "validAfter": "1770000000",
            "validBefore": "1770000120",
            "nonce": "0x" + "ab" * 32,
        },
        signature="0x" + "cd" * 65,
    )

    payload = json.loads(base64.b64decode(header).decode())
    assert payload["x402Version"] == 2
    assert payload["payload"]["signature"] == "0x" + "cd" * 65
    assert payload["accepted"]["scheme"] == "exact"
    assert payload["accepted"]["network"] == "eip155:84532"
    assert payload["accepted"]["payTo"] == quote.recipient
    assert payload["accepted"]["extra"] == {"name": "USDC", "version": "2"}
    assert "resource" in payload and payload["resource"] is None
    assert "extensions" in payload and payload["extensions"] is None


def test_sign_x_payment_with_circle_cli_invokes_typed_data_signer(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, check, text, timeout):
        calls.append(cmd)
        assert capture_output is True
        assert check is False
        assert text is True
        assert timeout == 30.0
        return subprocess.CompletedProcess(cmd, 0, stdout="0x" + "ef" * 65 + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    header = sign_x_payment_with_circle_cli(
        sample_quote(),
        payer_address="0x1111111111111111111111111111111111111111",
        circle_chain="BASE-SEPOLIA",
        now=1770000000,
        nonce="0x" + "ab" * 32,
    )

    assert calls
    assert calls[0][:4] == ["circle", "wallet", "sign", "typed-data"]
    assert "--address" in calls[0]
    assert "0x1111111111111111111111111111111111111111" in calls[0]
    assert "BASE-SEPOLIA" in calls[0]
    payload = json.loads(base64.b64decode(header).decode())
    assert payload["payload"]["signature"] == "0x" + "ef" * 65


def test_sign_x_payment_refuses_quote_above_cap() -> None:
    quote = sample_quote().model_copy(update={"amount_usdc": "0.02", "amount_units": "20000"})

    with pytest.raises(X402SigningError, match="exceeds max"):
        sign_x_payment_with_circle_cli(
            quote,
            payer_address="0x1111111111111111111111111111111111111111",
            circle_chain="BASE-SEPOLIA",
            max_amount_usdc="0.01",
        )


def test_sign_x_payment_refuses_amount_unit_mismatch() -> None:
    quote = sample_quote().model_copy(update={"amount_usdc": "0.01", "amount_units": "20000"})

    with pytest.raises(X402SigningError, match="amount mismatch"):
        sign_x_payment_with_circle_cli(
            quote,
            payer_address="0x1111111111111111111111111111111111111111",
            circle_chain="BASE-SEPOLIA",
            max_amount_usdc="0.01",
        )


def test_sign_x_payment_handles_missing_circle_cli(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("circle")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(X402SigningError, match="Circle CLI was not found"):
        sign_x_payment_with_circle_cli(
            sample_quote(),
            payer_address="0x1111111111111111111111111111111111111111",
            circle_chain="BASE-SEPOLIA",
        )


def test_sign_x_payment_handles_circle_cli_timeout(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="circle", timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(X402SigningError, match="timed out"):
        sign_x_payment_with_circle_cli(
            sample_quote(),
            payer_address="0x1111111111111111111111111111111111111111",
            circle_chain="BASE-SEPOLIA",
            circle_timeout_seconds=1,
        )
