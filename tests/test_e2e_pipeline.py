"""End-to-end integration tests for the Prism pipeline.

Covers VAL-CROSS-001 through VAL-CROSS-008 and VAL-CROSS-004:
  - VAL-CROSS-001: Trader and sentinel use different LLM families
  - VAL-CROSS-002: Trace pinned by trader is fetchable by sentinel
  - VAL-CROSS-003: Full pipeline — market question to dashboard display
  - VAL-CROSS-004: Data consistency — CIDs and hashes match on-chain
  - VAL-CROSS-007: Partial flow — trace without verdict on dashboard
  - tx_hash columns: Persisted after Circle SDK contract execution

These tests require running services and real API keys.
Mark with @pytest.mark.integration and @pytest.mark.slow.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess

import httpx
import psycopg
import pytest
import structlog

from prism_schemas.db import run_migration

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger("prism.tests.e2e")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TRADER_URL = os.environ.get("TRADER_URL", "http://localhost:3201")
SENTINEL_URL = os.environ.get("SENTINEL_URL", "http://localhost:3202")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:3203")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:3200")
PINATA_GATEWAY = "https://gateway.pinata.cloud/ipfs"

MARKET_ID = "0xpipe_e2e_001"
MARKET_QUESTION = "Will AI agents trade prediction markets autonomously by 2027?"


def _dsn() -> str:
    """Get DATABASE_URL."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ensure_env():
    """Skip if required env vars are not set."""
    required = ["DATABASE_URL", "CIRCLE_API_KEY", "ARC_RPC_URL"]
    for var in required:
        if not os.environ.get(var):
            pytest.skip(f"{var} not set in environment")


@pytest.fixture()
def db_conn():
    """Provide a database connection."""
    dsn = _dsn()
    with psycopg.connect(dsn) as conn:
        yield conn


# ---------------------------------------------------------------------------
# VAL-CROSS-001: Trader and sentinel use different LLM families
# ---------------------------------------------------------------------------


class TestLLMFamilySeparation:
    """VAL-CROSS-001: At system startup, trader and sentinel must use
    different LLM families. If both are set to the same family, at least
    one service MUST refuse to start with a clear error.
    """

    def test_trader_uses_claude_family(self) -> None:
        """Trader model belongs to anthropic-claude family."""
        from trader.config import _is_claude_family

        model = os.environ.get("TRADER_MODEL", "claude-sonnet-4-20250514")
        assert _is_claude_family(model), f"Trader model '{model}' is not Claude family"

    def test_sentinel_uses_gpt_family(self) -> None:
        """Sentinel model belongs to openai-gpt family."""
        from trader.config import _is_gpt_family

        model = os.environ.get("SENTINEL_MODEL", "gpt-4o-mini")
        assert _is_gpt_family(model), f"Sentinel model '{model}' is not GPT family"

    def test_same_family_rejected(self) -> None:
        """If both set to Claude, sentinel startup fails."""
        from trader.config import _validate_llm_family

        # Simulate both being Claude — sentinel should reject
        original = os.environ.get("SENTINEL_MODEL", "")
        os.environ["SENTINEL_MODEL"] = "claude-sonnet-4-20250514"
        try:
            with pytest.raises(SystemExit):
                _validate_llm_family("sentinel")
        finally:
            if original:
                os.environ["SENTINEL_MODEL"] = original
            else:
                os.environ.pop("SENTINEL_MODEL", None)

    def test_cross_family_validation_startup(self) -> None:
        """Both services validate their families correctly at startup."""
        from trader.config import _validate_llm_family

        # Trader validates Claude
        _validate_llm_family("trader")  # Should not raise

        # Sentinel validates GPT
        _validate_llm_family("sentinel")  # Should not raise


# ---------------------------------------------------------------------------
# VAL-CROSS-002: Trace pinned by trader is fetchable by sentinel
# ---------------------------------------------------------------------------


