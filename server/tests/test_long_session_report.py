from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.eval.long_session_report import (
    aggregate_csvs,
    render_plots,
    write_summary_markdown,
)


def _seed_trace(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _make_row(condition: str, turn_index: int, ttype: str = "retrieval", **extra) -> dict:
    base = {
        "condition": condition, "session_id": f"s_{condition}", "turn_index": turn_index,
        "phase": "A", "turn_type": ttype, "adversarial_subtype": None, "query": "q",
        "expected": {}, "pipeline": [], "tool_calls": [], "branch_flags": {},
        "prompt_tokens": 1000, "completion_tokens": 100, "first_chunk_ms": 200, "total_ms": 800,
        "context_payload_bytes": 5000, "context_payload_tokens": 1200,
        "context_events_count": turn_index, "focus_history_len": turn_index,
        "focus_product_id": None, "hard_constraints": {}, "state_drift": None,
        "degradation": None,
        "would_hit_b1": False, "effective_hit_b1": False,
        "would_hit_b2": False, "effective_hit_b2": False,
        "cache_stats_at_turn": {}, "rule_score": {"ndcg5": 0.8, "recall5": 1.0},
        "judge_score": None, "answer_text": "...", "retrieved_top_k": ["p1"],
        "script_version_hash": "sha256:" + "a"*64,
        "product_list_hash": "sha256:" + "b"*64,
        "condition_config_hash": "sha256:" + "c"*64,
    }
    base.update(extra)
    return base


def test_aggregate_csvs_outputs_retrieval_file(tmp_path):
    stage = tmp_path / "dryrun"
    meta = {"_meta": True, "condition": "C0", "script_version_hash": "sha256:" + "a"*64,
            "product_list_hash": "sha256:" + "b"*64, "condition_config_hash": "sha256:" + "c"*64,
            "cache_namespace": "x", "started_at": "x", "ark_model": "y", "spec_version": "z"}
    _seed_trace(stage / "trace_C0.jsonl", [meta, _make_row("C0", 0), _make_row("C0", 1)])
    aggregate_csvs(stage)
    csv_path = stage / "retrieval_C0.csv"
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "ndcg5" in content
    assert "0.8" in content


def test_render_plots_creates_pngs(tmp_path):
    stage = tmp_path / "dryrun"
    meta = {"_meta": True, "condition": "C0", "script_version_hash": "sha256:" + "a"*64,
            "product_list_hash": "sha256:" + "b"*64, "condition_config_hash": "sha256:" + "c"*64,
            "cache_namespace": "x", "started_at": "x", "ark_model": "y", "spec_version": "z"}
    for c in ["C0", "C1", "C2", "C3", "C4"]:
        _seed_trace(stage / f"trace_{c}.jsonl", [{**meta, "condition": c}, _make_row(c, 0), _make_row(c, 1)])
    plots_root = tmp_path / "plots"
    render_plots(stage, plots_root=plots_root)
    assert (plots_root / "retrieval_quality_by_turn.png").exists()
    assert (plots_root / "token_usage_curve.png").exists()
    assert (plots_root / "latency_p50_p90_p99.png").exists()


def test_write_summary_markdown_dryrun_contains_judge_disagreement(tmp_path):
    stage = tmp_path / "dryrun"
    meta = {"_meta": True, "condition": "C0", "script_version_hash": "sha256:" + "a"*64,
            "product_list_hash": "sha256:" + "b"*64, "condition_config_hash": "sha256:" + "c"*64,
            "cache_namespace": "x", "started_at": "x", "ark_model": "y", "spec_version": "z"}
    judge = {"raw": [{"hit": 1}, {"hit": 1}, {"hit": 1}], "mean": 4.0, "disagreement": 0.0, "call_count": 3}
    _seed_trace(stage / "trace_C0.jsonl", [meta, _make_row("C0", 0, judge_score=judge, turn_type="comparison")])
    summary = write_summary_markdown(stage)
    text = summary.read_text(encoding="utf-8")
    assert "DRYRUN_SUMMARY" in summary.name
    assert "disagreement" in text.lower() or "分歧" in text
    assert "C0" in text
