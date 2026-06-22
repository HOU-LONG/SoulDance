from backend.app.eval.models import EvalExpectation, EvalScenario


def test_eval_scenario_model_accepts_core_fields():
    scenario = EvalScenario(
        id="budget",
        message="推荐100以内防晒",
        session_id="eval_budget",
        expect=EvalExpectation(min_product_items=1, price_max=100),
    )

    assert scenario.id == "budget"
    assert scenario.expect.price_max == 100
