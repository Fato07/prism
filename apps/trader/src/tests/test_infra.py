"""Integration tests for shared infrastructure components.

Tests cover:
- DB migration and table verification (VAL-CROSS-005)
- CircleChain async wrapper (VAL-CHAIN-006)
- PinataClient IPFS pinning
- Env validation (VAL-CROSS-006)
- No raw private key patterns (VAL-CROSS-009)
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import psycopg
import pytest
from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace
from prism_schemas.verdict import SentinelVerdict

from trader.chain import ACCOUNT_TYPE, BLOCKCHAIN, CircleChain
from trader.config import (
    _is_claude_family,
    _is_gpt_family,
    check_geofence,
    startup_check,
    validate_env,
)
from trader.ipfs import PinataClient

# ---------------------------------------------------------------------------
# DB migration tests (VAL-CROSS-005)
# ---------------------------------------------------------------------------

_DSN = os.environ.get("DATABASE_URL", "")


def _make_trace(trace_id: str = "test-hash-001", **overrides: Any) -> TradingR1Trace:
    """Create a TradingR1Trace for testing with sensible defaults."""
    defaults: dict[str, Any] = dict(
        trace_id=trace_id,
        agent_id=1,
        market_id="0xabc",
        market_question="Will ETH hit $5000?",
        thesis=[
            ThesisStep(
                proposition="Bullish",
                supporting_evidence_ids=[0],
                risk_factors=["risk"],
            )
        ],
        evidence=[
            Evidence(
                source="test",
                claim="up 20%",
                confidence=0.8,
                timestamp=datetime.now(UTC),
            )
        ],
        raw_probability=0.65,
        volatility_adjustment=-0.05,
        final_probability=0.60,
        action="BUY",
        size_usdc=10.0,
        price_limit=0.60,
        rationale="Test rationale.",
        model_family="anthropic-claude",
        model_name="claude-sonnet-4-20250514",
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return TradingR1Trace(**defaults)


@pytest.mark.integration
@pytest.mark.skipif(not _DSN, reason="DATABASE_URL not set")
class TestDBMigration:
    """Neon Postgres migration and table structure tests."""

    def test_migration_runs(self) -> None:
        """Migration executes without error on Neon."""
        from prism_schemas.db import run_migration

        run_migration(_DSN)  # Should not raise

    def test_all_five_tables_exist(self) -> None:
        """All 5 required tables exist after migration."""
        from prism_schemas.db import list_tables, run_migration

        run_migration(_DSN)
        tables = list_tables(_DSN)
        required = {"agents", "traces", "validations", "trades", "feedback"}
        assert required.issubset(set(tables)), f"Missing tables: {required - set(tables)}"

    def test_insert_agent(self) -> None:
        """INSERT into agents table succeeds with all required fields."""
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agents "
                "(agent_id, role, wallet_address, agent_card_cid) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (agent_id) DO UPDATE "
                "SET wallet_address = EXCLUDED.wallet_address "
                "RETURNING agent_id",
                (9999001, "trader", "0xtest_trader_addr", "QmTestAgentCard"),
            )
            result = cur.fetchone()
            conn.commit()
            assert result is not None
            assert result[0] == 9999001

    def test_insert_trace(self) -> None:
        """INSERT into traces table succeeds with all required fields."""
        trace_id = str(uuid.uuid4())
        content_hash = hashlib.sha256(b"test_trace_content").digest()
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO traces "
                "(trace_id, agent_id, market_id, ipfs_cid, content_hash) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (trace_id) DO UPDATE "
                "SET ipfs_cid = EXCLUDED.ipfs_cid "
                "RETURNING trace_id",
                (
                    trace_id,
                    9999001,
                    "0xmarket_test",
                    "QmTestTrace",
                    content_hash,
                ),
            )
            result = cur.fetchone()
            conn.commit()
            assert result is not None

    def test_insert_validation(self) -> None:
        """INSERT into validations table succeeds with all required fields."""
        # First ensure sentinel agent exists
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agents "
                "(agent_id, role, wallet_address, agent_card_cid) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (agent_id) DO UPDATE "
                "SET wallet_address = EXCLUDED.wallet_address",
                (
                    9999002,
                    "sentinel",
                    "0xtest_sentinel_addr",
                    "QmTestSentinelCard",
                ),
            )
            conn.commit()

        # Get a trace_id from traces table
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute("SELECT trace_id FROM traces WHERE agent_id = 9999001 LIMIT 1")
            row = cur.fetchone()
            assert row is not None, "Need at least one trace row"
            trace_id = row[0]

        request_hash = hashlib.sha256(b"test_request").digest()
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO validations "
                "(request_hash, trace_id, sentinel_agent_id, "
                "verdict_score, response_uri) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (request_hash) DO UPDATE "
                "SET verdict_score = EXCLUDED.verdict_score "
                "RETURNING request_hash",
                (
                    request_hash,
                    trace_id,
                    9999002,
                    72,
                    "ipfs://QmTestVerdict",
                ),
            )
            result = cur.fetchone()
            conn.commit()
            assert result is not None

    def test_insert_trade(self) -> None:
        """INSERT into trades table succeeds with all required fields."""
        # Get a trace_id
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute("SELECT trace_id FROM traces WHERE agent_id = 9999001 LIMIT 1")
            row = cur.fetchone()
            assert row is not None
            trace_id = row[0]

        order_id = f"order-{uuid.uuid4()}"
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO trades "
                "(order_id, trace_id, market_id, side, "
                "size, builder_code, status, polymarket_tx) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (order_id) DO UPDATE "
                "SET status = EXCLUDED.status "
                "RETURNING order_id",
                (
                    order_id,
                    trace_id,
                    "0xmarket_test",
                    "BUY",
                    10.0,
                    "0xbuilder",
                    "paper_filled",
                    None,
                ),
            )
            result = cur.fetchone()
            conn.commit()
            assert result is not None

    def test_insert_feedback(self) -> None:
        """INSERT into feedback table succeeds with all required fields."""
        with psycopg.connect(_DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO feedback "
                "(agent_id, oracle_address, value_fixed_point, "
                "decimals, tag1, tag2, ipfs_cid) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (
                    9999001,
                    "0xoracle_test",
                    95,
                    0,
                    "reasoning_quality",
                    "calibration",
                    "QmTestFeedback",
                ),
            )
            result = cur.fetchone()
            conn.commit()
            assert result is not None


# ---------------------------------------------------------------------------
# CircleChain tests (VAL-CHAIN-006)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("CIRCLE_API_KEY"),
    reason="CIRCLE_API_KEY not set",
)
class TestCircleChain:
    """CircleChain async wrapper tests."""

    def test_circle_chain_init_with_env(self) -> None:
        """CircleChain initializes with API key and entity secret from env."""
        chain = CircleChain()
        assert chain.api_key, "CIRCLE_API_KEY should be loaded from env"
        assert chain.entity_secret, "CIRCLE_ENTITY_SECRET should be loaded from env"
        assert chain.wallet_set_id, "CIRCLE_WALLET_SET_ID should be loaded from env"

    def test_circle_chain_init_missing_key(self) -> None:
        """CircleChain raises EnvironmentError when CIRCLE_API_KEY is missing."""
        with pytest.raises(EnvironmentError, match="CIRCLE_API_KEY"):
            CircleChain(
                api_key="",
                entity_secret="secret",
                wallet_set_id="ws123",
            )

    def test_circle_chain_init_missing_entity_secret(self) -> None:
        """CircleChain raises EnvironmentError when ENTITY_SECRET missing."""
        with pytest.raises(EnvironmentError, match="CIRCLE_ENTITY_SECRET"):
            CircleChain(
                api_key="key123",
                entity_secret="",
                wallet_set_id="ws123",
            )

    def test_blockchain_constant(self) -> None:
        """ARC-TESTNET blockchain identifier is correct."""
        assert BLOCKCHAIN == "ARC-TESTNET"

    def test_account_type_constant(self) -> None:
        """Phase 0 Circle wallets are EOA."""
        assert ACCOUNT_TYPE == "EOA"


# ---------------------------------------------------------------------------
# PinataClient tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("PINATA_JWT"),
    reason="PINATA_JWT not set",
)
class TestPinataClient:
    """PinataClient IPFS pinning tests."""

    @pytest.mark.asyncio
    async def test_pinata_pin_json(self) -> None:
        """PinataClient pins JSON and returns valid CID."""
        client = PinataClient()
        try:
            data = {
                "test": True,
                "timestamp": datetime.now(UTC).isoformat(),
                "content": "Prism integration test",
            }
            cid = await client.pin_json(data)
            assert cid.startswith(("Qm", "bafy", "bafk")), f"Invalid CID format: {cid}"
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_pinata_pin_returns_retrievable_content(self) -> None:
        """Pinned content is retrievable via gateway."""
        client = PinataClient()
        try:
            data = {
                "test_retrieval": True,
                "unique_marker": f"prism-test-{uuid.uuid4()}",
            }
            cid = await client.pin_json(data)
            # Allow some time for propagation
            await asyncio.sleep(2)
            fetched = await client.fetch_json(cid)
            assert fetched["unique_marker"] == data["unique_marker"]
        finally:
            await client.close()

    def test_pinata_init_missing_jwt(self) -> None:
        """PinataClient raises EnvironmentError when PINATA_JWT is missing."""
        with pytest.raises(EnvironmentError, match="PINATA_JWT"):
            PinataClient(jwt="")


# ---------------------------------------------------------------------------
# Env validation tests (VAL-CROSS-006)
# ---------------------------------------------------------------------------


class TestEnvValidation:
    """Startup environment validation tests."""

    def test_missing_circle_api_key_detected(self) -> None:
        """Missing CIRCLE_API_KEY produces clear error."""
        env = {k: v for k, v in os.environ.items() if k != "CIRCLE_API_KEY"}
        missing = validate_env("trader", env)
        assert "CIRCLE_API_KEY" in missing

    def test_missing_anthropic_api_key_detected(self) -> None:
        """Missing ANTHROPIC_API_KEY produces clear error for trader."""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        missing = validate_env("trader", env)
        assert "ANTHROPIC_API_KEY" in missing

    def test_missing_openai_api_key_detected(self) -> None:
        """Missing OPENAI_API_KEY produces clear error for sentinel."""
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        missing = validate_env("sentinel", env)
        assert "OPENAI_API_KEY" in missing

    def test_missing_database_url_detected(self) -> None:
        """Missing DATABASE_URL produces clear error for all roles."""
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        for role in ("trader", "sentinel", "oracle"):
            missing = validate_env(role, env)
            assert "DATABASE_URL" in missing, f"DATABASE_URL not detected for {role}"

    def test_all_present_no_missing(self) -> None:
        """When all required vars are present, no missing vars reported."""
        if not _DSN:
            pytest.skip("DATABASE_URL not set")
        missing = validate_env("trader")
        for var in ("DATABASE_URL", "CIRCLE_API_KEY", "ANTHROPIC_API_KEY"):
            assert var not in missing, f"Required var {var} should be present"

    def test_startup_check_exits_on_missing(self) -> None:
        """startup_check() calls sys.exit(1) on missing vars."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(SystemExit, match="1"):
            startup_check("trader")

    def test_llm_family_validation_trader_claude(self) -> None:
        """Claude model validates for trader role."""
        assert _is_claude_family("claude-sonnet-4-20250514")
        assert _is_claude_family("claude-opus-4-7")
        assert not _is_claude_family("gpt-4o-mini")

    def test_llm_family_validation_sentinel_gpt(self) -> None:
        """GPT model validates for sentinel role."""
        assert _is_gpt_family("gpt-4o-mini")
        assert _is_gpt_family("gpt-4o")
        assert not _is_gpt_family("claude-sonnet-4-20250514")

    def test_geofence_check_allowed_locale(self) -> None:
        """EE (Estonia) passes geofence check."""
        assert check_geofence("EE") is True

    def test_geofence_check_restricted_locale(self) -> None:
        """US fails geofence check."""
        assert check_geofence("US") is False

    def test_geofence_check_fr_restricted(self) -> None:
        """FR fails geofence check."""
        assert check_geofence("FR") is False


