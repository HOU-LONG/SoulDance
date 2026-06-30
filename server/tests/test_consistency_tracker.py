# server/tests/test_consistency_tracker.py
from __future__ import annotations
from server.backend.app.models import SessionContext, ConsistencyState, ClaimRecord, FactContext, FactRecord
from server.backend.app.consistency_tracker import ConsistencyTracker, ConsistencyResult


def _mk_ctx(denied=None, confirmed=None) -> SessionContext:
    ctx = SessionContext(session_id="test")
    ctx.state.consistency = ConsistencyState(
        denied_product_queries=denied or [],
        confirmed_product_id=confirmed,
    )
    return ctx


def _mk_fact_ctx() -> FactContext:
    r = FactRecord(product_id="P1", title="小米 14 Ultra", brand="小米", price=5999.0,
                   category="手机", sub_category="智能机")
    return FactContext(
        product_index={"P1": r},
        brand_index={"小米": ["P1"]},
    )


def test_record_denial():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    tracker.record_denial(ctx, "小米 17 Max", turn=3)
    assert "小米 17 Max" in ctx.state.consistency.denied_product_queries
    assert ctx.state.consistency.claims[0].claim_type == "not_exists"


def test_record_claim():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    tracker.record_claim(ctx, "P1", "recommendation", "主推小米 14 Ultra ¥5999", turn=2)
    assert ctx.state.consistency.claims[0].product_id == "P1"


def test_set_confirmed_product():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    tracker.set_confirmed_product(ctx, "P1")
    assert ctx.state.consistency.confirmed_product_id == "P1"


def test_check_focus_drift_detected():
    """用户已确认关注 P1，新推荐不含 P1 → 漂移。"""
    ctx = _mk_ctx(confirmed="P1")
    tracker = ConsistencyTracker()
    result = tracker.check_before_output(ctx, ["P2", "P3"], _mk_fact_ctx())
    assert not result.is_consistent
    assert result.focus_drift_detected


def test_check_focus_no_drift():
    ctx = _mk_ctx(confirmed="P1")
    tracker = ConsistencyTracker()
    result = tracker.check_before_output(ctx, ["P1", "P2"], _mk_fact_ctx())
    assert result.is_consistent


def test_check_empty_context():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    result = tracker.check_before_output(ctx, ["P1"], _mk_fact_ctx())
    assert result.is_consistent


def test_get_denied_queries():
    ctx = _mk_ctx(denied=["查询A", "查询B"])
    tracker = ConsistencyTracker()
    assert set(tracker.get_denied_queries(ctx)) == {"查询A", "查询B"}


def test_get_denied_queries_empty():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    assert tracker.get_denied_queries(ctx) == []
