"""Tests for dialog_turns collection and capacity enforcement (Task 1.2)."""
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