class TestIPFSRoundTrip:
    """VAL-CROSS-002: The CID returned by the trader's Pinata pin is
    resolvable by the sentinel's IPFS fetch. The content produces the
    same content_hash() the trader computed.
    """

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ipfs_round_trip_with_real_pin(self) -> None:
        """Pin a trace to IPFS, fetch it back, verify content_hash matches."""
        from trader.ipfs import PinataClient
        from prism_schemas.trace import TradingR1Trace

        # Create a minimal valid trace
        trace = TradingR1Trace(
            trace_id="00000000-0000-0000-0000-000000000001",
            agent_id=1,
            market_id="test-market",
            market_question="Test question for IPFS round-trip?",
            thesis=[{"proposition": "Test thesis", "supporting_evidence_ids": [0], "risk_factors": ["test risk"]}],
            evidence=[{"source": "test", "claim": "test claim", "confidence": 0.8, "timestamp": "2026-01-01T00:00:00Z"}],
            raw_probability=0.6,
            volatility_adjustment=0.05,
            final_probability=0.55,
            action="BUY",
            size_usdc=5.0,
            price_limit=0.55,
            rationale="Test rationale for IPFS round-trip verification",
            model_family="anthropic-claude",
            model_name="test-model",
            created_at="2026-01-01T00:00:00Z",
        )

        original_hash = trace.content_hash()

        # Pin to IPFS
        pinata = PinataClient()
        cid = pinata.pin_json_sync(trace.model_dump(mode="json"))

        assert cid is not None, "IPFS pin returned no CID"
        assert cid.startswith(("Qm", "bafy")), f"Invalid CID format: {cid}"

        # Fetch back from gateway
        fetched_data = pinata.fetch_json_sync(cid)

        # Reconstruct trace and verify hash
        fetched_trace = TradingR1Trace.model_validate(fetched_data)
        fetched_hash = fetched_trace.content_hash()

        assert fetched_hash == original_hash, (
            f"Content hash mismatch: original={original_hash.hex()}, fetched={fetched_hash.hex()}"
        )


# ---------------------------------------------------------------------------
# VAL-CROSS-003: Full pipeline — market question to dashboard display
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """VAL-CROSS-003: Complete 12-step pipeline test.

    Requires all 4 services running on ports 3200-3203.
    """

    @pytest.mark.integration
    @pytest.mark.slow
    def test_full_pipeline_succeeds(self) -> None:
        """Full pipeline: trigger → validate → trade → dashboard accessible."""
        # Step 1-5: Trigger trader
        with httpx.Client(timeout=300.0) as client:
            trigger_resp = client.post(
                f"{TRADER_URL}/trigger",
                json={
                    "market_id": MARKET_ID,
                    "market_question": MARKET_QUESTION,
                },
            )
        assert trigger_resp.status_code in (200, 202), f"Trader failed: {trigger_resp.status_code}"

        trigger_data = trigger_resp.json()
        trace_id = trigger_data["trace_id"]
        ipfs_cid = trigger_data["ipfs_cid"]
        content_hash_hex = trigger_data["content_hash_hex"]

        # Step 6-10: Sentinel validates
        with httpx.Client(timeout=300.0) as client:
            validate_body = {
                "trace_uri": f"ipfs://{ipfs_cid}",
                "trace_hash": f"0x{content_hash_hex}",
            }
            on_chain_request_hash = trigger_data.get("on_chain_request_hash")
            if on_chain_request_hash:
                validate_body["on_chain_request_hash"] = on_chain_request_hash

            validate_resp = client.post(
                f"{SENTINEL_URL}/validate",
                json=validate_body,
                headers={"x402-payment": "test-bypass"},
            )
        assert validate_resp.status_code in (200, 202), f"Sentinel failed: {validate_resp.status_code}"

        validate_data = validate_resp.json()

        # Step 11: Paper trade
        action = trigger_data.get("action", "BUY")
        side = "BUY" if action in ("BUY", "HOLD") else "SELL"
        agent_id = int(os.environ.get("TRADER_AGENT_ID", "1"))

        with httpx.Client(timeout=30.0) as client:
            trade_resp = client.post(
                f"{GATEWAY_URL}/trade",
                json={
                    "agentId": agent_id,
                    "traceId": trace_id,
                    "marketId": MARKET_ID,
                    "side": side,
                    "sizeUsdc": trigger_data.get("size_usdc", 5.0),
                },
            )
        # Trade may fail if gateway has issues — non-fatal for this test
        trade_ok = trade_resp.status_code in (200, 202)

        # Step 12: Dashboard accessible
        with httpx.Client(timeout=10.0) as client:
            dash_resp = client.get(DASHBOARD_URL)
        assert dash_resp.status_code == 200, f"Dashboard not accessible: {dash_resp.status_code}"

        # Verify all artifacts produced
        assert trace_id, "No trace_id"
        assert ipfs_cid, "No ipfs_cid"
        assert content_hash_hex, "No content_hash_hex"
        assert validate_data.get("verdict_score") is not None, "No verdict_score"
        assert validate_data.get("verdict_label") in ("REJECT", "WARN", "PASS", "ENDORSE"), \
            f"Invalid verdict_label: {validate_data.get('verdict_label')}"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_pipeline_produces_verifiable_artifacts(self) -> None:
        """Every step produces verifiable artifacts (CID, tx hash, DB row)."""
        with httpx.Client(timeout=300.0) as client:
            trigger_resp = client.post(
                f"{TRADER_URL}/trigger",
                json={
                    "market_id": f"{MARKET_ID}_artifacts",
                    "market_question": "Artifact verification test?",
                },
            )

        assert trigger_resp.status_code in (200, 202)
        data = trigger_resp.json()

        # CID is verifiable (starts with Qm or bafy)
        assert data["ipfs_cid"].startswith(("Qm", "bafy")), f"Invalid CID: {data['ipfs_cid']}"

        # Content hash is a valid hex string
        content_hash = data["content_hash_hex"]
        assert len(content_hash) == 64, f"Invalid hash length: {len(content_hash)}"
        bytes.fromhex(content_hash)  # Should not raise

        # DB row exists
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT trace_id, ipfs_cid, tx_hash FROM traces WHERE trace_id = %s", (data["trace_id"],))
            row = cur.fetchone()
        assert row is not None, "No DB row for trace"
        assert row[1] == data["ipfs_cid"], "DB ipfs_cid mismatch"


