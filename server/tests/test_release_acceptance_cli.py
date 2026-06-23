from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "server" / "scripts" / "run_release_acceptance.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_list_checks_contains_release_acceptance_matrix() -> None:
    result = run_cli("--list-checks")

    assert result.returncode == 0, result.stderr
    checks = json.loads(result.stdout)
    assert [check["name"] for check in checks] == [
        "backend-tests",
        "eval-runner",
        "eval-full",
        "android-build",
        "script-syntax",
        "host-health-smoke",
    ]

    backend = checks[0]
    assert backend["cwd"] == "server"
    assert "pytest" in " ".join(backend["command"])

    eval_runner = checks[1]
    assert "--fake-llm" in eval_runner["command"], "eval-runner should use fake LLM for CI portability"

    eval_full = checks[2]
    assert eval_full["kind"] == "eval-full"
    assert "--min-pass-rate" in eval_full["command"]
    assert "0.80" in eval_full["command"]

    android = checks[3]
    assert android["cwd"] == "client"
    assert android["env"]["JAVA_HOME"].endswith("android-studio/jbr")
    assert android["env"]["ANDROID_HOME"].endswith("android-sdk")


def test_dry_run_can_select_checks_without_executing_them() -> None:
    result = run_cli(
        "--dry-run",
        "--check",
        "eval-runner",
        "--check",
        "android-build",
    )

    assert result.returncode == 0, result.stderr
    checks = json.loads(result.stdout)
    assert [check["name"] for check in checks] == ["eval-runner", "android-build"]
    assert checks[0]["cwd"] == "server"
    assert checks[1]["cwd"] == "client"


def test_unknown_check_reports_valid_names() -> None:
    result = run_cli("--check", "not-a-check", "--dry-run")

    assert result.returncode == 2
    assert "Unknown check: not-a-check" in result.stderr
    assert "backend-tests" in result.stderr
    assert "host-health-smoke" in result.stderr


def test_script_syntax_check_runs_bash_n_for_each_script() -> None:
    result = run_cli("--list-checks")

    assert result.returncode == 0, result.stderr
    checks = json.loads(result.stdout)
    script_check = checks[4]
    assert script_check["name"] == "script-syntax"
    assert script_check["command"][:2] == ["bash", "-c"]
    assert "for script in" in script_check["command"][2]
    assert "server/scripts/start_backend.sh" in script_check["command"][2]
