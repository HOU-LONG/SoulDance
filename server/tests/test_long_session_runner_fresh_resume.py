from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.eval.long_session_runner import (
    HashMismatchError,
    LongSessionRunner,
    MetaMissingError,
    RunnerConfig,
)
from backend.app.eval.long_session_templates import ScriptTurn


def _mk_config(tmp_path: Path, mode: str = "fresh") -> RunnerConfig:
    return RunnerConfig(
        stage="dryrun",
        condition="C0",
        data_root=tmp_path,
        mode=mode,
    )


def test_fresh_mode_creates_trace_with_meta(tmp_path):
    config = _mk_config(tmp_path, mode="fresh")
    runner = LongSessionRunner(config)
    runner._compute_hashes_static = lambda: ("sha256:" + "a"*64, "sha256:" + "b"*64, "sha256:" + "c"*64)
    runner._setup_trace_file_for_test()
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    assert trace_path.exists()
    first_line = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert first_line["_meta"] is True
    assert first_line["condition"] == "C0"


def test_fresh_mode_backs_up_existing_trace(tmp_path):
    config = _mk_config(tmp_path, mode="fresh")
    runner = LongSessionRunner(config)
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("OLD CONTENT\n", encoding="utf-8")
    runner._setup_trace_file_for_test()
    bak_files = list(trace_path.parent.glob("trace_C0.jsonl.*.bak"))
    assert len(bak_files) == 1


def test_resume_mode_requires_existing_trace(tmp_path):
    config = _mk_config(tmp_path, mode="resume")
    runner = LongSessionRunner(config)
    with pytest.raises(MetaMissingError):
        runner._setup_trace_file_for_test()


def test_resume_mode_rejects_hash_mismatch(tmp_path):
    config = _mk_config(tmp_path, mode="resume")
    runner = LongSessionRunner(config)
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    old_meta = {
        "_meta": True,
        "condition": "C0",
        "script_version_hash": "sha256:" + "0" * 64,  # 不匹配
        "product_list_hash": "sha256:" + "b" * 64,
        "condition_config_hash": "sha256:" + "c" * 64,
        "cache_namespace": str(tmp_path),
        "started_at": "2026-06-24T14:00:00+08:00",
        "ark_model": "ep-xxx",
        "spec_version": "2026-06-24-v1",
    }
    trace_path.write_text(json.dumps(old_meta) + "\n", encoding="utf-8")
    runner._compute_hashes_static = lambda: ("sha256:" + "a" * 64, "sha256:" + "b" * 64, "sha256:" + "c" * 64)
    with pytest.raises(HashMismatchError):
        runner._setup_trace_file_for_test()


def test_resume_returns_next_turn_index(tmp_path):
    config = _mk_config(tmp_path, mode="resume")
    runner = LongSessionRunner(config)
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"_meta": True, "condition": "C0", "script_version_hash": "sha256:" + "a" * 64,
            "product_list_hash": "sha256:" + "b" * 64, "condition_config_hash": "sha256:" + "c" * 64,
            "cache_namespace": str(tmp_path), "started_at": "x", "ark_model": "y", "spec_version": "z"}
    rows = [meta] + [{"turn_index": i, "condition": "C0"} for i in range(50)]
    trace_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    runner._compute_hashes_static = lambda: ("sha256:" + "a" * 64, "sha256:" + "b" * 64, "sha256:" + "c" * 64)
    runner._setup_trace_file_for_test()
    assert runner._should_resume_from() == 50


def test_invalid_trace_line_schema_fails_write(tmp_path):
    """写入不合法 trace 必须报错并不落盘。"""
    config = _mk_config(tmp_path, mode="fresh")
    runner = LongSessionRunner(config)
    runner._compute_hashes_static = lambda: ("sha256:" + "a" * 64, "sha256:" + "b" * 64, "sha256:" + "c" * 64)
    runner._setup_trace_file_for_test()
    with pytest.raises(Exception):  # TraceSchemaError
        runner._write_turn({"condition": "C0", "bad_field": True})  # 缺 required keys


def test_cache_namespace_is_stage_isolated(tmp_path):
    config_dryrun = _mk_config(tmp_path, mode="fresh")
    runner_d = LongSessionRunner(config_dryrun)
    config_pilot = RunnerConfig(stage="pilot", condition="C0", data_root=tmp_path, mode="fresh")
    runner_p = LongSessionRunner(config_pilot)
    assert runner_d.cache_namespace != runner_p.cache_namespace
    assert "dryrun" in str(runner_d.cache_namespace)
    assert "pilot" in str(runner_p.cache_namespace)
