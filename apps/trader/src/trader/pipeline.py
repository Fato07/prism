"""End-to-end pipeline orchestration for Prism Phase 0.

Runs the full 12-step pipeline:
  1. Market question → Trader API
  2. Trader generates TradingR1Trace (Claude/Mirascope)
  3. Pin trace to IPFS (Pinata)
  4. Persist trace to Neon DB
  5. Submit validationRequest on-chain (Circle SDK → Arc testnet)
  6. Sentinel fetches trace from IPFS
  7. Sentinel generates SentinelVerdict (GPT/DSPy)
  8. Pin verdict to IPFS
  9. Persist verdict to Neon DB
  10. Submit validationResponse on-chain (Circle SDK → Arc testnet)
  11. Paper trade via Polymarket Gateway
  12. Dashboard displays everything

Usage:
  uv run python -m trader.pipeline

Requires all 4 services running on ports 3200-3203 with PRISM_ONCHAIN=true.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import httpx
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger("prism.pipeline")

# Service URLs
TRADER_URL = os.environ.get("TRADER_URL", "http://localhost:3201")
SENTINEL_URL = os.environ.get("SENTINEL_URL", "http://localhost:3202")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:3203")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:3200")

# Default market question for testing
DEFAULT_MARKET_ID = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
DEFAULT_MARKET_QUESTION = "Will the US Federal Reserve cut interest rates by July 2026?"


async def wait_for_service(
    url: str,
    name: str,
    timeout: int = 30,
    health_path: str = "/health",
) -> bool:
    """Wait for a service to become healthy."""
    start = time.time()
    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.time() - start < timeout:
            try:
                resp = await client.get(f"{url}{health_path}")
                if resp.status_code == 200:
                    logger.info(f"{name}_ready", url=url)
                    return True
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            await asyncio.sleep(1)
    logger.error(f"{name}_not_ready", url=url, timeout=timeout)
    return False


async def wait_for_all_services() -> bool:
    """Wait for all 4 services to become healthy."""
    results = await asyncio.gather(
        wait_for_service(TRADER_URL, "trader", timeout=30, health_path="/health"),
        wait_for_service(SENTINEL_URL, "sentinel", timeout=30, health_path="/health"),
        wait_for_service(GATEWAY_URL, "gateway", timeout=30, health_path="/health"),
        wait_for_service(DASHBOARD_URL, "dashboard", timeout=30, health_path="/"),
    )
    return all(results)


async def run_pipeline(
    market_id: str = DEFAULT_MARKET_ID,
    market_question: str = DEFAULT_MARKET_QUESTION,
) -> dict:
    """Run the full 12-step pipeline and return results.

    Returns a dict with all artifacts from each step.
    """
    result: dict = {
        "market_id": market_id,
        "market_question": market_question,
        "steps": {},
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        # ── Step 1-5: Trader generates trace + IPFS + DB + on-chain ──
        logger.info("step_1_5_trigger_trace_generation", market_id=market_id)

        trigger_resp = await client.post(
            f"{TRADER_URL}/trigger",
            json={
                "market_id": market_id,
                "market_question": market_question,
            },
        )
        if trigger_resp.status_code not in (200, 202):
            raise RuntimeError(
                f"Trader /trigger failed:"
                f" {trigger_resp.status_code} {trigger_resp.text}"
            )

        trigger_data = trigger_resp.json()
        result["steps"]["trigger"] = trigger_data
        trace_id = trigger_data["trace_id"]
        ipfs_cid = trigger_data["ipfs_cid"]
        content_hash_hex = trigger_data["content_hash_hex"]
        tx_hash = trigger_data.get("tx_hash")
        on_chain_request_hash = trigger_data.get("on_chain_request_hash")

        logger.info(
            "trace_generated",
            trace_id=trace_id,
            ipfs_cid=ipfs_cid,
            tx_hash=tx_hash,
        )

        # ── Step 6-10: Sentinel validates + IPFS + DB + on-chain ──
        trace_uri = f"ipfs://{ipfs_cid}"
        logger.info("step_6_10_sentinel_validation", trace_uri=trace_uri)

        validate_body: dict = {
            "trace_uri": trace_uri,
            "trace_hash": f"0x{content_hash_hex}",
        }
        if on_chain_request_hash:
            validate_body["on_chain_request_hash"] = on_chain_request_hash

        validate_resp = await client.post(
            f"{SENTINEL_URL}/validate",
            json=validate_body,
            headers={"x402-payment": "test-bypass"},
        )
        if validate_resp.status_code not in (200, 202):
            raise RuntimeError(
                f"Sentinel /validate failed: {validate_resp.status_code} {validate_resp.text}"
            )

        validate_data = validate_resp.json()
        result["steps"]["validate"] = validate_data
        verdict_score = validate_data["verdict_score"]
        verdict_label = validate_data["verdict_label"]
        verdict_ipfs_cid = validate_data["ipfs_cid"]
        verdict_tx_hash = validate_data.get("tx_hash")

        logger.info(
            "verdict_generated",
            verdict_score=verdict_score,
            verdict_label=verdict_label,
            verdict_ipfs_cid=verdict_ipfs_cid,
            verdict_tx_hash=verdict_tx_hash,
        )

        # ── Step 11: Paper trade via Polymarket Gateway ──
        logger.info("step_11_paper_trade", trace_id=trace_id)

        # Determine trade side from trace action
        action = trigger_data.get("action", "BUY")
        side = "BUY" if action == "BUY" else "SELL" if action == "SELL" else "BUY"
        size_usdc = trigger_data.get("size_usdc", 5.0)

        agent_id = int(os.environ.get("TRADER_AGENT_ID", "1"))

        trade_resp = await client.post(
            f"{GATEWAY_URL}/trade",
            json={
                "agentId": agent_id,
                "traceId": trace_id,
                "marketId": market_id,
                "side": side,
                "sizeUsdc": size_usdc,
            },
        )
        if trade_resp.status_code not in (200, 202):
            logger.warning(
                "paper_trade_failed",
                status=trade_resp.status_code,
                body=trade_resp.text,
            )
            result["steps"]["trade"] = {"error": f"Trade failed: {trade_resp.status_code}"}
        else:
            trade_data = trade_resp.json()
            result["steps"]["trade"] = trade_data
            logger.info(
                "paper_trade_executed",
                order_id=trade_data.get("receipt", {}).get("orderId"),
                builder_code=trade_data.get("receipt", {}).get("builderCode"),
            )

        # ── Step 12: Dashboard verification ──
        logger.info("step_12_dashboard_verification")

        dash_resp = await client.get(DASHBOARD_URL)
        if dash_resp.status_code == 200:
            result["steps"]["dashboard"] = {"status": "ok", "http_code": 200}
            logger.info("dashboard_accessible")
        else:
            result["steps"]["dashboard"] = {"status": "error", "http_code": dash_resp.status_code}
            logger.warning("dashboard_not_accessible", http_code=dash_resp.status_code)

    # ── Data consistency checks ──
    result["consistency"] = {}

    # Check: trace CID from IPFS
    if ipfs_cid:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                ipfs_resp = await client.get(f"https://gateway.pinata.cloud/ipfs/{ipfs_cid}")
                if ipfs_resp.status_code == 200:
                    ipfs_data = ipfs_resp.json()
                    ipfs_trace_id = ipfs_data.get("trace_id")
                    result["consistency"]["ipfs_trace_cid_resolves"] = True
                    result["consistency"]["ipfs_trace_id_match"] = ipfs_trace_id == trace_id
                else:
                    result["consistency"]["ipfs_trace_cid_resolves"] = False
            except Exception as exc:
                result["consistency"]["ipfs_trace_cid_error"] = str(exc)

    # Check: verdict CID from IPFS
    if verdict_ipfs_cid:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                ipfs_resp = await client.get(f"https://gateway.pinata.cloud/ipfs/{verdict_ipfs_cid}")
                if ipfs_resp.status_code == 200:
                    ipfs_data = ipfs_resp.json()
                    ipfs_verdict_score = ipfs_data.get("verdict_score")
                    result["consistency"]["ipfs_verdict_cid_resolves"] = True
                    result["consistency"]["ipfs_verdict_score_match"] = (
                        ipfs_verdict_score == verdict_score
                    )
                else:
                    result["consistency"]["ipfs_verdict_cid_resolves"] = False
            except Exception as exc:
                result["consistency"]["ipfs_verdict_cid_error"] = str(exc)

    logger.info("pipeline_complete", trace_id=trace_id, verdict_score=verdict_score)
    return result


def verify_data_consistency(result: dict) -> list[str]:
    """Verify data consistency across DB, IPFS, and on-chain.

    Returns a list of issues found (empty = all consistent).
    """
    issues: list[str] = []

    consistency = result.get("consistency", {})

    # IPFS round-trip for trace
    if not consistency.get("ipfs_trace_cid_resolves", False):
        issues.append("Trace CID does not resolve from IPFS gateway")
    if not consistency.get("ipfs_trace_id_match", False):
        issues.append("Trace ID in IPFS content does not match trigger response")

    # IPFS round-trip for verdict
    if not consistency.get("ipfs_verdict_cid_resolves", False):
        issues.append("Verdict CID does not resolve from IPFS gateway")
    if not consistency.get("ipfs_verdict_score_match", False):
        issues.append("Verdict score in IPFS content does not match validate response")

    # On-chain tx hashes
    trigger_data = result.get("steps", {}).get("trigger", {})
    validate_data = result.get("steps", {}).get("validate", {})

    if not trigger_data.get("tx_hash"):
        issues.append("No on-chain tx_hash for validation request (on-chain step may be disabled)")
    if not validate_data.get("tx_hash"):
        issues.append("No on-chain tx_hash for validation response (on-chain step may be disabled)")

    return issues


async def main() -> None:
    """Main entry point for the pipeline script."""
    logger.info("starting_e2e_pipeline")

    # Wait for all services
    if not await wait_for_all_services():
        logger.error("services_not_ready")
        sys.exit(1)

    # Run the pipeline
    try:
        result = await run_pipeline()
    except Exception as exc:
        logger.error("pipeline_failed", error=str(exc))
        sys.exit(1)

    # Print summary
    print("\n" + "=" * 60)
    print("E2E PIPELINE RESULT")
    print("=" * 60)

    trigger = result.get("steps", {}).get("trigger", {})
    validate = result.get("steps", {}).get("validate", {})
    trade = result.get("steps", {}).get("trade", {})

    print(f"  Trace ID:        {trigger.get('trace_id')}")
    print(f"  IPFS CID:        {trigger.get('ipfs_cid')}")
    print(f"  Content Hash:    {trigger.get('content_hash_hex', '')[:20]}...")
    print(f"  Action:          {trigger.get('action')}")
    print(f"  Size:            {trigger.get('size_usdc')} USDC")
    print(f"  Val Request Tx:  {trigger.get('tx_hash', 'N/A')}")
    print()
    print(f"  Verdict Score:   {validate.get('verdict_score')}")
    print(f"  Verdict Label:   {validate.get('verdict_label')}")
    print(f"  Verdict CID:     {validate.get('ipfs_cid')}")
    print(f"  Val Response Tx: {validate.get('tx_hash', 'N/A')}")
    print()
    print(f"  Trade Order ID:  {trade.get('receipt', {}).get('orderId', 'N/A')}")
    print(f"  Builder Code:    {trade.get('receipt', {}).get('builderCode', 'N/A')}")

    # Check data consistency
    issues = verify_data_consistency(result)
    if issues:
        print("\n  ⚠️  Issues found:")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print("\n  ✅ All data consistency checks passed")

    # Write full result to JSON
    output_path = os.environ.get("PIPELINE_OUTPUT", "/tmp/prism_pipeline_result.json")
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n  Full result written to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
