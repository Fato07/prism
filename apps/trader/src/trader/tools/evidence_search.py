"""Evidence search tool — calls the sentinel's /evidence endpoint.

This tool retrieves structured market evidence from the sentinel before
the trader generates a Trading-R1 reasoning trace.  The results are
injected into the Mirascope prompt as tool-sourced context and mapped to
:class:`EvidenceToolReceipt` objects for the trace's ``evidence_receipts``
field.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx
import structlog
from prism_schemas.verdict import EvidenceToolReceipt
from pydantic import ValidationError

if TYPE_CHECKING:
    from sentinel.evidence_tools import EvidenceSearchResult

logger = structlog.get_logger("prism.trader.evidence_search")

# Default sentinel URL and timeout.
_DEFAULT_SENTINEL_URL = "http://localhost:3202"
_DEFAULT_TIMEOUT_SECONDS = 10.0


def _sentinel_evidence_url() -> str:
    """Return the sentinel /evidence URL from env (default localhost:3202/evidence)."""
    base = os.environ.get("SENTINEL_EVIDENCE_URL", _DEFAULT_SENTINEL_URL).rstrip("/")
    return f"{base}/evidence"


def _evidence_search_timeout() -> float:
    """Return the evidence search timeout in seconds from env or default."""
    raw = os.environ.get("EVIDENCE_SEARCH_TIMEOUT_SECONDS", "")
    if not raw.strip():
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
        if value <= 0:
            logger.warning(
                "evidence_search_invalid_timeout",
                raw=raw,
                fallback=_DEFAULT_TIMEOUT_SECONDS,
            )
            return _DEFAULT_TIMEOUT_SECONDS
        return value
    except ValueError:
        logger.warning(
            "evidence_search_non_numeric_timeout",
            raw=raw,
            fallback=_DEFAULT_TIMEOUT_SECONDS,
        )
        return _DEFAULT_TIMEOUT_SECONDS


async def evidence_search(
    market_question: str,
    *,
    max_results: int = 5,
) -> list[EvidenceSearchResult]:
    """Call the sentinel /evidence endpoint for structured market evidence.

    Reads ``SENTINEL_EVIDENCE_URL`` from the environment (defaults to
    ``http://localhost:3202``).  The request includes an ``X402-Bypass``
    header so the internal trader→sentinel call is not paywalled.

    Parameters:
        market_question: The market question to research (sent as both
            ``market_question`` and ``query`` fields).
        max_results: Maximum number of evidence results to request (1–20).

    Returns:
        A list of :class:`EvidenceSearchResult` objects, or an empty list
        if the sentinel is unreachable, returns a malformed response, or
        encounters any other error.  Errors are logged but never propagated.

    The timeout is controlled by ``EVIDENCE_SEARCH_TIMEOUT_SECONDS`` (default
    10 s).  If the sentinel does not respond within the timeout, the call
    is cancelled and an empty list is returned.
    """
    url = _sentinel_evidence_url()
    timeout = _evidence_search_timeout()

    logger.info(
        "evidence_search_starting",
        url=url,
        market_question=market_question[:100],
        timeout=timeout,
    )

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.post(
                url,
                json={
                    "market_question": market_question,
                    "query": market_question,
                    "max_results": max_results,
                },
                headers={
                    "X402-Bypass": os.environ.get("X402_INTERNAL_BYPASS_TOKEN", "true"),
                    "Content-Type": "application/json",
                },
            )

            if response.status_code != 200:
                logger.warning(
                    "evidence_search_http_error",
                    url=url,
                    status_code=response.status_code,
                    body=response.text[:300],
                )
                return []

            body = response.json()

            # Validate the response structure with basic shape checks
            if not isinstance(body, dict) or "results" not in body:
                logger.warning(
                    "evidence_search_malformed_response",
                    url=url,
                    body=str(body)[:300],
                )
                return []

            results_raw = body.get("results", [])
            if not isinstance(results_raw, list):
                logger.warning(
                    "evidence_search_results_not_a_list",
                    url=url,
                    body=str(body)[:300],
                )
                return []

            # Parse each result into an EvidenceSearchResult.
            # We import lazily to avoid circular imports.
            from sentinel.evidence_tools import EvidenceSearchResult

            results: list[EvidenceSearchResult] = []
            for item in results_raw:
                try:
                    results.append(EvidenceSearchResult.model_validate(item))
                except ValidationError as exc:
                    logger.warning(
                        "evidence_search_result_validation_failed",
                        url=url,
                        item=str(item)[:200],
                        error=str(exc)[:200],
                    )

            logger.info(
                "evidence_search_complete",
                url=url,
                result_count=len(results),
                budget_remaining=body.get("budget_remaining", -1),
            )
            return results

    except httpx.TimeoutException:
        logger.warning(
            "evidence_search_timeout",
            url=url,
            timeout=timeout,
        )
        return []
    except httpx.ConnectError as exc:
        logger.warning(
            "evidence_search_sentinel_unavailable",
            url=url,
            error=str(exc),
        )
        return []
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning(
            "evidence_search_error",
            url=url,
            error=type(exc).__name__,
            detail=str(exc)[:200],
        )
        return []


def map_result_to_receipt(result: EvidenceSearchResult) -> EvidenceToolReceipt:
    """Map an :class:`EvidenceSearchResult` to an :class:`EvidenceToolReceipt`.

    The mapping is direct — the two schemas share the same field names for
    the core provenance fields.  Additional receipt fields (``adequacy_checks``,
    ``source_content_hash``, etc.) are left at their defaults since the
    sentinel /evidence endpoint only fills the core search-result fields.
    """
    return EvidenceToolReceipt(
        provider=result.provider,
        tool_name=result.tool_name,
        source_title=result.title,
        source_url=result.url,
        source_published_at=result.published_at,
        retrieved_at=result.retrieved_at,
        confidence=result.confidence,
    )
