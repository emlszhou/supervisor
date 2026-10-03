import json
import subprocess
import sys

from supervisor.cli import main


def test_installed_cli_reports_scaffold_without_claiming_runtime_ready():
    result = subprocess.run(
        [sys.executable, "-m", "supervisor", "doctor"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["stage"] == "scaffold"
    assert report["development_prerequisites_ready"] is True
    assert report["workflow_implemented"] is False
    assert report["agent_execution_verified"] is False
    assert report["sandbox_verified"] is False


def test_doctor_fails_when_required_git_is_missing(monkeypatch, capsys):
    monkeypatch.setattr("supervisor.cli.shutil.which", lambda _command: None)
    assert main(["doctor"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["development_prerequisites_ready"] is False


def test_execution_command_is_explicitly_unavailable():
    result = subprocess.run(
        [sys.executable, "-m", "supervisor", "run"], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "invalid choice" in result.stderr


def test_installed_version_command():
    result = subprocess.run(
        [sys.executable, "-m", "supervisor", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "0.1.0.dev0" in result.stdout
