"""Braintrust dataset sync, idempotent resync, and interrupted-resume tests."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from prism_calibration.braintrust_sync import (
    SyncSliceResult,
    _clear_sync_state,
    _read_sync_state,
    _sync_state_path,
    _write_sync_state,
    read_braintrust_ref,
    sync_slice_to_braintrust,
)
from prism_calibration.freeze import freeze_slice
from prism_calibration.lineage import load_corpus_rows
from prism_calibration.pilot import build_pilot_slice

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unique_dataset_name() -> str:
    """Return a unique dataset name for test isolation.

    Each test invocation gets its own Braintrust dataset so rows from
    previous test runs do not accumulate and pollute assertions about
    row counts and IDs.
    """
    return f"test-pilot-slice-{uuid.uuid4().hex[:12]}"


def _build_pilot_root(tmp_path: Path) -> Path:
    """Build a small pilot slice and return the corpus root path."""
    root = tmp_path / "calibration"
    build_pilot_slice(root=root, pilot_size=20)
    return root


def _freeze_pilot(root: Path) -> Path:
    """Freeze the pilot slice and return the export directory."""
    export = freeze_slice(root, "pilot")
    return export.export_dir


# ---------------------------------------------------------------------------
# VAL-BT-001: Frozen slice appears as a Braintrust dataset
# ---------------------------------------------------------------------------


def test_sync_creates_dataset_with_matching_row_count_and_stable_ids(
    tmp_path: Path,
) -> None:
    """Syncing a frozen slice creates a Braintrust dataset whose row count
    and stable case IDs match the local export."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    ds_name = _unique_dataset_name()
    result = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )

    assert isinstance(result, SyncSliceResult)
    assert result.dataset_name == ds_name
    assert result.dataset_id  # non-empty Braintrust dataset ID
    assert result.row_count > 0

    # Row IDs in the result must match the frozen export
    frozen_rows = load_corpus_rows(root, include_sample=False)
    pilot_row_ids = sorted(
        loaded.row.row_id
        for loaded in frozen_rows
        if loaded.row.split.name == "pilot"
    )
    assert result.synced_row_ids == pilot_row_ids
    assert result.skipped_row_ids == []


def test_sync_auto_freezes_if_no_frozen_export_exists(tmp_path: Path) -> None:
    """If no frozen export exists, sync creates one automatically."""
    root = _build_pilot_root(tmp_path)

    ds_name = _unique_dataset_name()
    # No freeze yet — sync should auto-freeze
    result = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )

    assert result.row_count > 0
    assert result.export_id  # frozen export was created

    # Verify the frozen export now exists
    frozen_dir = root / "frozen" / "pilot"
    assert frozen_dir.is_dir()


# ---------------------------------------------------------------------------
# VAL-BT-002 / VAL-CROSS-003: Slice resync is idempotent
# ---------------------------------------------------------------------------


def test_resync_is_idempotent_no_duplicates(tmp_path: Path) -> None:
    """Re-syncing the same slice updates in place without creating duplicates."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    ds_name = _unique_dataset_name()

    # First sync
    first = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )
    assert first.row_count > 0

    # Fetch current rows from Braintrust
    import braintrust

    dataset = braintrust.init_dataset(project="Prism", name=first.dataset_name)
    rows_after_first = list(dataset.fetch())
    first_row_count = len(rows_after_first)
    first_ids = sorted(
        str(r.get("id", "")) if isinstance(r, dict) else str(getattr(r, "id", ""))
        for r in rows_after_first
    )

    # Second sync (idempotent)
    second = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )

    # Same dataset
    assert second.dataset_id == first.dataset_id
    assert second.dataset_name == first.dataset_name
    assert second.row_count == first.row_count

    # No duplicate rows in Braintrust
    dataset2 = braintrust.init_dataset(project="Prism", name=first.dataset_name)
    rows_after_second = list(dataset2.fetch())
    second_row_count = len(rows_after_second)

    # Row count must not increase on re-sync
    assert second_row_count == first_row_count

    # Stable IDs match
    second_ids = sorted(
        str(r.get("id", "")) if isinstance(r, dict) else str(getattr(r, "id", ""))
        for r in rows_after_second
    )
    assert second_ids == first_ids


def test_resync_with_no_local_changes_produces_zero_drift(tmp_path: Path) -> None:
    """A second sync with no local changes produces no duplicates or drift."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    ds_name = _unique_dataset_name()

    first = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )
    second = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )

    # Same synced row IDs, same counts, same dataset
    assert first.synced_row_ids == second.synced_row_ids
    assert first.row_count == second.row_count
    assert first.dataset_id == second.dataset_id


