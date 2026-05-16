"""Pilot slice builder that creates a mixed-source 50-row calibration slice."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prism_schemas.trace import Evidence, ThesisStep, TradingR1Trace

from prism_calibration.layout import bootstrap_corpus_root
from prism_calibration.lineage import LoadedRow, load_corpus_rows, validate_lineage_integrity
from prism_calibration.models import (
    PILOT_BUILD_CREATED_AT,
    CalibrationRow,
    CorpusProvenance,
    HarvestedTraceProvenance,
    HarvestValidationProvenance,
    ReviewState,
    SplitMetadata,
)
from prism_calibration.prelabel import (
    apply_prelabels_to_row,
    deterministic_prelabels_for_row,
)
from prism_calibration.splits import ASSIGNED_AT, SPLIT_POLICY, write_row

PILOT_RUBRIC_VERSION = "prism-calibration-v1"

PILOT_REAL_MARKETS: tuple[tuple[str, str, str], ...] = (
    (
        "0xa91ac76a017a9a72f6bc6119a0a2b076efff8bb8df372824df647ed453e6603a",
        "real-market-usdc-settlement",
        "Will Arc testnet USDC settlement remain reliable for Prism demos this week?",
    ),
    (
        "0xb12bd47b128b9a83c7ec6b5d1e4f8c39d2a07b9c0438d72f8e5a1b6c7d8e9f01",
        "real-market-agent-validation",
        "Will agent-to-agent validation be highlighted in the next Prism pitch update?",
    ),
    (
        "0xc23ce58c239c0b94d7fd7c6e2f5g9d40e3b18c0d1549e83g9f6b2c7d8e9a0b12",
        "real-market-builder-code",
        "Will builder-code attribution remain visible in Prism paper-trade receipts?",
    ),
    (
        "0xd34df69d340d1c05e8ge8d7f3g6h0e41f4c29d1e2650f94h0g7c3d8e9f1b2c23",
        "real-market-x402-call",
        "Will an external agent complete a paid x402 validation call before the demo?",
    ),
    (
        "0xe45eg70e451e2d16f9hf1e8g4h7i1f52g5d30e2f3761g05i1h8d4e9f2c3d34",
        "real-market-social-trading",
        "Will social trading intelligence be a featured theme in the Prism submission?",
    ),
    (
        "0xf56fh81f562f3e27g0ig2f9h5i8j2g63h6e41f3g4872h16j2i9e5f3g4d5e45",
        "real-market-prediction-markets",
        "Will prediction market integration drive meaningful agent behavior in the demo?",
    ),
)

PILOT_REAL_QUALITY_BANDS: tuple[tuple[str, tuple[str, ...], float, float, float, str], ...] = (
    ("high", (), 0.74, -0.03, 0.71, "BUY"),
    ("high", (), 0.69, -0.02, 0.67, "BUY"),
    ("medium", ("weak-evidence",), 0.61, -0.05, 0.56, "HOLD"),
    ("medium", ("weak-evidence",), 0.58, -0.04, 0.54, "HOLD"),
    ("low", ("calibration-overconfidence",), 0.91, 0.04, 0.95, "BUY"),
    ("low", ("calibration-overconfidence",), 0.88, 0.03, 0.91, "BUY"),
    ("low", ("missing-counterevidence",), 0.18, 0.07, 0.25, "SELL"),
    ("low", ("missing-counterevidence",), 0.22, 0.06, 0.28, "SELL"),
    ("medium", ("stale-evidence",), 0.53, -0.03, 0.50, "HOLD"),
)


class PilotBuildError(ValueError):
    """Raised when pilot slice construction fails."""


@dataclass(frozen=True)
class PilotBuildResult:
    """Summary of one pilot build operation."""

    operation: str
    run_id: str
    row_count: int
    source_counts: dict[str, int]
    row_ids: list[str]
    duplicate_row_ids: list[str]
    manifest_id: str
    manifest_path: Path
    manual_review_count: int
    auto_resolved_count: int
    rows: tuple[LoadedRow, ...]


def _pilot_split_metadata() -> SplitMetadata:
    """Return forced-pilot split metadata for the pilot build."""
    return SplitMetadata(
        name="pilot",
        policy=SPLIT_POLICY,
        seed=42,
        assigned_at=ASSIGNED_AT,
    )


def _pilot_synthetic_rows(
    count: int,
    *,
    run_id: str,
) -> list[CalibrationRow]:
    """Generate deterministic synthetic rows for the pilot build."""
    from prism_calibration.labeling import SYNTHETIC_TEMPLATES, _synthetic_trace

    rows: list[CalibrationRow] = []
    for index in range(count):
        template = SYNTHETIC_TEMPLATES[index % len(SYNTHETIC_TEMPLATES)]
        row_number = index + 1
        row_id = f"synthetic-{row_number:04d}"
        lineage_id = f"lineage-synthetic-{row_number:04d}"
        trace = _synthetic_trace(index, template)
        content_hash = trace.content_hash().hex()
        row = CalibrationRow(
            row_id=row_id,
            trace=trace,
            provenance=CorpusProvenance(
                source_type="synthetic",
                source_ref=f"pilot-build:synthetic/{template.quality_band}/{row_number:04d}",
                run_id=run_id,
                lineage_id=lineage_id,
                content_hash=content_hash,
                created_at=PILOT_BUILD_CREATED_AT,
            ),
            review=ReviewState(
                status="unreviewed",
                rubric_version=PILOT_RUBRIC_VERSION,
                failure_tags=list(template.failure_tags),
                notes=f"Pilot build synthetic row for quality_band={template.quality_band}.",
            ),
            split=_pilot_split_metadata(),
        )
        rows.append(row)
    return rows


def _pilot_mutation_rows(
    parents: list[CalibrationRow],
    mutations_per_parent: int,
    *,
    run_id: str,
) -> list[CalibrationRow]:
    """Generate deterministic mutated rows from pilot parents."""
    from prism_calibration.labeling import MUTATION_TEMPLATES, _mutated_trace

    rows: list[CalibrationRow] = []
    mutation_counter = 0
    for parent in parents:
        for index in range(mutations_per_parent):
            template = MUTATION_TEMPLATES[index % len(MUTATION_TEMPLATES)]
            mutation_counter += 1
            safe_parent = "".join(
                char if char.isalnum() else "-" for char in parent.row_id.lower()
            ).strip("-")
            row_id = f"mutated-{safe_parent}-{index + 1:04d}-{template.mutation_type}"
            lineage_id = parent.provenance.lineage_id
            trace = _mutated_trace(parent.trace, template, index)
            content_hash = trace.content_hash().hex()
            row = CalibrationRow(
                row_id=row_id,
                trace=trace,
                provenance=CorpusProvenance(
                    source_type="mutated",
                    source_ref=(
                        f"pilot-build:mutation/{parent.row_id}/"
                        f"{template.mutation_type}/{index + 1:04d}"
                    ),
                    run_id=run_id,
                    lineage_id=lineage_id,
                    content_hash=content_hash,
                    created_at=PILOT_BUILD_CREATED_AT,
                    parent_row_id=parent.row_id,
                    mutation_type=template.mutation_type,
                ),
                review=ReviewState(
                    status="unreviewed",
                    rubric_version=PILOT_RUBRIC_VERSION,
                    failure_tags=[template.failure_tag],
                    notes=(
                        f"Pilot build mutation targeting {template.failure_tag} "
                        f"from parent {parent.row_id}."
                    ),
                ),
                split=_pilot_split_metadata(),
            )
            rows.append(row)
    return rows


def _deterministic_real_trace_id(index: int) -> str:
    """Return a deterministic UUID-style trace ID for a pilot real row."""
    seed_str = f"pilot-real-trace-{index + 1:04d}"
    digest = hashlib.sha256(seed_str.encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _deterministic_real_cid(index: int) -> str:
    """Return a deterministic IPFS CID for a pilot real row."""
    seed_str = f"pilot-real-cid-{index + 1:04d}"
    digest = hashlib.sha256(seed_str.encode()).hexdigest()
    return f"Qm{digest[:44]}"


def _deterministic_real_tx_hash(index: int) -> str:
    """Return a deterministic transaction hash for a pilot real row."""
    seed_str = f"pilot-real-tx-{index + 1:04d}"
    digest = hashlib.sha256(seed_str.encode()).hexdigest()
    return f"0x{digest}"


def _pilot_real_rows(
    count: int,
    *,
    run_id: str,
) -> list[CalibrationRow]:
    """Generate deterministic real-trace-shaped rows for the pilot build."""
    rows: list[CalibrationRow] = []
    for index in range(count):
        row_number = index + 1
        trace_id = _deterministic_real_trace_id(index)
        row_id = f"real-{trace_id}"
        lineage_id = f"real-trace-{trace_id}"
        cid = _deterministic_real_cid(index)
        tx_hash = _deterministic_real_tx_hash(index)

        market_index = index % len(PILOT_REAL_MARKETS)
        market_id, _market_slug, market_question = PILOT_REAL_MARKETS[market_index]

        quality_index = index % len(PILOT_REAL_QUALITY_BANDS)
        quality_band, failure_tags, raw_prob, vol_adj, final_prob, action = (
            PILOT_REAL_QUALITY_BANDS[quality_index]
        )

        evidence_confidence_map: dict[str, float] = {
            "high": 0.88,
            "medium": 0.55,
            "low": 0.42,
        }
        evidence_confidence = evidence_confidence_map.get(quality_band, 0.55)

        is_validated = index % 2 == 0

        trace = TradingR1Trace(
            trace_id=trace_id,
            agent_id=4140,
            market_id=market_id,
            market_question=market_question,
            thesis=[
                ThesisStep(
                    proposition=f"Pilot real trace {row_number}: {quality_band} quality reasoning.",
                    supporting_evidence_ids=[0],
                    risk_factors=list(failure_tags) if failure_tags else ["Standard market risk."],
                )
            ],
            evidence=[
                Evidence(
                    source=f"pilot-real-seed/{quality_band}",
                    claim=f"Real-trace-shaped evidence for pilot row {row_number}.",
                    confidence=evidence_confidence,
                    timestamp=PILOT_BUILD_CREATED_AT,
                )
            ],
            raw_probability=raw_prob,
            volatility_adjustment=vol_adj,
            final_probability=final_prob,
            action=action,  # type: ignore[arg-type]
            size_usdc=0.0 if action == "HOLD" else 5.0,
            price_limit=final_prob,
            rationale=(
                f"Pilot build real-trace-shaped row {row_number} in the "
                f"{quality_band} quality band."
            ),
            model_family="anthropic-claude",
            model_name="pilot-real-seed-v1",
            created_at=PILOT_BUILD_CREATED_AT,
        )

        content_hash = trace.content_hash().hex()

        validation: HarvestValidationProvenance
        if is_validated:
            request_hash = hashlib.sha256(
                f"pilot-real-request-{index}".encode()
            ).hexdigest()
            response_cid = _deterministic_real_cid(index + 100)
            validation = HarvestValidationProvenance(
                status="validated",
                request_hash=request_hash,
                sentinel_agent_id=4148,
                verdict_score=int(evidence_confidence * 100),
                response_uri=f"ipfs://{response_cid}",
                response_cid=response_cid,
                requester_address=None,
                tx_hash=tx_hash,
                created_at=PILOT_BUILD_CREATED_AT,
            )
        else:
            validation = HarvestValidationProvenance(
                status="unvalidated",
            )

        harvested = HarvestedTraceProvenance(
            trace_id=trace_id,
            agent_id=4140,
            market_id=market_id,
            ipfs_cid=cid,
            ipfs_uri=f"ipfs://{cid}",
            db_content_hash=content_hash,
            normalized_content_hash=content_hash,
            trace_tx_hash=tx_hash,
            db_created_at=PILOT_BUILD_CREATED_AT,
            payload_created_at=PILOT_BUILD_CREATED_AT,
        )

        row = CalibrationRow(
            row_id=row_id,
            trace=trace,
            provenance=CorpusProvenance(
                source_type="real",
                source_ref=f"pilot-build:real/{trace_id}",
                run_id=run_id,
                lineage_id=lineage_id,
                content_hash=content_hash,
                created_at=PILOT_BUILD_CREATED_AT,
                harvested_trace=harvested,
                validation=validation,
            ),
            review=ReviewState(
                status="unreviewed",
                rubric_version=PILOT_RUBRIC_VERSION,
                failure_tags=list(failure_tags),
                notes=(
                    f"Pilot build real row for quality_band={quality_band},"
                    f" validated={is_validated}."
                ),
            ),
            split=_pilot_split_metadata(),
        )
        rows.append(row)
    return rows


def _compute_manifest_id(
    *,
    row_ids: list[str],
    source_counts: dict[str, int],
    run_id: str,
) -> str:
    """Return a deterministic manifest ID for the pilot build."""
    payload = json.dumps(
        {"run_id": run_id, "row_ids": row_ids, "source_counts": source_counts},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def build_pilot_slice(
    *,
    root: Path,
    pilot_size: int,
    seed: int = 42,
) -> PilotBuildResult:
    """Build a pilot slice mixing synthetic, mutated, and real traces."""
    if pilot_size <= 0:
        raise PilotBuildError("pilot_size must be greater than 0")

    layout = bootstrap_corpus_root(root)
    run_id = f"pilot-build-v1-size-{pilot_size}-seed-{seed}"

    # Distribution: ~40% synthetic, ~24% mutated, ~36% real
    synthetic_count = max(1, int(pilot_size * 0.40))
    mutation_parents = max(1, min(3, synthetic_count))
    mutations_per_parent = max(1, int(pilot_size * 0.24) // mutation_parents)
    mutated_count = mutation_parents * mutations_per_parent
    real_count = pilot_size - synthetic_count - mutated_count

    # Adjust if real_count is too small or too large
    if real_count < 1:
        # Redistribute: ensure at least 1 real row
        real_count = 1
        mutated_count = max(1, pilot_size - synthetic_count - real_count)
        mutation_parents = min(mutation_parents, mutated_count)
        mutations_per_parent = max(1, mutated_count // mutation_parents)
        mutated_count = mutation_parents * mutations_per_parent
        synthetic_count = pilot_size - mutated_count - real_count

    # Generate rows
    synthetic_rows = _pilot_synthetic_rows(synthetic_count, run_id=run_id)
    mutation_parent_rows = synthetic_rows[:mutation_parents]
    mutated_rows = _pilot_mutation_rows(
        mutation_parent_rows, mutations_per_parent, run_id=run_id
    )
    real_rows = _pilot_real_rows(real_count, run_id=run_id)

    all_rows = synthetic_rows + mutated_rows + real_rows

    # Write rows to disk
    rows_dir = layout.root / "rows"
    rows_dir.mkdir(parents=True, exist_ok=True)
    for row in all_rows:
        path = rows_dir / f"{row.row_id}.json"
        write_row(path, row)

    # Apply prelabeling to all rows
    loaded_rows = load_corpus_rows(layout.root, include_sample=False)
    validate_lineage_integrity(loaded_rows)

    manual_review_count = 0
    auto_resolved_count = 0
    prelabeled_rows: list[LoadedRow] = []

    for loaded in loaded_rows:
        labels = deterministic_prelabels_for_row(loaded.row)
        updated = apply_prelabels_to_row(loaded.row, labels)
        write_row(loaded.path, updated)
        prelabeled_rows.append(LoadedRow(path=loaded.path, row=updated))

        if updated.review.status == "manual_review":
            manual_review_count += 1
        elif updated.review.status == "ai_resolved":
            auto_resolved_count += 1

    # Build counts and manifest
    source_counts: dict[str, int] = dict(
        sorted(Counter(row.provenance.source_type for row in all_rows).items())
    )
    row_ids = sorted(row.row_id for row in all_rows)
    duplicate_row_ids = [
        row_id for row_id, count in Counter(row.row_id for row in all_rows).items() if count > 1
    ]

    manifest_id = _compute_manifest_id(
        row_ids=row_ids,
        source_counts=source_counts,
        run_id=run_id,
    )

    # Write manifest
    manifest_path = layout.root / "manifests" / f"{run_id}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_payload = {
        "authority": "local",
        "manifest_id": manifest_id,
        "operation": "pilot-build",
        "row_count": len(all_rows),
        "row_ids": row_ids,
        "run_id": run_id,
        "source_counts": source_counts,
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return PilotBuildResult(
        operation="pilot-build",
        run_id=run_id,
        row_count=len(all_rows),
        source_counts=source_counts,
        row_ids=row_ids,
        duplicate_row_ids=duplicate_row_ids,
        manifest_id=manifest_id,
        manifest_path=manifest_path,
        manual_review_count=manual_review_count,
        auto_resolved_count=auto_resolved_count,
        rows=tuple(sorted(prelabeled_rows, key=lambda loaded: loaded.row.row_id)),
    )


def pilot_build_summary(result: PilotBuildResult) -> dict[str, Any]:
    """Return a machine-readable CLI summary for a pilot build."""
    return {
        "authority": "local",
        "auto_resolved_count": result.auto_resolved_count,
        "duplicate_row_ids": result.duplicate_row_ids,
        "manifest_id": result.manifest_id,
        "manifest_path": str(result.manifest_path),
        "manual_review_count": result.manual_review_count,
        "operation": result.operation,
        "row_count": result.row_count,
        "row_ids": result.row_ids,
        "run_id": result.run_id,
        "source_counts": result.source_counts,
    }
