"""Trader prompt templates for Trading-R1 reasoning traces."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentinel.evidence_tools import EvidenceSearchResult

TRADING_R1_SYSTEM = (
    "You are an expert prediction market trading agent using the "
    "Trading-R1 methodology.\n\n"
    "Given a market question, you must produce a structured reasoning "
    "trace with these stages:\n\n"
    "1. THESIS COMPOSITION: Break down your reasoning into discrete steps. "
    "Each step has a proposition, IDs of supporting evidence, and "
    "risk factors.\n\n"
    "2. EVIDENCE COLLECTION: For each piece of evidence, specify the "
    "source, the claim, your confidence (0.0–1.0), and the timestamp. "
    "Use actual publication/observation timestamps when known. If you do "
    "not have current evidence, say so explicitly and choose HOLD. Do not "
    "invent placeholder sources or timestamps.\n\n"
    "3. VOLATILITY-ADJUSTED DECISION: Start with a raw probability "
    "estimate, apply a volatility adjustment (can be positive or "
    "negative), and arrive at a final probability. This final probability "
    "should be calibrated to reflect your true belief.\n\n"
    "4. DECISION: Based on the final probability, choose an action "
    "(BUY, SELL, or HOLD), specify a size in USDC, a price limit, "
    "and write a clear rationale explaining why this is the right trade.\n\n"
    "IMPORTANT RULES:\n"
    "- For BUY/SELL, size_usdc MUST be small and demo-scale: pick a value "
    "in the 0.5–2 USDC range, typically around 1 USDC (e.g. 0.5, 1.0, 1.5)\n"
    "- For HOLD, size_usdc MUST be 0 and price_limit should be neutral (0.5)\n"
    "- raw_probability and final_probability MUST be between 0.01 and 0.99\n"
    "- confidence in evidence MUST be between 0.0 and 1.0\n"
    "- Every thesis step MUST have at least one supporting_evidence_id\n"
    "- Every thesis step MUST list at least one risk_factor\n"
    "- You MUST have at least 1 piece of evidence\n"
    "- If your evidence is stale, generic, or only historical, choose HOLD "
    "rather than BUY/SELL\n"
    "- The rationale MUST explain the reasoning clearly\n"
    "- Be honest about uncertainty — do not manufacture high confidence "
    "where none exists"
)


def build_evidence_context(search_results: list[EvidenceSearchResult]) -> str:
    """Build a tool-sourced evidence context section for the LLM prompt.

    Formats a list of :class:`EvidenceSearchResult` objects into a structured
    prompt section that instructs the LLM to use the provided real-world
    evidence rather than fabricating sources from its training data.

    Parameters:
        search_results: Evidence results returned by the sentinel /evidence
            endpoint (already validated and parsed).

    Returns:
        A formatted string suitable for injection into the Mirascope prompt.
    """
    if not search_results:
        return ""

    lines: list[str] = [
        "TOOL-SOURCED EVIDENCE (do not fabricate — use this evidence below):",
        "",
        "The following evidence was retrieved by Prism's evidence tools before",
        "trace generation. Use these sources to construct your evidence collection.",
        "Cite the source titles, URLs, and snippets accurately. Do not invent",
        "placeholder sources, URLs, or claims. If any evidence appears outdated",
        "or low-confidence, note this in your volatility adjustment and rationale,",
        "and prefer HOLD if evidence quality is insufficient.",
        "",
    ]

    for i, result in enumerate(search_results, start=1):
        lines.append(f"--- Evidence Item {i} ---")
        lines.append(f"Title: {result.title}")
        lines.append(f"URL: {result.url}")
        lines.append(f"Snippet: {result.snippet}")
        lines.append(f"Provider: {result.provider}")
        if result.tool_name:
            lines.append(f"Tool: {result.tool_name}")
        if result.published_at:
            lines.append(f"Published: {result.published_at}")
        if result.retrieved_at:
            lines.append(f"Retrieved at: {result.retrieved_at}")
        lines.append(f"Confidence: {result.confidence}")
        lines.append("")

    lines.append(
        "Produce a complete Trading-R1 reasoning trace using the tool-sourced "
        "evidence above. Your evidence collection should reference these sources "
        "directly. Your thesis steps should cite evidence IDs that correspond to "
        "the numbered evidence items above. If the evidence does not support a "
        "strong directional view, choose HOLD."
    )

    return "\n".join(lines)
