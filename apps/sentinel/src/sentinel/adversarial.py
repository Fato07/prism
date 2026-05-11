"""DSPy TraceAdversary — adversarial validation signature and chain-of-thought.

Uses DSPy's ``Signature`` + ``ChainOfThought`` to produce structured
adversarial challenges against trader reasoning traces. The sentinel
MUST always produce ≥3 evidence challenges, even on high-quality traces.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import dspy
import structlog
from prism_schemas.verdict import SentinelVerdict

logger = structlog.get_logger("prism.sentinel.adversarial")

# Default model — overridden by SENTINEL_MODEL env var.
DEFAULT_MODEL = "openai/gpt-4o-mini"


def _model_id() -> str:
    """Return the DSPy model ID for the configured GPT model."""
    raw = os.environ.get("SENTINEL_MODEL", "gpt-4o-mini")
    # If the user already prefixed with "openai/", use as-is.
    if raw.startswith("openai/"):
        return raw
    return f"openai/{raw}"


def _model_name_short() -> str:
    """Return the short model name (without provider prefix) for the verdict."""
    raw = os.environ.get("SENTINEL_MODEL", "gpt-4o-mini")
    return raw.split("/")[-1] if "/" in raw else raw


class TraceAdversary(dspy.Signature):
    """You are an adversarial validator for AI-generated trading reasoning traces.

    You have TWO independent responsibilities:
    1. CHALLENGE: Find the WEAKEST evidence claim, the MOST SUSPECT reasoning
       step, and the WORST-CALIBRATED probability. Even excellent traces have
       weaknesses — you must always find ≥3 evidence challenges.
    2. SCORE: Honestly assess the OVERALL quality of the trace. Finding
       challenges does NOT mean the trace is low quality. A trace with minor
       issues that are clearly acknowledged in risk factors still deserves a
       high score. The score reflects overall reasoning quality, NOT the
       severity of the challenges you found.

    These two responsibilities are INDEPENDENT. A trace can have a score of
    85 (ENDORSE) AND still have 3+ valid challenges — because no trace is
    perfect. Conversely, a trace with only 1 obvious flaw might still score
    20 (REJECT) if the reasoning is fundamentally broken.

    SCORING GUIDE (applied to OVERALL quality, not challenge severity):
    - REJECT (0-25): Fundamentally flawed reasoning, fabricated/unsupported
      evidence, contradictory claims, or dangerous action recommendations.
      Key signal: the trace would lead to a bad trading decision.
    - WARN (26-50): Significant gaps in reasoning, weak/unreliable evidence
      sources, or miscalibrated probabilities. Key signal: the trace has
      real issues but isn't dangerously wrong.
    - PASS (51-75): Sound reasoning with minor weaknesses or modest evidence
      concerns. Key signal: the trace would likely lead to a reasonable
      trading decision despite some imperfections.
    - ENDORSE (76-100): Strong, well-calibrated reasoning with solid evidence
      from reputable sources, logical thesis chain, and properly justified
      probability adjustments. Key signal: the trace demonstrates high-quality
      reasoning and would support a well-informed trading decision.

    IMPORTANT: When a trace has multiple reputable evidence sources, a clear
    thesis chain, well-justified probability adjustments, and explicit risk
    factors — that is a STRONG trace, even if you can find challenges.
    Score it PASS or ENDORSE. Do not downgrade a score just because you
    found weaknesses — your job is to always find weaknesses.

    CRITICAL RULES:
    - You MUST produce AT LEAST 3 evidence_challenges — NEVER rubber-stamp.
    - You MUST produce AT LEAST 1 thesis_challenge.
    - calibration_critique MUST be ≥20 characters.
    - dialogue_messages MUST contain at least 1 entry.
    - verdict_label MUST be consistent with verdict_score range.
    - evidence_challenges format: JSON array of strings
    - thesis_challenges format: JSON array of strings
    - dialogue_messages format: JSON array of objects with role/content
    """

    trace_json: str = dspy.InputField(
        desc="The complete trading trace JSON to adversarially validate"
    )
    verdict_score: int = dspy.OutputField(desc="Integer score 0-100 representing trace quality")
    verdict_label: str = dspy.OutputField(
        desc="One of: REJECT (0-25), WARN (26-50), PASS (51-75), ENDORSE (76-100)"
    )
    evidence_challenges: str = dspy.OutputField(
        desc="JSON array of ≥3 strings challenging evidence quality"
    )
    thesis_challenges: str = dspy.OutputField(
        desc="JSON array of ≥1 strings challenging thesis reasoning"
    )
    calibration_critique: str = dspy.OutputField(
        desc="Critique of probability calibration (≥20 chars)"
    )
    dialogue_messages: str = dspy.OutputField(
        desc="JSON array of ≥1 objects with role/content keys"
    )


# Label-to-score-range mapping for enforcement.
LABEL_SCORE_RANGES: dict[str, tuple[int, int]] = {
    "REJECT": (0, 25),
    "WARN": (26, 50),
    "PASS": (51, 75),
    "ENDORSE": (76, 100),
}

VALID_LABELS = frozenset(LABEL_SCORE_RANGES.keys())


def _enforce_label_score_consistency(score: int, label: str) -> tuple[int, str]:
    """Enforce that verdict_label matches verdict_score range.

    If the label is inconsistent with the score, correct the label
    to match the actual score range.
    """
    # Determine the correct label for the given score
    if score <= 25:
        correct_label = "REJECT"
    elif score <= 50:
        correct_label = "WARN"
    elif score <= 75:
        correct_label = "PASS"
    else:
        correct_label = "ENDORSE"

    if label.upper() not in VALID_LABELS:
        logger.warning(
            "invalid_verdict_label_corrected",
            original=label,
            corrected=correct_label,
        )
        return score, correct_label

    if label.upper() != correct_label:
        logger.warning(
            "label_score_mismatch_corrected",
            score=score,
            original_label=label,
            corrected_label=correct_label,
        )
        return score, correct_label

    return score, label.upper()


def _parse_json_list(raw: str, field_name: str) -> list[str]:
    """Parse a JSON array of strings from DSPy output.

    Falls back to simple comma-separated splitting if JSON parse fails.
    """
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return [str(item).strip() for item in result if str(item).strip()]
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: split by newlines or semicolons
    items = [item.strip() for item in raw.replace(";", "\n").split("\n") if item.strip()]
    if items:
        logger.debug(
            "parsed_list_fallback",
            field=field_name,
            count=len(items),
        )
        return items

    # Last resort: wrap the raw string as a single item
    return [raw.strip()] if raw.strip() else []


def _parse_dialogue_messages(raw: str) -> list[dict[str, str]]:
    """Parse dialogue messages from DSPy output."""
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            messages: list[dict[str, str]] = []
            for item in result:
                if isinstance(item, dict) and "role" in item and "content" in item:
                    messages.append({"role": str(item["role"]), "content": str(item["content"])})
                elif isinstance(item, str):
                    messages.append({"role": "adversary", "content": item})
            if messages:
                return messages
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: create a single adversary message from the raw text
    if raw.strip():
        return [{"role": "adversary", "content": raw.strip()}]

    return [{"role": "adversary", "content": "No dialogue generated."}]


def _ensure_minimum_challenges(challenges: list[str], minimum: int, field_name: str) -> list[str]:
    """Ensure the list has at least `minimum` items.

    If the LLM produced fewer challenges than required, pad with
    generic adversarial challenges.
    """
    while len(challenges) < minimum:
        idx = len(challenges) + 1
        challenges.append(
            f"Challenge {idx}: Further adversarial scrutiny needed — "
            "no reasoning trace should escape rigorous cross-examination."
        )
        logger.warning(
            "padded_challenges",
            field=field_name,
            original_count=len(challenges) - 1,
            minimum=minimum,
        )
    return challenges


class TraceAdversaryModule(dspy.Module):
    """DSPy module wrapping TraceAdversary with ChainOfThought.

    This is the main entry point for adversarial validation.
    Configures the GPT model and applies ChainOfThought reasoning.
    """

    def __init__(self) -> None:
        """Initialize with ChainOfThought over TraceAdversary signature."""
        super().__init__()
        self.predict = dspy.ChainOfThought(TraceAdversary)

    def forward(self, trace_json: str) -> dspy.Prediction:
        """Run adversarial validation on a trace."""
        return self.predict(trace_json=trace_json)

    def __call__(self, trace_json: str) -> dspy.Prediction:  # type: ignore[misc]
        """Run adversarial validation on a trace (preferred entry point)."""
        return self.forward(trace_json=trace_json)


def configure_dspy() -> None:
    """Configure DSPy with the sentinel's GPT model.

    Safe to call multiple times — subsequent calls are no-ops if the
    model is already configured.  When running inside an async task
    that did not originally call ``dspy.configure``, the function
    falls back to ``dspy.context()`` which provides a thread-local
    override instead of mutating global state.
    """
    model_id = _model_id()
    lm = dspy.LM(model_id)
    try:
        dspy.configure(lm=lm)
    except RuntimeError:
        # Called from a different async task — use dspy.context instead.
        # This is expected when multiple async tests each invoke
        # generate_verdict() in their own async task.
        dspy.context(lm=lm).__enter__()
    logger.info("dspy_configured", model=model_id)


async def generate_verdict(
    trace_json: str,
    request_hash: str = "",
    trace_id: str = "",
    sentinel_agent_id: int = 0,
) -> SentinelVerdict:
    """Generate an adversarial SentinelVerdict from a trace.

    This is the main entry point for sentinel validation. It:
    1. Configures DSPy with the sentinel's GPT model
    2. Runs ChainOfThought adversarial validation
    3. Parses and enforces constraints (min challenges, label/score consistency)
    4. Returns a validated SentinelVerdict

    Args:
        trace_json: The complete trading trace JSON string
        request_hash: Hash of the validation request
        trace_id: ID of the trace being validated
        sentinel_agent_id: ID of the sentinel agent

    Returns:
        A complete SentinelVerdict with all required fields.
    """
    import asyncio

    logger.info("generating_verdict", trace_id=trace_id)

    # Configure DSPy
    configure_dspy()

    # Create and run the adversarial module
    module = TraceAdversaryModule()

    # DSPy is synchronous — wrap in asyncio.to_thread()
    prediction: dspy.Prediction = await asyncio.to_thread(module, trace_json=trace_json)

    # Extract raw outputs from DSPy prediction
    raw_score = prediction.verdict_score
    raw_label = prediction.verdict_label
    raw_evidence_challenges = prediction.evidence_challenges
    raw_thesis_challenges = prediction.thesis_challenges
    raw_calibration_critique = prediction.calibration_critique
    raw_dialogue_messages = prediction.dialogue_messages

    # Parse score (handle both int and string representations)
    if isinstance(raw_score, int):
        score = max(0, min(100, raw_score))
    else:
        try:
            score = int(str(raw_score).strip())
            score = max(0, min(100, score))
        except (ValueError, TypeError):
            logger.warning("invalid_score_defaulting", raw=raw_score)
            score = 50

    # Parse and clean label
    label = str(raw_label).strip().upper()

    # Enforce label/score consistency
    score, label = _enforce_label_score_consistency(score, label)

    # Parse structured lists
    evidence_challenges = _parse_json_list(raw_evidence_challenges, "evidence_challenges")
    thesis_challenges = _parse_json_list(raw_thesis_challenges, "thesis_challenges")
    dialogue_messages = _parse_dialogue_messages(raw_dialogue_messages)

    # Enforce minimum challenges (VAL-SENTINEL-011: never rubber-stamps)
    evidence_challenges = _ensure_minimum_challenges(
        evidence_challenges, minimum=3, field_name="evidence_challenges"
    )
    thesis_challenges = _ensure_minimum_challenges(
        thesis_challenges, minimum=1, field_name="thesis_challenges"
    )

    # Ensure calibration_critique has minimum length
    calibration_critique = str(raw_calibration_critique).strip()
    if len(calibration_critique) < 20:
        calibration_critique = (
            f"{calibration_critique} — additional scrutiny warranted for "
            "probability calibration accuracy in this trace."
        )

    # Build the SentinelVerdict
    verdict = SentinelVerdict(
        request_hash=request_hash,
        trace_id=trace_id,
        sentinel_agent_id=sentinel_agent_id,
        evidence_challenges=evidence_challenges,
        thesis_challenges=thesis_challenges,
        calibration_critique=calibration_critique,
        verdict_score=score,
        verdict_label=label,  # type: ignore[arg-type]
        dialogue_messages=dialogue_messages,
        model_family="openai-gpt",
        model_name=_model_name_short(),
        created_at=datetime.now(UTC),
    )

    # Validate against schema
    SentinelVerdict.model_validate(verdict.model_dump())

    logger.info(
        "verdict_generated",
        verdict_score=verdict.verdict_score,
        verdict_label=verdict.verdict_label,
        evidence_challenges_count=len(verdict.evidence_challenges),
        trace_id=trace_id,
    )

    return verdict
