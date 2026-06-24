from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_long_session_eval.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
    )


def test_missing_mode_flags_fails():
    """两者都不传 → exit code != 0"""
    res = _run("--stage", "dryrun", "--condition", "C0")
    assert res.returncode != 0
    assert "reset-cache" in res.stderr.lower() or "resume" in res.stderr.lower()


def test_both_mode_flags_conflict():
    res = _run("--stage", "dryrun", "--condition", "C0", "--reset-cache", "--resume")
    assert res.returncode != 0
    assert "互斥" in res.stderr or "mutually exclusive" in res.stderr.lower()


def test_resume_without_existing_trace_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOPGUIDE_EVAL_DATA_ROOT", str(tmp_path))
    res = _run("--stage", "dryrun", "--condition", "C0", "--resume")
    assert res.returncode != 0


def test_report_mode_runs_without_condition(tmp_path, monkeypatch):
    """--report 模式不需要 --condition"""
    monkeypatch.setenv("SHOPGUIDE_EVAL_DATA_ROOT", str(tmp_path))
    (tmp_path / "dryrun").mkdir()
    res = _run("--stage", "dryrun", "--report")
    # 没有 trace 时 report 应给出友好提示而非崩溃
    assert "no trace" in res.stdout.lower() or "no trace" in res.stderr.lower() or res.returncode == 0
