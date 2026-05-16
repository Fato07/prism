"""x402 EIP-3009 payment-header signing via Circle CLI agent wallets.

This module intentionally does not handle private keys. It prepares the
EIP-712 typed data required by x402's EVM exact scheme, asks the Circle CLI
wallet signer to sign it, then wraps the signature into the base64 X-PAYMENT
header expected by Prism's sentinel.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import subprocess
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from prism_cli.models import ValidationQuote

TRANSFER_WITH_AUTHORIZATION_TYPES: dict[str, list[dict[str, str]]] = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ],
}

NETWORK_SIGNING_CONFIG: dict[str, dict[str, str | int]] = {
    "eip155:84532": {
        "chain_id": 84532,
        "circle_chain": "BASE-SEPOLIA",
        "domain_name": "USDC",
        "domain_version": "2",
    },
    "base-sepolia": {
        "chain_id": 84532,
        "circle_chain": "BASE-SEPOLIA",
        "domain_name": "USDC",
        "domain_version": "2",
    },
    "eip155:8453": {
        "chain_id": 8453,
        "circle_chain": "BASE",
        "domain_name": "USD Coin",
        "domain_version": "2",
    },
    "base": {
        "chain_id": 8453,
        "circle_chain": "BASE",
        "domain_name": "USD Coin",
        "domain_version": "2",
    },
    "eip155:5042002": {
        "chain_id": 5042002,
        "circle_chain": "ARC-TESTNET",
        "domain_name": "USDC",
        "domain_version": "2",
    },
    "arc-testnet": {
        "chain_id": 5042002,
        "circle_chain": "ARC-TESTNET",
        "domain_name": "USDC",
        "domain_version": "2",
    },
}

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
BYTES32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
SIGNATURE_RE = re.compile(r"0x[0-9a-fA-F]{130}")


class X402SigningError(RuntimeError):
    """User-facing x402 signing error."""


def infer_circle_chain(quote: ValidationQuote) -> str:
    """Infer the Circle CLI chain flag from the quote network."""
    config = _network_config(quote)
    return str(config["circle_chain"])


def sign_x_payment_with_circle_cli(
    quote: ValidationQuote,
    *,
    payer_address: str,
    circle_chain: str | None = None,
    max_amount_usdc: str = "0.01",
    circle_timeout_seconds: float = 30.0,
    now: int | None = None,
    nonce: str | None = None,
) -> str:
    """Sign an x402 exact-EVM payment with Circle CLI and return X-PAYMENT.

    The private key remains inside the Circle agent wallet / local Circle CLI
    wallet. Prism CLI only passes typed data to ``circle wallet sign typed-data``
    and receives a signature.
    """
    _assert_amount_within_cap(quote, max_amount_usdc)
    typed_data, authorization = build_eip3009_typed_data(
        quote,
        payer_address=payer_address,
        now=now,
        nonce=nonce,
    )
    signature = _sign_typed_data_with_circle_cli(
        typed_data,
        payer_address=payer_address,
        circle_chain=circle_chain or infer_circle_chain(quote),
        timeout_seconds=circle_timeout_seconds,
    )
    return build_x_payment_header(quote, authorization=authorization, signature=signature)


def build_eip3009_typed_data(
    quote: ValidationQuote,
    *,
    payer_address: str,
    now: int | None = None,
    nonce: str | None = None,
    valid_after: int | None = None,
    valid_before: int | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build typed data for x402 EIP-3009 ``transferWithAuthorization``."""
    if not ADDRESS_RE.fullmatch(payer_address):
        raise X402SigningError("Payer address must be a 0x-prefixed EVM address.")
    if not quote.recipient or not ADDRESS_RE.fullmatch(quote.recipient):
        raise X402SigningError("Quote is missing a valid recipient address.")
    if not quote.asset_contract or not ADDRESS_RE.fullmatch(quote.asset_contract):
        raise X402SigningError("Quote is missing a valid USDC contract address.")

    config = _network_config(quote)
    issued_at = int(time.time()) if now is None else now
    resolved_valid_after = issued_at - 60 if valid_after is None else valid_after
    timeout_s = 120
    resolved_valid_before = issued_at + timeout_s if valid_before is None else valid_before
    resolved_nonce = nonce or "0x" + secrets.token_hex(32)
    if not BYTES32_RE.fullmatch(resolved_nonce):
        raise X402SigningError("Nonce must be a 0x-prefixed bytes32 hex string.")

    value = _validated_quote_amount_units(quote)
    message = {
        "from": payer_address,
        "to": quote.recipient,
        "value": value,
        "validAfter": int(resolved_valid_after),
        "validBefore": int(resolved_valid_before),
        "nonce": resolved_nonce,
    }
    typed_data: dict[str, Any] = {
        "types": TRANSFER_WITH_AUTHORIZATION_TYPES,
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": str(config["domain_name"]),
            "version": str(config["domain_version"]),
            "chainId": int(config["chain_id"]),
            "verifyingContract": quote.asset_contract,
        },
        "message": message,
    }
    authorization = {
        "from": payer_address,
        "to": quote.recipient,
        "value": str(value),
        "validAfter": str(resolved_valid_after),
        "validBefore": str(resolved_valid_before),
        "nonce": resolved_nonce,
    }
    return typed_data, authorization