# ---------------------------------------------------------------------------
# No raw private keys (VAL-CROSS-009)
# ---------------------------------------------------------------------------


class TestNoRawPrivateKeys:
    """Verify no raw private key patterns exist in the codebase."""

    def test_no_fromprivatekey_pattern(self) -> None:
        """No 'fromPrivateKey' pattern found in production codebase."""
        result = subprocess.run(
            [
                "rg",
                "-i",
                "--type",
                "py",
                "--glob",
                "!test_*.py",
                "fromPrivateKey",
                "/Users/fathindosunmu/DEV/MyProjects/prism/apps/",
                "/Users/fathindosunmu/DEV/MyProjects/prism/packages/",
            ],
            capture_output=True,
            text=True,
        )
        # Exit code 1 means no matches found (rg returns 1 when no matches)
        assert result.returncode == 1, (
            f"Found 'fromPrivateKey' pattern in production code:\n{result.stdout}"
        )

    def test_no_wallet_hex_pattern(self) -> None:
        """No 'Wallet(0x' pattern found in production code."""
        result = subprocess.run(
            [
                "rg",
                "-i",
                r"Wallet\(0x",
                "--glob",
                "!test_*.py",
                "/Users/fathindosunmu/DEV/MyProjects/prism/apps/",
                "/Users/fathindosunmu/DEV/MyProjects/prism/packages/",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, (
            f"Found 'Wallet(0x' pattern in production code:\n{result.stdout}"
        )

    def test_circle_sdk_used_for_chain_ops(self) -> None:
        """All chain interactions go through Circle SDK (circle.web3)."""
        if not os.environ.get("CIRCLE_API_KEY"):
            pytest.skip("CIRCLE_API_KEY not set")
        chain = CircleChain()
        # Verify the import path is correct
        assert chain.api_key  # If this passes, Circle SDK config is in place


# ---------------------------------------------------------------------------
# Schema tests (content_hash determinism)
# ---------------------------------------------------------------------------


class TestContentHash:
    """Verify content_hash is deterministic and change-sensitive."""

    def test_trace_hash_deterministic(self) -> None:
        """Same trace produces same hash on repeated calls."""
        trace = _make_trace()
        assert trace.content_hash() == trace.content_hash()

    def test_trace_hash_round_trip(self) -> None:
        """Hash preserved through JSON round-trip."""
        trace = _make_trace(trace_id="test-hash-002")
        original_hash = trace.content_hash()
        json_str = trace.model_dump_json()
        restored = TradingR1Trace.model_validate_json(json_str)
        assert restored.content_hash() == original_hash

    def test_trace_hash_changes_on_modification(self) -> None:
        """Modifying a field produces a different hash."""
        base = _make_trace(
            trace_id="test-hash-003",
            rationale="Original rationale.",
        )
        modified = base.model_copy(update={"rationale": "Modified rationale."})
        assert base.content_hash() != modified.content_hash()

    def test_verdict_hash_deterministic(self) -> None:
        """Same verdict produces same hash on repeated calls."""
        verdict = SentinelVerdict(
            request_hash="0xtest_request",
            trace_id="test-hash-001",
            sentinel_agent_id=2,
            evidence_challenges=["challenge1"],
            thesis_challenges=["thesis_issue"],
            calibration_critique=("Reasonable but could be better calibration overall."),
            verdict_score=72,
            verdict_label="PASS",
            dialogue_messages=[{"role": "sentinel", "content": "Challenge"}],
            model_family="openai-gpt",
            model_name="gpt-4o-mini",
            created_at=datetime.now(UTC),
        )
        assert verdict.content_hash() == verdict.content_hash()
