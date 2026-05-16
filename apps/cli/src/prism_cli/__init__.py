"""Prism command-line client."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("prism-cli")
except PackageNotFoundError:  # pragma: no cover - source tree without package metadata
    __version__ = "0.1.0"
