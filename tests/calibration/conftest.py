"""Pytest fixtures for the calibration test package.

Without the autouse fixture below, any calibration test that resolves
``braintrust_project()`` would fall through to the production "Prism"
project name and pollute live Braintrust data. The override forces a
CI-only project so isolation does not depend on per-test discipline.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_braintrust_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRISM_BRAINTRUST_PROJECT", "Prism CI")
