from __future__ import annotations

import json

from backend.app.eval.long_session_models import validate_trace_line  # noqa: F401
from backend.app.eval.long_session_runner import (
    CONDITION_CONFIGS,
    LongSessionRunner,
    RunnerConfig,
)
from backend.app.eval.long_session_templates import ScriptTurn


def test_condition_configs_completeness():
    assert set(CONDITION_CONFIGS.keys()) == {"C0", "C1", "C2", "C3", "C4"}
    for cfg in CONDITION_CONFIGS.values():
        assert set(cfg.keys()) == {
            "disable_window",
            "disable_snapshot",
            "disable_recommendation",
            "disable_rank",
        }


def test_runner_fresh_setup_with_real_hashes(tmp_path):
    config = RunnerConfig(stage="dryrun", condition="C0", data_root=tmp_path, mode="fresh")
    runner = LongSessionRunner(config)
    runner._script = [ScriptTurn(phase="A", turn_type="retrieval", query="x", expected={})]
    runner._products = []
    runner._setup_trace_file_for_test()
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    assert trace_path.exists()
    meta = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert meta["_meta"] is True
    assert meta["script_version_hash"].startswith("sha256:")
