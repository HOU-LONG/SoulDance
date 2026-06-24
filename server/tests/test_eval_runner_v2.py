"""Phase 2 评测 DSL 扩展验证。

每种新断言至少 1 个正例 + 1 个反例：
- expected_brands / forbidden_brands
- price_min
- expect_clarification
- expect_no_match
- expect_order_status (单元层面：直接喂 mock events)
- expect_cart_quantity
- expect_error_kind
- expect_product_ids_subset_of
- forbidden_terms_in_explanation
- 占位符 ${var_name}
- IR 指标 compute_ranking_metrics
"""

from __future__ import annotations

from backend.app.eval.metrics import (
    compute_ranking_metrics,
    evaluate_events,
    evaluate_step,
)
from backend.app.eval.models import (
    EvalExpectation,
    EvalScenario,
    EvalStep,
)


def _product_event(product_id: str, brand: str = "BrandA", price: float = 99.0, name: str = "") -> dict:
    return {
        "type": "product_item",
        "product": {
            "product_id": product_id,
            "name": name or product_id,
            "brand": brand,
            "price": price,
            "description": "",
        },
    }


# ---------- expected_brands / forbidden_brands ----------


def test_expected_brands_positive():
    events = [_product_event("p1", brand="华为"), _product_event("p2", brand="小米")]
    expectation = EvalExpectation(expected_brands=["华为"])
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed, result.failures


def test_expected_brands_negative():
    events = [_product_event("p1", brand="小米")]
    expectation = EvalExpectation(expected_brands=["华为"])
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed
    assert any("expected brand" in failure for failure in result.failures)


def test_forbidden_brands_positive():
    events = [_product_event("p1", brand="华为")]
    expectation = EvalExpectation(forbidden_brands=["小米"])
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed


def test_forbidden_brands_negative():
    events = [_product_event("p1", brand="小米")]
    expectation = EvalExpectation(forbidden_brands=["小米"])
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed
    assert any("forbidden brand" in failure for failure in result.failures)


# ---------- price_min ----------


def test_price_min_positive():
    events = [_product_event("p1", price=200.0)]
    expectation = EvalExpectation(price_min=150.0)
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed


def test_price_min_negative():
    events = [_product_event("p1", price=50.0)]
    expectation = EvalExpectation(price_min=150.0)
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed
    assert any("below min" in failure for failure in result.failures)


# ---------- clarification ----------


def test_expect_clarification_positive():
    events = [{"type": "clarification_request", "question": "你想看防晒里的哪个方向？"}]
    expectation = EvalExpectation(expect_clarification=True)
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed


def test_expect_clarification_negative():
    events = [_product_event("p1")]
    expectation = EvalExpectation(expect_clarification=True)
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed


# ---------- no_match ----------


def test_expect_no_match_positive():
    events = [
        {"type": "text_delta", "delta": "我按「这些条件」做了硬过滤，当前商品库里没有完全满足的商品。"},
        {"type": "done"},
    ]
    expectation = EvalExpectation(expect_no_match=True)
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed, result.failures


def test_expect_no_match_negative_when_products_returned():
    events = [
        {"type": "text_delta", "delta": "没有完全满足的商品"},
        _product_event("p1"),
    ]
    expectation = EvalExpectation(expect_no_match=True)
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed
    assert any("product_item events still emitted" in failure for failure in result.failures)


# ---------- order_status ----------


def test_expect_order_status_positive():
    events = [{"type": "order_status", "status": "awaiting_confirmation", "order_id": "o1"}]
    expectation = EvalExpectation(expect_order_status="awaiting_confirmation")
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed


def test_expect_order_status_negative():
    events = [{"type": "order_status", "status": "address_required", "order_id": "o1"}]
    expectation = EvalExpectation(expect_order_status="completed")
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed


# ---------- cart_quantity ----------


def test_expect_cart_quantity_positive():
    events = [
        {
            "type": "cart_update",
            "items": [{"product_id": "p1", "quantity": 2}, {"product_id": "p2", "quantity": 1}],
        }
    ]
    expectation = EvalExpectation(expect_cart_quantity={"p1": 2, "p2": 1})
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed, result.failures


def test_expect_cart_quantity_negative():
    events = [{"type": "cart_update", "items": [{"product_id": "p1", "quantity": 1}]}]
    expectation = EvalExpectation(expect_cart_quantity={"p1": 5})
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed


# ---------- error_kind ----------


def test_expect_error_kind_llm_timeout_positive():
    events = [
        {"type": "text_delta", "delta": "我已经找到候选商品，但生成详细解释暂时超时了。"},
        {"type": "done"},
    ]
    expectation = EvalExpectation(expect_error_kind="llm_timeout")
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed, result.failures