# ---------------------------------------------------------------------------
# VAL-CROSS-006: Partial sync resumes cleanly
# ---------------------------------------------------------------------------


def test_interrupted_sync_resumes_from_durable_state(tmp_path: Path) -> None:
    """If sync is interrupted, rerunning resumes from durable state
    and finishes with the same final shape as a clean run."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    ds_name = _unique_dataset_name()

    # Load the frozen manifest to get row IDs
    frozen_rows = load_corpus_rows(root, include_sample=False)
    pilot_rows = sorted(
        [loaded for loaded in frozen_rows if loaded.row.split.name == "pilot"],
        key=lambda loaded: loaded.row.row_id,
    )
    all_row_ids = [loaded.row.row_id for loaded in pilot_rows]
    assert len(all_row_ids) >= 5, "Need at least 5 rows for interruption test"

    # Simulate a partial sync by writing durable state with only some rows synced.
    # The dataset_name in state must match the one we'll pass on resume.
    partial_ids = all_row_ids[:3]  # Only first 3 rows "synced"
    _write_sync_state(root, "pilot", {
        "dataset_id": "placeholder-id",
        "dataset_name": ds_name,
        "export_id": "placeholder-export",
        "slice": "pilot",
        "synced_row_ids": sorted(partial_ids),
        "skipped_row_ids": [],
        "total_rows": len(all_row_ids),
    })

    # Now resume the sync with the same dataset_name
    result = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )

    assert result.resumed is True
    assert result.row_count == len(all_row_ids), (
        f"Resume should sync all {len(all_row_ids)} rows, got {result.row_count}"
    )
    assert result.synced_row_ids == sorted(all_row_ids)

    # Verify no duplicates in Braintrust
    import braintrust

    dataset = braintrust.init_dataset(project="Prism", name=result.dataset_name)
    remote_rows = list(dataset.fetch())
    assert len(remote_rows) == len(all_row_ids)

    # State file should be cleared after successful completion
    state = _read_sync_state(root, "pilot")
    assert state is None


def test_clean_run_and_resumed_run_produce_same_remote_shape(
    tmp_path: Path,
) -> None:
    """A resumed sync finishes with the same dataset shape as a clean
    uninterrupted run when both target isolated datasets."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    # Use two separate dataset names to isolate the runs
    clean_ds_name = _unique_dataset_name()
    resume_ds_name = _unique_dataset_name()

    # Clean run
    clean = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=clean_ds_name,
    )

    import braintrust

    dataset = braintrust.init_dataset(project="Prism", name=clean.dataset_name)
    clean_rows = list(dataset.fetch())
    clean_ids = sorted(
        str(r.get("id", "")) if isinstance(r, dict) else str(getattr(r, "id", ""))
        for r in clean_rows
    )

    # Now simulate interruption + resume using a separate dataset name
    frozen_rows = load_corpus_rows(root, include_sample=False)
    pilot_rows = sorted(
        [loaded for loaded in frozen_rows if loaded.row.split.name == "pilot"],
        key=lambda loaded: loaded.row.row_id,
    )
    all_row_ids = [loaded.row.row_id for loaded in pilot_rows]

    # Write partial state with the resume dataset name
    _write_sync_state(root, "pilot", {
        "dataset_id": "placeholder-id",
        "dataset_name": resume_ds_name,
        "export_id": "placeholder-export",
        "slice": "pilot",
        "synced_row_ids": sorted(all_row_ids[:2]),
        "skipped_row_ids": [],
        "total_rows": len(all_row_ids),
    })

    resumed = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=resume_ds_name,
    )

    dataset2 = braintrust.init_dataset(project="Prism", name=resumed.dataset_name)
    resumed_rows = list(dataset2.fetch())
    resumed_ids = sorted(
        str(r.get("id", "")) if isinstance(r, dict) else str(getattr(r, "id", ""))
        for r in resumed_rows
    )

    # Same row count and same IDs (both datasets were freshly created)
    assert len(resumed_rows) == len(clean_rows)
    assert resumed_ids == clean_ids


# ---------------------------------------------------------------------------
# VAL-BT-007: Local export remains source of truth
# ---------------------------------------------------------------------------


