from __future__ import annotations

from backend.app.models import ContextEvent, SessionContext
from backend.app.semantic_layer import semantic_context_payload, _recent_context_summary


def _build_session_with_n_events(n: int) -> SessionContext:
    ctx = SessionContext(session_id="t")
    for i in range(n):
        ctx.state.context_events.append(
            ContextEvent(
                event_id=f"evt_{i}",
                turn_index=i,
                user_message=f"u{i}",
                assistant_intent="recommend_product",
                result_type="recommendation_set" if i % 2 == 0 else "answer",
            )
        )
    return ctx


def test_recent_context_summary_default_truncates_to_3():
    ctx = _build_session_with_n_events(20)
    summary = _recent_context_summary(ctx)
    assert len(summary["recent_user_turns"]) == 3
    assert len(summary["recent_recommendation_sets"]) == 3
    assert len(summary["last_events"]) == 3


def test_recent_context_summary_disable_window_returns_full():
    ctx = _build_session_with_n_events(20)
    summary = _recent_context_summary(ctx, disable_window=True)
    assert len(summary["recent_user_turns"]) == 20
    assert len(summary["recent_recommendation_sets"]) == 10  # 偶数 turn
    assert len(summary["last_events"]) == 20


def test_semantic_context_payload_propagates_disable_window():
    ctx = _build_session_with_n_events(20)
    payload_default = semantic_context_payload(ctx)
    payload_disabled = semantic_context_payload(ctx, disable_window=True)
    assert len(payload_default["recent_context"]["recent_user_turns"]) == 3
    assert len(payload_disabled["recent_context"]["recent_user_turns"]) == 20
