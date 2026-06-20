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