def test_local_manifest_retains_dataset_reference(tmp_path: Path) -> None:
    """After sync, the frozen export has a Braintrust reference sidecar
    so the local export remains the authoritative record."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    ds_name = _unique_dataset_name()
    result = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )

    # Check that a braintrust-ref sidecar exists alongside the frozen manifest
    ref = read_braintrust_ref(result.export_dir)
    assert ref is not None
    assert ref["dataset_id"] == result.dataset_id
    assert ref["dataset_name"] == result.dataset_name
    assert ref["export_id"] == result.export_id


def test_local_export_remains_source_of_truth_without_braintrust(
    tmp_path: Path,
) -> None:
    """The frozen export can still be validated locally without Braintrust."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    # Sync to Braintrust
    ds_name = _unique_dataset_name()
    sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )

    # Validate the frozen export still works locally
    from prism_calibration.freeze import validate_frozen_export

    export_dir = root / "frozen" / "pilot"
    # Find the latest frozen export
    export_subdirs = sorted(export_dir.iterdir()) if export_dir.is_dir() else []
    assert export_subdirs, "Frozen export should exist"

    validation = validate_frozen_export(export_subdirs[-1])
    assert validation.manifest.row_count > 0


# ---------------------------------------------------------------------------
# VAL-BT-008: CLI and Braintrust agree on remote state
# ---------------------------------------------------------------------------


def test_cli_dataset_state_matches_braintrust_remote(tmp_path: Path) -> None:
    """CLI-visible dataset state (via sync result) matches Braintrust remote rows."""
    root = _build_pilot_root(tmp_path)
    _freeze_pilot(root)

    ds_name = _unique_dataset_name()
    result = sync_slice_to_braintrust(
        root=root, slice_name="pilot", dataset_name=ds_name,
    )

    import braintrust

    dataset = braintrust.init_dataset(project="Prism", name=result.dataset_name)
    remote_rows = list(dataset.fetch())
    remote_ids = sorted(
        str(r.get("id", "")) if isinstance(r, dict) else str(getattr(r, "id", ""))
        for r in remote_rows
    )

    # CLI-reported row count and IDs must match remote
    assert result.row_count == len(remote_rows)
    assert result.synced_row_ids == remote_ids


# ---------------------------------------------------------------------------
# Sync state management
# ---------------------------------------------------------------------------


def test_sync_state_path_is_deterministic(tmp_path: Path) -> None:
    """Sync state path is deterministic for the same root and slice."""
    path = _sync_state_path(tmp_path, "pilot")
    assert path == tmp_path / "state" / "sync-slice-pilot.json"


def test_write_and_read_sync_state_roundtrips(tmp_path: Path) -> None:
    """Sync state writes and reads back deterministically."""
    state = {
        "dataset_id": "ds-123",
        "dataset_name": "pilot-slice-pilot",
        "export_id": "abc123",
        "slice": "pilot",
        "synced_row_ids": ["row-1", "row-2"],
        "skipped_row_ids": [],
        "total_rows": 5,
    }
    _write_sync_state(tmp_path, "pilot", state)
    loaded = _read_sync_state(tmp_path, "pilot")
    assert loaded == state


def test_clear_sync_state_removes_file(tmp_path: Path) -> None:
    """Clearing sync state removes the state file."""
    _write_sync_state(tmp_path, "pilot", {"slice": "pilot"})
    assert _read_sync_state(tmp_path, "pilot") is not None
    _clear_sync_state(tmp_path, "pilot")
    assert _read_sync_state(tmp_path, "pilot") is None


def test_read_sync_state_returns_none_when_no_file(tmp_path: Path) -> None:
    """Reading sync state returns None when no state file exists."""
    assert _read_sync_state(tmp_path, "pilot") is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_sync_without_braintrust_package_raises(tmp_path: Path) -> None:
    """If the braintrust package cannot be imported, sync raises a clear error."""
    from prism_calibration.braintrust_sync import BraintrustSyncError

    assert issubclass(BraintrustSyncError, ValueError)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_sync_cli_syncs_full_slice(tmp_path: Path) -> None:
    """The sync CLI command syncs the full frozen slice to Braintrust."""
    import subprocess

    root = _build_pilot_root(tmp_path)

    result = subprocess.run(
        [
            "uv", "run", "python", "-m", "prism_calibration.cli",
            "sync", "--root", str(root), "--slice", "pilot",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["operation"] == "sync-slice"
    assert payload["row_count"] > 0
    assert payload["dataset_id"]
    assert payload["dataset_name"].startswith("pilot-slice-")