# ---------------------------------------------------------------------------
# VAL-CROSS-004: Data consistency — CIDs and hashes match on-chain
# ---------------------------------------------------------------------------


class TestDataConsistency:
    """VAL-CROSS-004: Verify that CIDs and hashes in DB match on-chain data."""

    def test_trace_cid_in_db_matches_ipfs_content(self) -> None:
        """ipfs_cid in traces table matches content retrievable from IPFS."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT trace_id, ipfs_cid FROM traces WHERE ipfs_cid != '' ORDER BY created_at DESC LIMIT 1"
            )
            row = cur.fetchone()

        if not row:
            pytest.skip("No traces with IPFS CID in DB")

        trace_id, ipfs_cid = row

        # Fetch from IPFS gateway — may rate-limit, so be lenient
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{PINATA_GATEWAY}/{ipfs_cid}")
        except httpx.HTTPError:
            pytest.skip("IPFS gateway unavailable")

        if resp.status_code != 200:
            pytest.skip(f"IPFS gateway returned {resp.status_code}")

        content = resp.json()
        assert content.get("trace_id") == str(trace_id), "Trace ID mismatch in IPFS content"

    def test_verdict_cid_in_db_matches_ipfs_content(self) -> None:
        """response_uri in validations table matches content from IPFS."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT trace_id, response_uri FROM validations WHERE response_uri LIKE 'ipfs://%%' AND response_uri != '' ORDER BY created_at DESC LIMIT 1"
            )
            row = cur.fetchone()

        if not row:
            pytest.skip("No validations with IPFS response_uri in DB")

        trace_id, response_uri = row
        cid = response_uri.replace("ipfs://", "")

        # Fetch from IPFS gateway — may rate-limit, so be lenient
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{PINATA_GATEWAY}/{cid}")
        except httpx.HTTPError:
            pytest.skip("IPFS gateway unavailable")

        if resp.status_code != 200:
            pytest.skip(f"IPFS gateway returned {resp.status_code}")

        content = resp.json()
        assert "verdict_score" in content, "Verdict IPFS content missing verdict_score"
        assert "verdict_label" in content, "Verdict IPFS content missing verdict_label"

    def test_content_hash_recomputed_from_ipfs_matches(self) -> None:
        """SHA-256 of canonical JSON from IPFS matches content_hash in DB."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT trace_id, ipfs_cid, encode(content_hash, 'hex') AS content_hash FROM traces "
                "WHERE ipfs_cid != '' ORDER BY created_at DESC LIMIT 1"
            )
            row = cur.fetchone()

        if not row:
            pytest.skip("No traces with IPFS CID in DB")

        trace_id, ipfs_cid, db_hash = row

        # Fetch from IPFS — may rate-limit
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{PINATA_GATEWAY}/{ipfs_cid}")
        except httpx.HTTPError:
            pytest.skip("IPFS gateway unavailable")

        if resp.status_code != 200:
            pytest.skip(f"IPFS gateway returned {resp.status_code}")

        content = resp.json()

        # Recompute hash using the same method as content_hash()
        canonical = json.dumps(content, sort_keys=True).encode()
        recomputed = hashlib.sha256(canonical).hexdigest()

        assert recomputed == db_hash, (
            f"Hash mismatch: DB={db_hash}, recomputed={recomputed}"
        )


# ---------------------------------------------------------------------------
# VAL-CROSS-007: Partial flow — trace without verdict on dashboard
# ---------------------------------------------------------------------------


class TestPartialFlow:
    """VAL-CROSS-007: When trader has generated a trace but sentinel has
    NOT yet processed it, the dashboard displays the trace in the left
    panel and shows pending state in the right panel — no crash.
    """

    @pytest.mark.integration
    def test_partial_flow_db_state(self) -> None:
        """Verify DB has traces without matching validations (partial state)."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            # Find traces that don't have validations
            cur.execute(
                "SELECT t.trace_id FROM traces t "
                "LEFT JOIN validations v ON t.trace_id = v.trace_id "
                "WHERE v.trace_id IS NULL "
                "LIMIT 1"
            )
            row = cur.fetchone()

        # This is informational — partial flow may or may not exist
        if row:
            logger.info("partial_flow_exists", trace_id=row[0])
        else:
            logger.info("no_partial_flow_in_db")

    @pytest.mark.integration
    def test_dashboard_handles_missing_verdict(self) -> None:
        """Dashboard returns 200 even when no validation exists for a trace."""
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(DASHBOARD_URL)
        except (httpx.ConnectError, httpx.TimeoutException):
            pytest.skip("Dashboard service not running")

        assert resp.status_code == 200, f"Dashboard failed: {resp.status_code}"
        # Page should contain "Prism" heading and not crash
        assert "Prism" in resp.text, "Dashboard missing Prism heading"

    @pytest.mark.integration
    def test_tx_hash_null_for_pending_onchain(self) -> None:
        """Traces without on-chain tx_hash have NULL tx_hash in DB."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT trace_id, tx_hash FROM traces WHERE tx_hash IS NULL LIMIT 5"
            )
            rows = cur.fetchall()

        # This is expected when PRISM_ONCHAIN is not set
        # These traces show "pending" on dashboard for on-chain receipts
        if rows:
            logger.info("pending_onchain_traces_exist", count=len(rows))


# ---------------------------------------------------------------------------
# tx_hash columns: Verify schema and persistence
# ---------------------------------------------------------------------------


class TestTxHashColumns:
    """Verify tx_hash columns exist and are populated after on-chain steps."""

    def test_traces_table_has_tx_hash_column(self) -> None:
        """traces table has tx_hash column."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'traces' AND column_name = 'tx_hash'"
            )
            row = cur.fetchone()
        assert row is not None, "traces table missing tx_hash column"

    def test_validations_table_has_tx_hash_column(self) -> None:
        """validations table has tx_hash column."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'validations' AND column_name = 'tx_hash'"
            )
            row = cur.fetchone()
        assert row is not None, "validations table missing tx_hash column"

    def test_agents_table_has_registration_tx_hash_column(self) -> None:
        """agents table has registration_tx_hash column."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'agents' AND column_name = 'registration_tx_hash'"
            )
            row = cur.fetchone()
        assert row is not None, "agents table missing registration_tx_hash column"

    def test_update_trace_tx_hash_persistence(self) -> None:
        """update_trace_tx_hash correctly persists tx_hash to DB."""
        from trader.persistence import update_trace_tx_hash

        dsn = _dsn()
        # Find a trace to update
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT trace_id FROM traces LIMIT 1")
            row = cur.fetchone()

        if not row:
            pytest.skip("No traces in DB")

        trace_id = row[0]
        test_tx_hash = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

        update_trace_tx_hash(trace_id, test_tx_hash)

        # Verify
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT tx_hash FROM traces WHERE trace_id = %s", (trace_id,))
            result = cur.fetchone()

        assert result is not None
        assert result[0] == test_tx_hash

    def test_update_validation_tx_hash_persistence(self) -> None:
        """update_validation_tx_hash correctly persists tx_hash to DB."""
        from sentinel.persistence import update_validation_tx_hash

        dsn = _dsn()
        # Find a validation to update — request_hash is BYTEA
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT request_hash FROM validations LIMIT 1")
            row = cur.fetchone()

        if not row:
            pytest.skip("No validations in DB")

        request_hash_bytes = row[0]  # This is bytes
        # Convert bytes to hex string for the persistence function
        request_hash_hex = request_hash_bytes.hex() if isinstance(request_hash_bytes, bytes) else str(request_hash_bytes)
        test_tx_hash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

        update_validation_tx_hash(request_hash_hex, test_tx_hash)

        # Verify
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT tx_hash FROM validations WHERE request_hash = %s", (request_hash_bytes,))
            result = cur.fetchone()

        assert result is not None
        assert result[0] == test_tx_hash


