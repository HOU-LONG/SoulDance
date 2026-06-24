"""Tests for session context compression data models and policy.

Task 1 scope: data models only.
"""
from __future__ import annotations

from backend.app.models import (
    CompressionPartDecision,
    LivingSummary,
    SessionCompressionState,
)


def test_compression_state_defaults_are_session_scoped() -> None:
    state = SessionCompressionState(user_id="u1", session_id="s1")
    assert state.user_id == "u1"
    assert state.session_id == "s1"
    assert state.living_summary.text == ""
    assert state.decisions == {}
    # model_context_limit must not bake in a production default; it is injected
    # from config at runtime (see Plan Task 2).
    assert state.model_context_limit == 0
    assert state.last_total_tokens is None
    assert state.watermark_level == "maintain"


def test_compression_state_json_roundtrip_preserves_decisions() -> None:
    state = SessionCompressionState(user_id="u1", session_id="s1")
    state.decisions["s1:1:tool:0"] = CompressionPartDecision(
        part_id="s1:1:tool:0",
        action="placeholder",
        replacement_text="[tool output omitted: s1:1:tool:0]",
        original_token_count=1200,
        compressed_token_count=12,
        created_turn=1,
    )
    state.living_summary = LivingSummary(
        text="user wants sub-2000 RMB earbuds",
        covered_part_ids=["s1:1:tool:0"],
        updated_turn=1,
        source_token_count=1200,
    )
    restored = SessionCompressionState.model_validate_json(state.model_dump_json())
    assert restored == state


def test_compression_part_decision_optional_token_counts() -> None:
    decision = CompressionPartDecision(
        part_id="s1:2:assistant:0",
        action="placeholder",
        replacement_text="[older assistant turn]",
    )
    assert decision.original_token_count is None
    assert decision.compressed_token_count is None
    assert decision.created_turn == 0


def test_living_summary_defaults_are_empty() -> None:
    summary = LivingSummary()
    assert summary.text == ""
    assert summary.covered_part_ids == []
    assert summary.updated_turn == 0
    assert summary.source_token_count == 0


def test_session_id_is_required() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SessionCompressionState()  # type: ignore[call-arg]
