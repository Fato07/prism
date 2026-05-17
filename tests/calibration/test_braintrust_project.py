from __future__ import annotations

from prism_calibration.braintrust_sync import BRAINTRUST_PROJECT, braintrust_project


def test_braintrust_project_defaults_to_prism(monkeypatch) -> None:
    monkeypatch.delenv("PRISM_BRAINTRUST_PROJECT", raising=False)

    assert braintrust_project() == BRAINTRUST_PROJECT


def test_braintrust_project_can_be_isolated_for_ci(monkeypatch) -> None:
    monkeypatch.setenv("PRISM_BRAINTRUST_PROJECT", "Prism CI")

    assert braintrust_project() == "Prism CI"