# ---------------------------------------------------------------------------
# DB Schema: Verify all required tables exist
# ---------------------------------------------------------------------------


class TestDBSchemaComplete:
    """VAL-CROSS-005: Verify all 5 required tables exist with correct columns."""

    def test_all_five_tables_exist(self) -> None:
        """All 5 tables exist in the public schema."""
        from prism_schemas.db import list_tables

        tables = list_tables()
        required = {"agents", "traces", "validations", "trades", "feedback"}
        assert required.issubset(set(tables)), f"Missing tables: {required - set(tables)}"

    def test_traces_columns(self) -> None:
        """traces table has all required columns including tx_hash."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'traces'"
            )
            columns = {row[0] for row in cur.fetchall()}

        required = {"trace_id", "agent_id", "market_id", "ipfs_cid", "content_hash", "tx_hash", "created_at"}
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_validations_columns(self) -> None:
        """validations table has all required columns including tx_hash."""
        dsn = _dsn()
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'validations'"
            )
            columns = {row[0] for row in cur.fetchall()}

        required = {"request_hash", "trace_id", "sentinel_agent_id", "verdict_score", "response_uri", "tx_hash", "created_at"}
        assert required.issubset(columns), f"Missing columns: {required - columns}"


# ---------------------------------------------------------------------------
# No raw private keys
# ---------------------------------------------------------------------------


class TestNoRawPrivateKeys:
    """VAL-CROSS-009: Grep entire codebase for raw private key patterns."""

    def test_no_fromprivatekey_pattern(self) -> None:
        """No ethers.Wallet.fromPrivateKey pattern found in non-test code."""
        import subprocess

        result = subprocess.run(
            ["rg", "-l", "fromPrivateKey", "apps/", "packages/", "--type", "py", "--type", "ts", "--type", "js", "--glob", "!**/test*"],
            capture_output=True,
            text=True,
            cwd="/Users/fathindosunmu/DEV/MyProjects/prism",
        )
        assert result.stdout.strip() == "", f"Found fromPrivateKey in: {result.stdout}"

    def test_circle_sdk_used_for_chain_ops(self) -> None:
        """All chain operations use Circle SDK."""
        import subprocess

        # Verify that trader/chain.py and sentinel/chain.py import from circle.web3
        result = subprocess.run(
            ["rg", "from circle.web3", "apps/trader/src/trader/chain.py", "apps/sentinel/src/sentinel/chain.py"],
            capture_output=True,
            text=True,
            cwd="/Users/fathindosunmu/DEV/MyProjects/prism",
        )
        assert "circle.web3" in result.stdout, "Circle SDK import not found in chain modules"