def test_expect_error_kind_negative_when_no_marker():
    events = [{"type": "text_delta", "delta": "正常回复"}]
    expectation = EvalExpectation(expect_error_kind="llm_timeout")
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed


# ---------- product_ids_subset_of ----------


def test_product_subset_positive():
    events = [_product_event("p1"), _product_event("p2")]
    expectation = EvalExpectation(expect_product_ids_subset_of=["p1", "p2", "p3"])
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed


def test_product_subset_negative():
    events = [_product_event("p1"), _product_event("p99")]
    expectation = EvalExpectation(expect_product_ids_subset_of=["p1", "p2"])
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed


# ---------- forbidden_terms_in_explanation ----------


def test_forbidden_terms_in_explanation_positive():
    events = [{"type": "text_delta", "delta": "这款防晒霜清爽不油腻"}]
    expectation = EvalExpectation(forbidden_terms_in_explanation=["酒精"])
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert result.passed


def test_forbidden_terms_in_explanation_negative():
    events = [{"type": "text_delta", "delta": "这款防晒含酒精成分"}]
    expectation = EvalExpectation(forbidden_terms_in_explanation=["酒精"])
    result = evaluate_step(expectation, events, step_index=0, scenario_vars={})
    assert not result.passed


# ---------- 占位符 ----------


def test_placeholder_resolution_in_expected_focus():
    events = [_product_event("real_pid")]
    expectation = EvalExpectation(expected_focus_product="${first_product}")
    result = evaluate_step(
        expectation,
        events,
        step_index=0,
        scenario_vars={"first_product": "real_pid"},
    )
    assert result.passed, result.failures


def test_placeholder_resolution_in_subset_list():
    events = [_product_event("p1")]
    expectation = EvalExpectation(expect_product_ids_subset_of=["${pid_a}", "${pid_b}"])
    result = evaluate_step(
        expectation,
        events,
        step_index=0,
        scenario_vars={"pid_a": "p1", "pid_b": "p2"},
    )
    assert result.passed, result.failures


# ---------- 向后兼容 ----------


def test_legacy_scenario_auto_expands_to_single_step():
    scenario = EvalScenario(
        id="legacy",
        session_id="s",
        message="推荐防晒",
        expect=EvalExpectation(min_product_items=1),
    )
    assert len(scenario.steps) == 1
    assert scenario.steps[0].action == "user_message"
    assert scenario.steps[0].message == "推荐防晒"


def test_legacy_cart_action_scenario_maps_to_cart_step():
    scenario = EvalScenario(id="legacy_cart", session_id="s", message="x", type="cart_action")
    assert scenario.steps[0].action == "cart_action"


def test_legacy_order_flow_scenario_maps_to_order_step():
    scenario = EvalScenario(id="legacy_order", session_id="s", message="x", type="order_flow")
    assert scenario.steps[0].action == "order_action"


def test_evaluate_events_old_api_still_works():
    scenario = EvalScenario(
        id="legacy",
        session_id="s",
        message="推荐",
        expect=EvalExpectation(min_product_items=1),
    )
    events = [_product_event("p1"), {"type": "done"}]
    result = evaluate_events(scenario, events)
    assert result.passed
    assert result.product_ids == ["p1"]


# ---------- 多步组合 ----------


def test_multi_step_scenario_construction():
    scenario = EvalScenario(
        id="multi",
        session_id="s",
        steps=[
            EvalStep(message="推荐防晒", bind={"first_product": "product_ids[0]"}),
            EvalStep(
                message="第一款适合油皮吗",
                expect=EvalExpectation(expected_focus_product="${first_product}"),
            ),
        ],
    )
    assert len(scenario.steps) == 2
    assert scenario.steps[0].bind == {"first_product": "product_ids[0]"}


# ---------- IR 指标 ----------


def test_compute_ranking_metrics_perfect():
    predicted = ["p1", "p2", "p3", "p4"]
    expected = ["p1", "p2", "p3"]
    metrics = compute_ranking_metrics(predicted, expected, k_values=(3,))
    assert metrics["recall@3"] == 1.0
    assert metrics["ndcg@3"] == 1.0


def test_compute_ranking_metrics_partial():
    predicted = ["p1", "p99", "p3", "p4"]
    expected = ["p1", "p2", "p3"]
    metrics = compute_ranking_metrics(predicted, expected, k_values=(3,))
    assert metrics["recall@3"] == 2 / 3
    assert 0 < metrics["ndcg@3"] < 1


def test_compute_ranking_metrics_empty_expected_returns_empty():
    metrics = compute_ranking_metrics(["p1"], [], k_values=(5,))
    assert metrics == {}