def build_x_payment_header(
    quote: ValidationQuote,
    *,
    authorization: dict[str, str],
    signature: str,
) -> str:
    """Build the base64 X-PAYMENT header from authorization + signature."""
    if not SIGNATURE_RE.fullmatch(signature):
        raise X402SigningError("Circle CLI did not return a valid 65-byte EVM signature.")
    config = _network_config(quote)
    if not quote.caip2:
        raise X402SigningError("Quote is missing a CAIP-2 network id.")
    if not quote.asset_contract:
        raise X402SigningError("Quote is missing an asset contract.")
    if not quote.recipient:
        raise X402SigningError("Quote is missing a recipient.")

    payment_payload = {
        "x402Version": 2,
        "payload": {
            "authorization": authorization,
            "signature": signature,
        },
        "accepted": {
            "scheme": quote.scheme,
            "network": quote.caip2,
            "asset": quote.asset_contract,
            "amount": str(_validated_quote_amount_units(quote)),
            "payTo": quote.recipient,
            "maxTimeoutSeconds": 120,
            "extra": {
                "name": str(config["domain_name"]),
                "version": str(config["domain_version"]),
            },
        },
        "resource": None,
        "extensions": None,
    }
    encoded = json.dumps(payment_payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(encoded).decode("ascii")


def _sign_typed_data_with_circle_cli(
    typed_data: dict[str, Any],
    *,
    payer_address: str,
    circle_chain: str,
    timeout_seconds: float,
) -> str:
    """Call ``circle wallet sign typed-data`` and return the signature."""
    typed_data_json = json.dumps(typed_data, separators=(",", ":"))
    cmd = [
        "circle",
        "wallet",
        "sign",
        "typed-data",
        typed_data_json,
        "--address",
        payer_address,
        "--chain",
        circle_chain,
        "--quiet",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise X402SigningError(
            "Circle CLI was not found. Install/login with `circle wallet status`, then retry."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise X402SigningError(
            f"Circle CLI signing timed out after {timeout_seconds:g}s. "
            "Check `circle wallet status` in an interactive terminal."
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "circle wallet sign failed").strip()
        raise X402SigningError(detail)
    match = SIGNATURE_RE.search(result.stdout.strip())
    if match is None:
        raise X402SigningError("Circle CLI did not print a valid EVM signature.")
    return match.group(0)


def _network_config(quote: ValidationQuote) -> dict[str, str | int]:
    """Return signing config for a quote network."""
    keys = [quote.caip2 or "", quote.network]
    for key in keys:
        config = NETWORK_SIGNING_CONFIG.get(key.lower())
        if config:
            return config
    raise X402SigningError(f"Unsupported x402 network for Circle signing: {quote.network}")


def _assert_amount_within_cap(quote: ValidationQuote, max_amount_usdc: str) -> None:
    """Refuse to sign if the actual EIP-3009 units exceed the caller's cap."""
    amount_units = _validated_quote_amount_units(quote)
    cap_units = _amount_usdc_to_units(max_amount_usdc, field_name="max amount")
    if amount_units > cap_units:
        amount = Decimal(amount_units) / Decimal(1_000_000)
        cap = Decimal(cap_units) / Decimal(1_000_000)
        raise X402SigningError(
            f"Quote amount {amount} USDC exceeds max {cap} USDC; increase --max-amount-usdc "
            "only if you intend to pay more."
        )


def _validated_quote_amount_units(quote: ValidationQuote) -> int:
    """Return quote units after checking decimal amount and units agree."""
    declared_units = _amount_usdc_to_units(quote.amount_usdc, field_name="quote amount")
    try:
        signed_units = int(quote.amount_units)
    except ValueError as exc:
        raise X402SigningError("Quote amount_units is not an integer.") from exc
    if signed_units != declared_units:
        raise X402SigningError(
            "Quote amount mismatch: decimal amount and smallest-unit amount disagree."
        )
    return signed_units


def _amount_usdc_to_units(value: str, *, field_name: str) -> int:
    """Convert a USDC decimal amount to 6-decimal smallest units."""
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise X402SigningError(f"Invalid {field_name} USDC amount.") from exc
    if amount < 0:
        raise X402SigningError(f"Invalid {field_name} USDC amount.")
    units = amount * Decimal(1_000_000)
    if units != units.to_integral_value():
        raise X402SigningError(f"Invalid {field_name}: USDC supports at most 6 decimals.")
    return int(units)
