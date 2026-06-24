from __future__ import annotations

import json
import pytest

from backend.app.eval.long_session_models import (
    TraceMeta, TraceSchemaError, TurnTrace, validate_trace_line,
)


def _valid_trace_dict() -> dict:
    return {
        "condition": "C2",
        "session_id": "eval_dryrun_c2_2026-06-24",
        "turn_index": 47,
        "phase": "A",
        "turn_type": "retrieval",
        "adversarial_subtype": None,
        "query": "推荐防晒",
        "expected": {"expected_intent": "recommend_product"},
        "pipeline": ["planner", "retrieval"],
        "tool_calls": [{"name": "retrieval", "ms": 230}],
        "branch_flags": {"memory_hit": None, "fallback": None, "clarify": False},
        "prompt_tokens": 4321,
        "completion_tokens": 187,
        "first_chunk_ms": 820,
        "total_ms": 2310,
        "context_payload_bytes": 8742,
        "context_payload_tokens": 2180,
        "context_events_count": 47,
        "focus_history_len": 47,
        "focus_product_id": "p_beauty_006",
        "hard_constraints": {"category": "美妆护肤"},
        "state_drift": None,
        "degradation": None,
        "would_hit_b1": True,
        "effective_hit_b1": False,
        "would_hit_b2": True,
        "effective_hit_b2": False,
        "cache_stats_at_turn": {"b1_size": 23, "b2_size": 31},
        "rule_score": {"ndcg5": 0.83},
        "judge_score": None,
        "answer_text": "好的，给你推荐一款",
        "retrieved_top_k": ["p_beauty_006"],
        "script_version_hash": "sha256:" + "a" * 64,
        "product_list_hash": "sha256:" + "b" * 64,
        "condition_config_hash": "sha256:" + "c" * 64,
    }


def test_valid_trace_passes_schema():
    validate_trace_line(_valid_trace_dict())


def test_missing_required_key_fails():
    d = _valid_trace_dict()
    del d["turn_index"]
    with pytest.raises(TraceSchemaError):
        validate_trace_line(d)


def test_invalid_hash_format_fails():
    d = _valid_trace_dict()
    d["script_version_hash"] = "not-a-hash"
    with pytest.raises(TraceSchemaError):
        validate_trace_line(d)


def test_nullable_fields_accept_null():
    d = _valid_trace_dict()
    for k in ("adversarial_subtype", "focus_product_id", "state_drift", "degradation", "judge_score"):
        d[k] = None
    validate_trace_line(d)


def test_negative_token_count_fails():
    d = _valid_trace_dict()
    d["prompt_tokens"] = -1
    with pytest.raises(TraceSchemaError):
        validate_trace_line(d)


def test_turn_trace_pydantic_model_roundtrip():
    d = _valid_trace_dict()
    trace = TurnTrace(**d)
    assert trace.condition == "C2"
    dumped = trace.model_dump(mode="json")
    validate_trace_line(dumped)


def test_trace_meta_pydantic_model():
    meta = TraceMeta(
        condition="C2",
        script_version_hash="sha256:" + "a" * 64,
        product_list_hash="sha256:" + "b" * 64,
        condition_config_hash="sha256:" + "c" * 64,
        cache_namespace="data/eval/long_session_2026-06-24/dryrun/cache_c2/",
        started_at="2026-06-24T14:00:00+08:00",
        ark_model="ep-xxx",
        spec_version="2026-06-24-v1",
    )
    assert meta.condition == "C2"
