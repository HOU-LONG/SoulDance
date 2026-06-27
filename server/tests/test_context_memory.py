"""Tests for context memory architecture (Phase 1-3)."""
from __future__ import annotations

import asyncio

import pytest

from backend.app.agent import ShopGuideAgent
from backend.app.data_loader import load_products
from backend.app.llm_client import FakeLLMClient
from backend.app.models import ChatRequest, SessionContext


class FakeRetriever:
    def search(self, query, top_k=20):
        return []


def test_dialog_turns_collected_after_turn():
    """Verify that after handle_message completes, dialog_turns has both
    user and assistant messages."""
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    session_id = "test_dt"

    asyncio.run(
        agent.handle_message(
            "anonymous",
            ChatRequest(type="user_message", session_id=session_id, message="推荐精华"),
        )
    )
    ctx = agent.sessions.get("anonymous", session_id)
    assert len(ctx.dialog_turns) >= 2, f"Expected >=2 turns, got {len(ctx.dialog_turns)}"
    assert ctx.dialog_turns[0]["role"] == "user"
    assert ctx.dialog_turns[-1]["role"] == "assistant"


def test_collect_assistant_reply_appends_text():
    """Verify _collect_assistant_reply collects text_delta events and
    appends assistant message, and enforces capacity."""
    ctx = SessionContext(session_id="test_collect")
    agent = ShopGuideAgent([], FakeLLMClient(), FakeRetriever())

    events = [
        {"type": "text_delta", "text": "Hello "},
        {"type": "text_delta", "text": "World!"},
        {"type": "done", "message_id": "abc"},
    ]
    agent._collect_assistant_reply(ctx, events)
    assert len(ctx.dialog_turns) == 1
    assert ctx.dialog_turns[0]["role"] == "assistant"
    assert ctx.dialog_turns[0]["content"] == "Hello World!"


def test_collect_assistant_reply_placeholder_on_empty():
    """Verify that when there are no text_delta events, a placeholder
    is appended to keep the role sequence valid."""
    ctx = SessionContext(session_id="test_placeholder")
    agent = ShopGuideAgent([], FakeLLMClient(), FakeRetriever())

    events = [{"type": "done", "message_id": "abc"}]
    agent._collect_assistant_reply(ctx, events)
    assert len(ctx.dialog_turns) == 1
    assert ctx.dialog_turns[0]["role"] == "assistant"
    assert ctx.dialog_turns[0]["content"] == "[回复]"


def test_collect_assistant_reply_truncates_long_text():
    """Verify that assistant replies longer than 2000 chars are truncated."""
    ctx = SessionContext(session_id="test_truncate")
    agent = ShopGuideAgent([], FakeLLMClient(), FakeRetriever())

    long_text = "X" * 3000
    events = [{"type": "text_delta", "text": long_text}]
    agent._collect_assistant_reply(ctx, events)
    assert len(ctx.dialog_turns) == 1
    assert ctx.dialog_turns[0]["role"] == "assistant"
    assert len(ctx.dialog_turns[0]["content"]) == 2000


def test_collect_assistant_reply_capacity_enforced():
    """Verify that when dialog_turns exceeds 100 messages, the oldest
    are trimmed to keep only the last 100."""
    ctx = SessionContext(session_id="test_cap")
    agent = ShopGuideAgent([], FakeLLMClient(), FakeRetriever())

    # Pre-fill with 99 messages
    for i in range(99):
        ctx.dialog_turns.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"})

    # Append one more via _collect_assistant_reply
    events = [{"type": "text_delta", "text": "msg99_assistant"}]
    agent._collect_assistant_reply(ctx, events)

    # Should be at 100 messages now (99 + 1 new)
    assert len(ctx.dialog_turns) == 100

    # Append another one — should trim to keep 100
    events2 = [{"type": "text_delta", "text": "msg100_assistant"}]
    agent._collect_assistant_reply(ctx, events2)
    assert len(ctx.dialog_turns) == 100
    # Oldest should have been trimmed
    assert ctx.dialog_turns[0]["content"] == "msg1"
    assert ctx.dialog_turns[-1]["content"] == "msg100_assistant"


def test_dialog_turns_user_message_appended_in_stream():
    """Verify that user message is appended to dialog_turns at the entry
    of stream_message."""
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    session_id = "test_user_msg"

    asyncio.run(
        agent.handle_message(
            "anonymous",
            ChatRequest(type="user_message", session_id=session_id, message="推荐防晒"),
        )
    )
    ctx = agent.sessions.get("anonymous", session_id)
    user_turns = [t for t in ctx.dialog_turns if t["role"] == "user"]
    assert len(user_turns) >= 1
    assert user_turns[0]["content"] == "推荐防晒"


# ── Phase 2: LivingSummary + backward compat ──────────────────────────────────


def test_phase2_summary_not_triggered_below_threshold():
    ctx = SessionContext(session_id="test_no_summary")
    for i in range(10):
        ctx.dialog_turns.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"})
    assert len(ctx.dialog_turns) < 16


def test_phase2_old_state_json_backward_compat():
    old_data = {"session_id": "old_session", "schema_version": 1}
    ctx = SessionContext.model_validate(old_data)
    assert ctx.compression_state.living_summary.text == ""
    assert ctx.dialog_turns == []


# ── Phase 3: domain tracking + entity params ──────────────────────────────────


def test_phase3_domain_switch_clears_soft_prefs():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    session_id = "test_ds"

    asyncio.run(agent.handle_message(
        "anonymous", ChatRequest(type="user_message", session_id=session_id, message="推荐一款精华")))
    ctx = agent.sessions.get("anonymous", session_id)
    assert ctx.state.constraint_state.current_domain == "美妆护肤"

    asyncio.run(agent.handle_message(
        "anonymous", ChatRequest(type="user_message", session_id=session_id, message="推荐一款小米手机")))
    ctx = agent.sessions.get("anonymous", session_id)
    assert ctx.state.constraint_state.current_domain == "数码电子"
    # Soft prefs should be cleared on domain switch (via _reset_shopping_task)
    assert not ctx.state.constraint_state.soft, f"Expected empty soft prefs, got {ctx.state.constraint_state.soft}"


def test_phase3_entity_params_populated():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    session_id = "test_ep"

    asyncio.run(agent.handle_message(
        "anonymous", ChatRequest(type="user_message", session_id=session_id, message="推荐精华预算500以内")))
    ctx = agent.sessions.get("anonymous", session_id)
    assert len(ctx.entity_params) >= 1, f"Expected cached params, got {ctx.entity_params}"
    first_pid = list(ctx.entity_params.keys())[0]
    assert "price" in ctx.entity_params[first_pid]
    assert "brand" in ctx.entity_params[first_pid]


def test_phase3_entity_params_order_tracks_insertion():
    ctx = SessionContext(session_id="test_order")
    for i in range(5):
        pid = f"p_{i:04d}"
        ctx.entity_params[pid] = {"price": i}
        ctx.entity_params_order.append(pid)
    assert ctx.entity_params_order == ["p_0000", "p_0001", "p_0002", "p_0003", "p_0004"]
