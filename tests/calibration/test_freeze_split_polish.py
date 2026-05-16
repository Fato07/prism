"""Tests for the freeze/split polish feature: single-load efficiency and named constants."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from prism_calibration.models import SplitName
from prism_calibration.splits import (
    ASSIGNED_AT_SENTINEL,
    SPLIT_THRESHOLD_DEV,
    SPLIT_THRESHOLD_HOLDOUT,
    SPLIT_THRESHOLD_PILOT,
    split_for_lineage,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI with Braintrust env unset."""
    env = os.environ.copy()
    env.pop("BRAINTRUST_API_KEY", None)
    env.pop("BRAINTRUST_ORG_NAME", None)
    return subprocess.run(
        [sys.executable, "-m", "prism_calibration.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def lineage_for_split(target: SplitName, *, seed: int = 42) -> str:
    """Return a deterministic lineage ID that maps to the requested split."""
    for index in range(1_000):
        lineage_id = f"lineage-{target}-{index}"
        if split_for_lineage(lineage_id, seed=seed) == target:
            return lineage_id
    raise AssertionError(f"Could not find lineage for split {target}")


def corpus_row(
    row_id: str,
    *,
    lineage_id: str,
    source_type: str = "synthetic",
    parent_row_id: str | None = None,
    mutation_type: str | None = None,
) -> dict[str, Any]:
    """Return a minimal schema-valid corpus row for freeze/split polish tests."""
    timestamp = "2026-05-15T12:00:00Z"
    provenance: dict[str, Any] = {
        "source_type": source_type,
        "source_ref": f"tests/generated/{row_id}.json",
        "run_id": "polish-test-run",
        "lineage_id": lineage_id,
        "content_hash": (row_id.encode().hex() * 64)[:64].ljust(64, "0"),
        "created_at": timestamp,
    }
    if parent_row_id is not None:
        provenance["parent_row_id"] = parent_row_id
    if mutation_type is not None:
        provenance["mutation_type"] = mutation_type

    return {
        "schema_version": "1.0",
        "row_id": row_id,
        "trace": {
            "trace_id": f"trace-{row_id}",
            "agent_id": 4140,
            "market_id": f"polish-market-{lineage_id}",
            "market_question": "Will named constants and single-load freeze work?",
            "thesis": [
                {
                    "proposition": f"{row_id} uses exposed split constants.",
                    "supporting_evidence_ids": [0],
                    "risk_factors": ["Constants may not be exposed."],
                }
            ],
            "evidence": [
                {
                    "source": "polish-test",
                    "claim": f"{row_id} has stable split inputs.",
                    "confidence": 0.85,
                    "timestamp": timestamp,
                }
            ],
            "raw_probability": 0.59,
            "volatility_adjustment": 0.02,
            "final_probability": 0.61,
            "action": "HOLD",
            "size_usdc": 0.0,
            "price_limit": 0.61,
            "rationale": f"{row_id} is a polish fixture.",
            "model_family": "anthropic-claude",
            "model_name": "claude-opus-4-7",
            "created_at": timestamp,
        },
        "provenance": provenance,
        "review": {
            "status": "unreviewed",
            "rubric_version": "prism-calibration-v1",
            "failure_tags": [],
        },
        "split": {
            "name": "pilot",
            "policy": "pre-freeze fixture",
            "seed": 0,
            "assigned_at": timestamp,
        },
    }


def write_rows(root: Path, rows: list[dict[str, Any]]) -> None:
    """Write private corpus rows under a local root."""
    row_dir = root / "rows"
    row_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        (row_dir / f"{row['row_id']}.json").write_text(
            json.dumps(row, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def prepare_pilot_root(root: Path) -> None:
    """Build a local root containing pilot rows and an excluded dev row."""
    initial = run_cli("build", "--root", str(root), "--seed", "42")
    assert initial.returncode == 0, initial.stderr

    pilot_lineage = lineage_for_split("pilot")
    dev_lineage = lineage_for_split("dev")
    write_rows(
        root,
        [
            corpus_row("pilot-parent", lineage_id=pilot_lineage),
            corpus_row(
                "pilot-mutated",
                lineage_id=pilot_lineage,
                source_type="mutated",
                parent_row_id="pilot-parent",
                mutation_type="weakened-evidence",
            ),
            corpus_row("dev-row", lineage_id=dev_lineage),
        ],
    )

    build = run_cli("build", "--root", str(root), "--seed", "42")
    assert build.returncode == 0, build.stderr


# --- Named-constant tests ---


class TestSplitThresholdConstants:
    """Verify split thresholds are exposed as named module-level constants."""

    def test_pilot_threshold_is_50(self) -> None:
        """The pilot split threshold constant equals 50."""
        assert SPLIT_THRESHOLD_PILOT == 50

    def test_dev_threshold_is_75(self) -> None:
        """The dev split threshold constant equals 75."""
        assert SPLIT_THRESHOLD_DEV == 75

    def test_holdout_threshold_is_90(self) -> None:
        """The holdout split threshold constant equals 90."""
        assert SPLIT_THRESHOLD_HOLDOUT == 90

    def test_thresholds_are_strictly_ascending(self) -> None:
        """Threshold constants are strictly increasing: pilot < dev < holdout."""
        assert SPLIT_THRESHOLD_PILOT < SPLIT_THRESHOLD_DEV < SPLIT_THRESHOLD_HOLDOUT

    def test_thresholds_are_within_bucket_range(self) -> None:
        """All thresholds are within the [0, 100] bucket range."""
        for threshold in (SPLIT_THRESHOLD_PILOT, SPLIT_THRESHOLD_DEV, SPLIT_THRESHOLD_HOLDOUT):
            assert 0 <= threshold <= 100

    def test_assigned_at_sentinel_is_epoch(self) -> None:
        """The ASSIGNED_AT sentinel is the Unix epoch datetime."""
        assert ASSIGNED_AT_SENTINEL.year == 1970
        assert ASSIGNED_AT_SENTINEL.month == 1
        assert ASSIGNED_AT_SENTINEL.day == 1
        assert ASSIGNED_AT_SENTINEL.hour == 0
        assert ASSIGNED_AT_SENTINEL.minute == 0
        assert ASSIGNED_AT_SENTINEL.second == 0

    def test_split_for_lineage_uses_threshold_constants(self) -> None:
        """split_for_lineage produces splits consistent with the threshold constants."""
        # Pilot: bucket < SPLIT_THRESHOLD_PILOT
        pilot_lineage = lineage_for_split("pilot")
        import hashlib
        digest = hashlib.sha256(f"42:{pilot_lineage}".encode()).hexdigest()
        bucket = int(digest[:8], 16) % 100
        assert bucket < SPLIT_THRESHOLD_PILOT

        # Dev: SPLIT_THRESHOLD_PILOT <= bucket < SPLIT_THRESHOLD_DEV
        dev_lineage = lineage_for_split("dev")
        digest = hashlib.sha256(f"42:{dev_lineage}".encode()).hexdigest()
        bucket = int(digest[:8], 16) % 100
        assert SPLIT_THRESHOLD_PILOT <= bucket < SPLIT_THRESHOLD_DEV

        # Holdout: SPLIT_THRESHOLD_DEV <= bucket < SPLIT_THRESHOLD_HOLDOUT
        holdout_lineage = lineage_for_split("holdout")
        digest = hashlib.sha256(f"42:{holdout_lineage}".encode()).hexdigest()
        bucket = int(digest[:8], 16) % 100
        assert SPLIT_THRESHOLD_DEV <= bucket < SPLIT_THRESHOLD_HOLDOUT

        # Canary: bucket >= SPLIT_THRESHOLD_HOLDOUT
        canary_lineage = lineage_for_split("canary")
        digest = hashlib.sha256(f"42:{canary_lineage}".encode()).hexdigest()
        bucket = int(digest[:8], 16) % 100
        assert bucket >= SPLIT_THRESHOLD_HOLDOUT


class TestFreezeSingleLoad:
    """Verify freeze loads corpus rows once and preserves export identity."""

    def test_freeze_preserves_identity_on_unchanged_slice(self, tmp_path: Path) -> None:
        """Freezing an unchanged slice twice produces identical export identity."""
        root = tmp_path / "calibration"
        prepare_pilot_root(root)

        first = run_cli("freeze", "--root", str(root), "--slice", "pilot")
        second = run_cli("freeze", "--root", str(root), "--slice", "pilot")

        assert first.returncode == 0, first.stderr
        assert second.returncode == 0, second.stderr
        first_payload = json.loads(first.stdout)
        second_payload = json.loads(second.stdout)
        assert second_payload["export_id"] == first_payload["export_id"]
        assert second_payload["export_path"] == first_payload["export_path"]
        assert second_payload["row_hashes"] == first_payload["row_hashes"]

        manifest_path = Path(first_payload["manifest_path"])
        first_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        second_hash = hashlib.sha256(
            Path(second_payload["manifest_path"]).read_bytes()
        ).hexdigest()
        assert second_hash == first_hash

    def test_freeze_dev_slice_excludes_sample_rows(self, tmp_path: Path) -> None:
        """Freezing a non-sample slice does not include sample rows."""
        root = tmp_path / "calibration"
        initial = run_cli("build", "--root", str(root), "--seed", "42")
        assert initial.returncode == 0, initial.stderr

        dev_lineage = lineage_for_split("dev")
        write_rows(root, [corpus_row("dev-only", lineage_id=dev_lineage)])
        build = run_cli("build", "--root", str(root), "--seed", "42")
        assert build.returncode == 0, build.stderr

        result = run_cli("freeze", "--root", str(root), "--slice", "dev")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["slice"] == "dev"
        assert payload["row_count"] >= 1
        # sample-row-001 from bootstrap should never appear in a dev freeze
        assert "sample-row-001" not in payload["row_ids"]
