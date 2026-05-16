from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner

from prism_cli import __version__
from prism_cli.app import app

runner = CliRunner()


def test_package_version_matches_metadata() -> None:
    assert __version__ == version("prism-cli")


def test_cli_version_option() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"prism-cli {__version__}" in result.output
