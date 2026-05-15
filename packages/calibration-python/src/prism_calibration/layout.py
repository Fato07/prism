"""Filesystem layout helpers for the local calibration corpus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CORPUS_ROOT = Path("data/calibration")
SAMPLE_DIR_NAME = "sample"
SAMPLE_SUBDIR_NAMES = ("rows",)
PRIVATE_DIR_NAMES = ("rows", "manifests", "frozen", "quarantine", "state")


@dataclass(frozen=True)
class CorpusLayout:
    """Resolved local corpus paths rooted at ``data/calibration`` by default."""

    root: Path

    @property
    def sample_dir(self) -> Path:
        """Return the publishable sample fixture directory."""
        return self.root / SAMPLE_DIR_NAME

    @property
    def private_dirs(self) -> tuple[Path, ...]:
        """Return private/gated directories that must remain gitignored."""
        return tuple(self.root / name for name in PRIVATE_DIR_NAMES)

    @property
    def sample_dirs(self) -> tuple[Path, ...]:
        """Return publishable sample subdirectories."""
        return tuple(self.sample_dir / name for name in SAMPLE_SUBDIR_NAMES)

    def missing_paths(self) -> tuple[Path, ...]:
        """Return required layout paths that do not currently exist."""
        required = (self.root, self.sample_dir, *self.sample_dirs, *self.private_dirs)
        return tuple(path for path in required if not path.exists())


def resolve_root(root: str | Path | None) -> Path:
    """Resolve a user-provided corpus root or the default local root."""
    return Path(root) if root is not None else DEFAULT_CORPUS_ROOT


def bootstrap_corpus_root(root: str | Path | None = None) -> CorpusLayout:
    """Create the local corpus root with publishable and gated subtrees."""
    layout = CorpusLayout(root=resolve_root(root))
    layout.sample_dir.mkdir(parents=True, exist_ok=True)
    for directory in layout.sample_dirs:
        directory.mkdir(parents=True, exist_ok=True)
    for directory in layout.private_dirs:
        directory.mkdir(parents=True, exist_ok=True)
    return layout


def layout_payload(layout: CorpusLayout, *, seed: int | None = None) -> dict[str, Any]:
    """Return a machine-readable layout summary for CLI output."""
    payload: dict[str, Any] = {
        "authority": "local",
        "private_dirs": [str(path) for path in layout.private_dirs],
        "root": str(layout.root),
        "sample_dir": str(layout.sample_dir),
        "sample_dirs": [str(path) for path in layout.sample_dirs],
        "status": "ready",
    }
    if seed is not None:
        payload["seed"] = seed
    return payload
