from __future__ import annotations

import pytest

from backend.app.eval.long_session_runner import (
    LongSessionRunner,
    _compute_rule_score,
)
from backend.app.eval.long_session_templates import ScriptTurn


def test_rule_score_retrieval_perfect_hit():
    turn = ScriptTurn(
        phase="A",
        turn_type="retrieval",
        query="推荐防晒霜",
        expected={"ideal_top": ["p_beauty_006"], "forbidden": []},
    )
    score = _compute_rule_score(turn, answer_text="...", retrieved_top_k=["p_beauty_006", "p_x", "p_y"], product_map={})
    assert score["recall5"] == 1.0
    assert score["ndcg5"] > 0.9


def test_rule_score_retrieval_forbidden_hit():
    turn = ScriptTurn(
        phase="A",
        turn_type="retrieval",
        query="推荐",
        expected={"ideal_top": ["p1"], "forbidden": ["p_bad"]},
    )
    score = _compute_rule_score(turn, answer_text="...", retrieved_top_k=["p_bad", "p1"], product_map={})
    assert score["forbidden_hit"] is True


def test_rule_score_followup_factual_price_match():
    from backend.app.models import Product
    product = Product(
        product_id="p1",
        title="测试",
        brand="X",
        category="美妆护肤",
        sub_category="",
        price=199.0,
        marketing_description="",
        image_path="",
    )
    turn = ScriptTurn(
        phase="A",
        turn_type="followup_factual",
        query="价格多少？",
        expected={"subject_product_id": "p1", "expected_intent": "product_followup"},
    )
    score = _compute_rule_score(
        turn,
        answer_text="价格是 199 元",
        retrieved_top_k=["p1"],
        product_map={"p1": product},
    )
    assert score["fact_match"] is True
