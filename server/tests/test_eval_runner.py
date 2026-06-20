from backend.app.eval.metrics import evaluate_events
from backend.app.eval.models import EvalExpectation, EvalScenario


def test_evaluate_events_detects_missing_product_items():
    scenario = EvalScenario(
        id="missing",
        message="推荐防晒",
        session_id="eval_missing",
        expect=EvalExpectation(min_product_items=1, event_types=["ack", "done"]),
    )

    result = evaluate_events(scenario, [{"type": "ack"}, {"type": "done"}])

    assert not result.passed
    assert any("product_item" in failure for failure in result.failures)


def test_evaluate_events_detects_forbidden_term_in_product_name():
    scenario = EvalScenario(
        id="exclude_alcohol",
        message="推荐敏感肌可以用的护肤品，不要含酒精",
        session_id="eval_exclude_alcohol",
        expect=EvalExpectation(min_product_items=1, forbid_terms=["酒精", "alcohol"]),
    )

    result = evaluate_events(
        scenario,
        [
            {"type": "product_item", "product": {"product_id": "p1", "name": "含酒精爽肤水", "description": "清爽"}},
        ],
    )

    assert not result.passed
    assert any("forbidden term" in failure for failure in result.failures)


def test_evaluate_events_passes_when_forbidden_term_absent():
    scenario = EvalScenario(
        id="exclude_alcohol",
        message="推荐敏感肌可以用的护肤品，不要含酒精",
        session_id="eval_exclude_alcohol",
        expect=EvalExpectation(min_product_items=1, forbid_terms=["酒精", "alcohol"]),
    )

    result = evaluate_events(
        scenario,
        [
            {"type": "product_item", "product": {"product_id": "p1", "name": "温和保湿乳", "description": "无添加"}},
        ],
    )

    assert result.passed


def test_evaluate_events_detects_price_over_max():
    scenario = EvalScenario(
        id="budget_under_100",
        message="推荐100元以内的防晒霜",
        session_id="eval_budget_under_100",
        expect=EvalExpectation(min_product_items=1, price_max=100),
    )

    result = evaluate_events(
        scenario,
        [
            {"type": "product_item", "product": {"product_id": "p1", "name": "贵价防晒", "price": 150}},
        ],
    )

    assert not result.passed
    assert any("exceeds max" in failure for failure in result.failures)


def test_evaluate_events_passes_when_price_under_max():
    scenario = EvalScenario(
        id="budget_under_100",
        message="推荐100元以内的防晒霜",
        session_id="eval_budget_under_100",
        expect=EvalExpectation(min_product_items=1, price_max=100),
    )

    result = evaluate_events(
        scenario,
        [
            {"type": "product_item", "product": {"product_id": "p1", "name": "平价防晒", "price": 80}},
        ],
    )

    assert result.passed


def test_evaluate_events_detects_missing_cart_success():
    scenario = EvalScenario(
        id="cart_add_ui_action",
        message="cart_action:add_first_product",
        session_id="eval_cart_add",
        type="cart_action",
        expect=EvalExpectation(require_cart_success=True, event_types=["ack", "cart_update", "done"]),
    )

    result = evaluate_events(
        scenario,
        [{"type": "ack"}, {"type": "done"}],
    )

    assert not result.passed
    assert any("cart_update" in failure for failure in result.failures)


def test_evaluate_events_detects_cart_failure():
    scenario = EvalScenario(
        id="cart_add_ui_action",
        message="cart_action:add_first_product",
        session_id="eval_cart_add",
        type="cart_action",
        expect=EvalExpectation(require_cart_success=True, event_types=["ack", "cart_update", "done"]),
    )

    result = evaluate_events(
        scenario,
        [{"type": "ack"}, {"type": "cart_update", "success": False}, {"type": "done"}],
    )

    assert not result.passed
    assert any("cart_update event reported failure" in failure for failure in result.failures)


def test_evaluate_events_passes_when_cart_success():
    scenario = EvalScenario(
        id="cart_add_ui_action",
        message="cart_action:add_first_product",
        session_id="eval_cart_add",
        type="cart_action",
        expect=EvalExpectation(require_cart_success=True, event_types=["ack", "cart_update", "done"]),
    )

    result = evaluate_events(
        scenario,
        [{"type": "ack"}, {"type": "cart_update", "success": True}, {"type": "done"}],
    )

    assert result.passed


def test_evaluate_events_detects_missing_order_completed():
    scenario = EvalScenario(
        id="order_confirm_flow",
        message="order_flow:first_product",
        session_id="eval_order_flow",
        type="order_flow",
        expect=EvalExpectation(require_order_completed=True),
    )

    result = evaluate_events(
        scenario,
        [{"type": "ack"}, {"type": "done"}],
    )

    assert not result.passed
    assert any("order_completed" in failure for failure in result.failures)


def test_evaluate_events_detects_order_incomplete():
    scenario = EvalScenario(
        id="order_confirm_flow",
        message="order_flow:first_product",
        session_id="eval_order_flow",
        type="order_flow",
        expect=EvalExpectation(require_order_completed=True),
    )

    result = evaluate_events(
        scenario,
        [{"type": "ack"}, {"type": "order_completed", "completed": False}, {"type": "done"}],
    )

    assert not result.passed
    assert any("order_completed event reported incomplete" in failure for failure in result.failures)


def test_evaluate_events_passes_when_order_completed():
    scenario = EvalScenario(
        id="order_confirm_flow",
        message="order_flow:first_product",
        session_id="eval_order_flow",
        type="order_flow",
        expect=EvalExpectation(require_order_completed=True),
    )

    result = evaluate_events(
        scenario,
        [{"type": "ack"}, {"type": "order_completed", "completed": True}, {"type": "done"}],
    )

    assert result.passed
