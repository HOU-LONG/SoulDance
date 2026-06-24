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


def test_eval_scenario_model_accepts_retrieval_gold_labels():
    scenario = EvalScenario(
        id="budget",
        message="recommend sunscreen",
        session_id="eval_budget",
        expect=EvalExpectation(
            gold_product_ids=["p1", "p2"],
            gold_primary_ids=["p1"],
            expected_gate="recommend",
        ),
    )

    assert scenario.expect.gold_product_ids == ["p1", "p2"]
    assert scenario.expect.gold_primary_ids == ["p1"]
    assert scenario.expect.expected_gate == "recommend"


def test_eval_expectation_accepts_recommend_ablation_fields():
    expectation = EvalExpectation(
        price_min=100,
        expected_brands=["BrandA"],
        forbidden_brands=["BrandB"],
        expect_clarification=True,
        expect_product_ids_subset_of=["p1", "p2"],
    )

    assert expectation.price_min == 100
    assert expectation.expected_brands == ["BrandA"]
    assert expectation.forbidden_brands == ["BrandB"]
    assert expectation.expect_clarification is True
    assert expectation.expect_product_ids_subset_of == ["p1", "p2"]
