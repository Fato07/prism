from __future__ import annotations

from typer.testing import CliRunner

from prism_cli.app import app

runner = CliRunner()


def test_markets_command_is_exposed_in_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "markets" in result.output
    assert "market" in result.output


def test_market_resolve_command_is_exposed_in_help() -> None:
    result = runner.invoke(app, ["market", "--help"])

    assert result.exit_code == 0
    assert "resolve" in result.output
