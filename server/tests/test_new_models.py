# server/tests/test_new_models.py
from __future__ import annotations
from server.backend.app.models import (
    FactRecord, FactContext, ClaimRecord, ConsistencyState,
    SessionRecovery, SessionState, SessionContext,
)


def test_fact_record():
    r = FactRecord(product_id="P1", title="商品1", brand="小米", price=100.0,
                   category="手机", sub_category="智能机", key_specs=["快"])
    assert r.product_id == "P1"
    assert r.price == 100.0


def test_fact_context():
    r1 = FactRecord(product_id="P1", title="A", brand="小米", price=100,
                    category="手机", sub_category="智能机")
    r2 = FactRecord(product_id="P2", title="B", brand="华为", price=200,
                    category="手机", sub_category="智能机")
    ctx = FactContext(
        prompt_block="事实块",
        product_index={"P1": r1, "P2": r2},
        brand_index={"小米": ["P1"], "华为": ["P2"]},
        denied_queries=["不存在商品"],
    )
    assert ctx.product_index["P1"].brand == "小米"
    assert ctx.brand_index["小米"] == ["P1"]
    assert "不存在商品" in ctx.denied_queries


def test_fact_context_defaults():
    ctx = FactContext()
    assert ctx.prompt_block == ""
    assert ctx.product_index == {}
    assert ctx.denied_queries == []


def test_consistency_state():
    cs = ConsistencyState(
        claims=[ClaimRecord(turn=1, product_id="P1", claim_type="price", claim_value="¥100")],
        confirmed_product_id="P1",
        denied_product_queries=["不存在查询"],
    )
    assert cs.confirmed_product_id == "P1"
    assert len(cs.denied_product_queries) == 1
    assert cs.claims[0].claim_type == "price"


def test_consistency_state_defaults():
    cs = ConsistencyState()
    assert cs.claims == []
    assert cs.confirmed_product_id is None


def test_session_recovery():
    sr = SessionRecovery(user_message_restored=True, products_cached=False,
                         hint="你的消息已收到")
    assert sr.user_message_restored is True
    assert sr.hint is not None


def test_session_state_has_consistency_field():
    """SessionState 默认应有 consistency 和 checkpoint_stage 字段。"""
    state = SessionState()
    assert state.consistency == ConsistencyState()
    assert state.checkpoint_stage == ""


def test_session_context_imports_unchanged():
    """旧模型不受影响。"""
    from server.backend.app.models import (
        ConstraintEdits, CartOperation, QueryIntent, SemanticFrame,
        ShoppingIntentIR, RetrievalPlan,
    )
    from server.backend.app.tool_plan import ToolPlan  # ToolPlan 在 tool_plan.py，不在 models.py
    assert ConstraintEdits is not None
    assert SemanticFrame is not None
    assert ToolPlan is not None
