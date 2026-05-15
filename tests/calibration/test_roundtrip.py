"""Round-trip validation tests for frozen calibration exports."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from test_freeze import prepare_pilot_root, run_cli


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_frozen_export_validates_from_clean_path_without_braintrust(tmp_path: Path) -> None:
    """A copied frozen export reloads locally with matching IDs, counts, and hashes."""
    root = tmp_path / "calibration"
    prepare_pilot_root(root)
    freeze = run_cli("freeze", "--root", str(root), "--slice", "pilot")
    assert freeze.returncode == 0, freeze.stderr
    freeze_payload = json.loads(freeze.stdout)

    clean_export = tmp_path / "clean" / "pilot-export"
    shutil.copytree(Path(freeze_payload["export_path"]), clean_export)

    validation = run_cli("validate", "--frozen", str(clean_export))

    assert validation.returncode == 0, validation.stderr
    validation_payload = json.loads(validation.stdout)
    assert validation_payload["status"] == "valid"
    assert validation_payload["export_id"] == freeze_payload["export_id"]
    assert validation_payload["row_count"] == freeze_payload["row_count"]
    assert validation_payload["row_ids"] == freeze_payload["row_ids"]
    assert validation_payload["row_hashes"] == freeze_payload["row_hashes"]
    assert validation_payload["manifest_hash"] == hashlib.sha256(
        (clean_export / "manifest.json").read_bytes()
    ).hexdigest()

    validation_from_manifest = run_cli("validate", "--frozen", str(clean_export / "manifest.json"))
    assert validation_from_manifest.returncode == 0, validation_from_manifest.stderr
    manifest_payload = json.loads(validation_from_manifest.stdout)
    assert manifest_payload["export_id"] == freeze_payload["export_id"]
    assert manifest_payload["row_ids"] == freeze_payload["row_ids"]


def test_frozen_validation_rejects_tampered_row_payload(tmp_path: Path) -> None:
    """Frozen validation fails if a row no longer matches its manifest hash."""
    root = tmp_path / "calibration"
    prepare_pilot_root(root)
    freeze = run_cli("freeze", "--root", str(root), "--slice", "pilot")
    assert freeze.returncode == 0, freeze.stderr
    freeze_payload = json.loads(freeze.stdout)

    clean_export = tmp_path / "clean" / "tampered-export"
    shutil.copytree(Path(freeze_payload["export_path"]), clean_export)
    manifest = load_json(clean_export / "manifest.json")
    row_path = clean_export / manifest["rows"][0]["path"]
    row = load_json(row_path)
    row["trace"]["rationale"] = "Tampered after freeze."
    row_path.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validation = run_cli("validate", "--frozen", str(clean_export))

    assert validation.returncode != 0
    assert "row hash mismatch" in validation.stderr
