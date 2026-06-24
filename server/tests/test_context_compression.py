"""Tests for session context compression data models and policy.

Task 1 scope: data models.
Task 2 scope: watermark policy, stable part ids, config-sourced context limit.
"""
from __future__ import annotations

from dataclasses import dataclass

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


# ---------------------------------------------------------------------------
# Task 2: watermark policy + stable part ids + config-sourced context limit
# ---------------------------------------------------------------------------


@dataclass
class _Part:
    """Minimal stand-in for whatever the assembler will eventually pass in.

    The policy helpers should only depend on this duck-typed surface — keeping
    the contract narrow lets us swap the real part type later without rewriting
    tests.
    """

    part_id: str
    token_count: int
    turn_index: int
    is_recent: bool = False
    is_current_user_message: bool = False
    is_user_text: bool = False


def test_choose_watermark_level_returns_maintain_below_50_percent() -> None:
    from backend.app.context_compression import choose_watermark_level

    assert choose_watermark_level(total_tokens=60_000, limit=128_000) == "maintain"


def test_choose_watermark_level_returns_cheap_deterministic_between_50_and_70() -> None:
    from backend.app.context_compression import choose_watermark_level

    assert (
        choose_watermark_level(total_tokens=70_000, limit=128_000)
        == "cheap_deterministic"
    )


def test_choose_watermark_level_returns_structured_compaction_between_70_and_85() -> None:
    from backend.app.context_compression import choose_watermark_level

    assert (
        choose_watermark_level(total_tokens=95_000, limit=128_000)
        == "structured_compaction"
    )


def test_choose_watermark_level_returns_incremental_summary_between_85_and_95() -> None:
    from backend.app.context_compression import choose_watermark_level

    assert (
        choose_watermark_level(total_tokens=110_000, limit=128_000)
        == "incremental_summary"
    )


def test_choose_watermark_level_returns_emergency_fit_above_95_percent() -> None:
    from backend.app.context_compression import choose_watermark_level

    assert (
        choose_watermark_level(total_tokens=125_000, limit=128_000)
        == "emergency_fit"
    )


def test_choose_watermark_level_handles_zero_limit_safely() -> None:
    """A misconfigured limit must not raise ZeroDivisionError — it should
    surface as emergency_fit so the upstream caller fails loud, not silent.
    """
    from backend.app.context_compression import choose_watermark_level

    assert (
        choose_watermark_level(total_tokens=100, limit=0) == "emergency_fit"
    )


def test_stable_part_id_is_deterministic() -> None:
    from backend.app.context_compression import stable_part_id

    pid1 = stable_part_id(session_id="s1", turn_index=3, role="tool", ordinal=0)
    pid2 = stable_part_id(session_id="s1", turn_index=3, role="tool", ordinal=0)
    assert pid1 == pid2 == "s1:3:tool:0"


def test_stable_part_id_distinguishes_role_and_ordinal() -> None:
    from backend.app.context_compression import stable_part_id

    ids = {
        stable_part_id("s1", 1, "user", 0),
        stable_part_id("s1", 1, "user", 1),
        stable_part_id("s1", 1, "assistant", 0),
        stable_part_id("s1", 2, "user", 0),
    }
    assert len(ids) == 4


def test_is_protected_part_protects_current_user_message_regardless_of_size() -> None:
    from backend.app.context_compression import is_protected_part

    # A huge current user paste (e.g. a stack trace) must NEVER be marked
    # unprotected. Spec principle 5.
    big_user = _Part(
        part_id="s1:9:user:0",
        token_count=12_000,
        turn_index=9,
        is_current_user_message=True,
        is_user_text=True,
    )
    assert is_protected_part(big_user) is True


def test_is_protected_part_protects_recent_parts_even_when_large() -> None:
    from backend.app.context_compression import is_protected_part

    # The 8000-token figure is how the protected-window BUILDER decides which
    # parts are "recent". Once a part is marked recent, the policy must not
    # re-filter it for being large. Plan modification: avoids the `9000-token
    # recent message gets dropped` bug from earlier review.
    big_recent = _Part(
        part_id="s1:8:assistant:0",
        token_count=9_000,
        turn_index=8,
        is_recent=True,
    )
    assert is_protected_part(big_recent) is True


def test_is_protected_part_does_not_protect_old_non_user_parts() -> None:
    from backend.app.context_compression import is_protected_part

    old_tool = _Part(
        part_id="s1:1:tool:0",
        token_count=500,
        turn_index=1,
        is_recent=False,
        is_current_user_message=False,
    )
    assert is_protected_part(old_tool) is False


def test_apply_or_reuse_decision_creates_new_decision_first_time() -> None:
    from backend.app.context_compression import apply_or_reuse_decision

    state = SessionCompressionState(user_id="u1", session_id="s1")
    part = _Part(part_id="s1:1:tool:0", token_count=1_200, turn_index=1)

    text = apply_or_reuse_decision(
        state,
        part,
        lambda p: f"[tool output omitted: {p.part_id}]",
    )

    assert text == "[tool output omitted: s1:1:tool:0]"
    assert "s1:1:tool:0" in state.decisions
    decision = state.decisions["s1:1:tool:0"]
    assert decision.action == "placeholder"
    assert decision.original_token_count == 1_200
    assert decision.created_turn == 1


def test_apply_or_reuse_decision_returns_existing_byte_for_byte() -> None:
    """Spec principle 7: once a part_id has a decision, replays must produce
    the same placeholder bytes — otherwise prompt caches invalidate.
    """
    from backend.app.context_compression import apply_or_reuse_decision

    state = SessionCompressionState(user_id="u1", session_id="s1")
    part = _Part(part_id="s1:1:tool:0", token_count=1_200, turn_index=1)

    first = apply_or_reuse_decision(
        state, part, lambda p: f"[v1 omitted: {p.part_id}]"
    )
    # Even if the factory changes on the next turn (e.g. policy refactor),
    # the stored decision must win.
    second = apply_or_reuse_decision(
        state, part, lambda p: f"[v2 different: {p.part_id}]"
    )
    assert first == second == "[v1 omitted: s1:1:tool:0]"
    assert len(state.decisions) == 1


def test_settings_expose_llm_context_limit_from_env(monkeypatch) -> None:
    """Plan Task 2 Step 3: model_context_limit must come from config, not from
    the Pydantic model default.
    """
    monkeypatch.setenv("LLM_CONTEXT_LIMIT", "64000")
    from backend.app.config import get_settings

    # get_settings() is lru_cached; clear so this test sees the env we just set.
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_context_limit == 64_000
    finally:
        get_settings.cache_clear()


def test_settings_default_llm_context_limit_is_128k(monkeypatch) -> None:
    monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
    from backend.app.config import get_settings

    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_context_limit == 128_000
    finally:
        get_settings.cache_clear()
