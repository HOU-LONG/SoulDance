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
