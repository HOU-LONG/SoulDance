from __future__ import annotations

from backend.app.models import HardConstraints, RetrievalPlan, SessionContext
from backend.app.semantic_layer import semantic_context_payload


def _ctx_with_focus_and_plan() -> SessionContext:
    ctx = SessionContext(session_id="t")
    ctx.focus_product_id = "p_beauty_006"
    ctx.last_plan = RetrievalPlan(
        intent="recommend_product",
        retrieval_mode="vector",
        retrieval_query="防晒霜",
        category="美妆护肤",
        hard_constraints=HardConstraints(),
    )
    ctx.last_recommendations = [{"product_id": "p_beauty_006", "title": "测试商品"}]
    return ctx


def test_payload_default_keeps_snapshot():
    ctx = _ctx_with_focus_and_plan()
    payload = semantic_context_payload(ctx)
    assert payload["focus_product_id"] == "p_beauty_006"
    assert payload["focus_product"] is not None
    assert payload["last_plan"] is not None
    assert payload["current_task"] is not None


def test_payload_disable_snapshot_nulls_four_fields():
    ctx = _ctx_with_focus_and_plan()
    payload = semantic_context_payload(ctx, disable_snapshot=True)
    assert payload["focus_product"] is None
    assert payload["last_plan"] is None
    assert payload["pending_clarification"] is None
    assert payload["current_task"] is None
    # focus_product_id 自身仍保留（状态机不动）
    assert payload["focus_product_id"] == "p_beauty_006"
    # recent_context 仍正常（由 A1 控制）
    assert "recent_context" in payload


def test_payload_disable_snapshot_does_not_touch_recent_context():
    ctx = _ctx_with_focus_and_plan()
    payload = semantic_context_payload(ctx, disable_snapshot=True)
    # recent_context 仍有完整结构
    assert isinstance(payload["recent_context"], dict)
    assert "recent_user_turns" in payload["recent_context"]
