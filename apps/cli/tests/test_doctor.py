from __future__ import annotations

import json
import subprocess

from typer.testing import CliRunner

import prism_cli.app as app_module
from prism_cli.app import app
from prism_cli.doctor import DoctorCheck, DoctorReport, run_circle_diagnostics

runner = CliRunner()


def test_circle_doctor_detects_base_sepolia_auth_required() -> None:
    def fake_run(cmd, capture_output, check, text, timeout):
        assert cmd[:2] == ["circle", "wallet"]
        if cmd[2] == "status":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    {
                        "data": {
                            "type": "agent",
                            "email": "dev@example.com",
                            "mainnet": {"tokenStatus": "VALID"},
                        }
                    }
                ),
                stderr="",
            )
        if cmd[2] == "list":
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout=json.dumps(
                    {
                        "error": {
                            "code": "AUTH_REQUIRED",
                            "message": "Run `circle wallet login dev@example.com --testnet`",
                        }
                    }
                ),
                stderr="",
            )
        raise AssertionError(cmd)

    checks = run_circle_diagnostics(timeout_seconds=1.0, run=fake_run)

    by_id = {check.id: check for check in checks}
    assert by_id["circle_cli"].status == "ok"
    assert by_id["circle_base_sepolia_login"].status == "fail"
    assert "--testnet" in by_id["circle_base_sepolia_login"].remediation


def test_circle_doctor_fails_when_base_sepolia_has_no_wallets() -> None:
    def fake_run(cmd, capture_output, check, text, timeout):
        if cmd[2] == "status":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    {
                        "data": {
                            "type": "agent",
                            "email": "dev@example.com",
                            "testnet": {"tokenStatus": "VALID"},
                        }
                    }
                ),
                stderr="",
            )
        if cmd[2] == "list":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({"data": {"wallets": []}}),
                stderr="",
            )
        raise AssertionError(cmd)

    checks = run_circle_diagnostics(timeout_seconds=1.0, run=fake_run)

    by_id = {check.id: check for check in checks}
    assert by_id["circle_base_sepolia_login"].status == "ok"
    assert by_id["circle_base_sepolia_wallet"].status == "fail"
    assert "circle wallet create" in by_id["circle_base_sepolia_wallet"].remediation


def test_doctor_command_outputs_json_and_exits_nonzero_on_fail(monkeypatch) -> None:
    async def fake_run_doctor(config, include_circle=True):
        assert include_circle is True
        return DoctorReport(
            overall_status="fail",
            checks=[
                DoctorCheck(
                    id="circle_base_sepolia_login",
                    label="Circle Base Sepolia login",
                    status="fail",
                    detail="Testnet auth required",
                    remediation="circle wallet login dev@example.com --testnet",
                )
            ],
        )

    monkeypatch.setattr(app_module, "run_doctor", fake_run_doctor)

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["overall_status"] == "fail"
    assert payload["checks"][0]["id"] == "circle_base_sepolia_login"
    assert "--testnet" in payload["checks"][0]["remediation"]
