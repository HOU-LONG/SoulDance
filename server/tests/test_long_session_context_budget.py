from __future__ import annotations

from backend.app.agent import ShopGuideAgent


def test_payload_within_budget_returns_unchanged():
    agent = ShopGuideAgent.__new__(ShopGuideAgent)  # bypass __init__
    payload = {"recent_context": {"recent_user_turns": [{"user_message": "你好"}]}}
    result, degradation = ShopGuideAgent._maybe_force_trim_context(agent, payload, budget=25000)
    assert degradation is None
    assert result == payload


def test_payload_over_budget_gets_trimmed_with_label():
    agent = ShopGuideAgent.__new__(ShopGuideAgent)
    # 造一个超大 payload
    big_turns = [{"user_message": "x" * 200, "assistant_intent": "recommend_product"} for _ in range(500)]
    payload = {"recent_context": {"recent_user_turns": big_turns, "recent_recommendation_sets": [], "last_events": []}}
    result, degradation = ShopGuideAgent._maybe_force_trim_context(agent, payload, budget=1000)
    assert degradation == "context_overflow_forced_trim"
    # 截断后 recent_user_turns 必须更短
    assert len(result["recent_context"]["recent_user_turns"]) < 500


def test_trim_keeps_most_recent_turns():
    agent = ShopGuideAgent.__new__(ShopGuideAgent)
    turns = [{"user_message": "x" * 200, "turn_index": i} for i in range(500)]
    payload = {"recent_context": {"recent_user_turns": turns, "recent_recommendation_sets": [], "last_events": []}}
    result, _ = ShopGuideAgent._maybe_force_trim_context(agent, payload, budget=1000)
    kept = result["recent_context"]["recent_user_turns"]
    # 保留的应该是最近的（turn_index 较大的）
    assert kept[-1]["turn_index"] == 499
