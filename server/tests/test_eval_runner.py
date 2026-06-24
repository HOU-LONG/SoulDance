from pathlib import Path

from backend.app.eval.runner import load_scenarios, run_scenarios
from backend.app.main import create_app


def test_eval_runner_executes_minimal_websocket_scenario(tmp_path: Path):
    scenario_path = tmp_path / "scenarios.json"
    scenario_path.write_text(
        """
        [
          {
            "id": "smoke",
            "message": "推荐防晒霜",
            "session_id": "eval_smoke",
            "expect": {"min_product_items": 1, "event_types": ["ack", "done"]}
          }
        ]
        """,
        encoding="utf-8",
    )
    app = create_app(use_fake_llm=True, use_fake_retriever=True)

    scenarios = load_scenarios(scenario_path)
    report = run_scenarios(app, scenarios)

    assert report.total == 1
    assert report.passed == 1



def test_eval_runner_adds_retrieval_attribution_for_user_message():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    gold_product_id = next(
        product.product_id
        for product in app.state.products
        if product.sub_category == "\u9632\u6652"
    )
    scenarios = [
        load_scenarios_from_dict(
            {
                "id": "attribution_sunscreen",
                "message": "\u63a8\u8350\u9632\u6652\u971c",
                "session_id": "eval_attribution_sunscreen",
                "expect": {"min_product_items": 1, "gold_product_ids": [gold_product_id]},
            }
        )
    ]

    report = run_scenarios(app, scenarios)
    result = report.results[0]

    assert report.attribution_summary is not None
    assert result.gold_ids == [gold_product_id]
    assert result.retrieval_query
    assert result.hard_constraints
    assert result.pre_filter_top20
    assert isinstance(result.post_filter_top20, list)
    assert result.final_top5 == result.product_ids[:5]
    assert result.miss_reason in {"hit", "lexical_miss", "hard_filter_removed_gold", "rerank_demoted_gold"}


def test_eval_runner_marks_clarification_as_blocked():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    scenario = load_scenarios_from_dict(
        {
            "id": "clarify_phone",
            "message": "\u63a8\u8350\u624b\u673a",
            "session_id": "eval_attribution_clarify",
            "expect": {"gold_product_ids": ["p_digital_001"]},
        }
    )

    report = run_scenarios(app, [scenario])
    result = report.results[0]

    assert result.clarification_blocked is True
    assert result.miss_reason == "clarification_blocked"
    assert report.attribution_summary.clarification_block_rate >= 0


def test_write_attribution_csv_outputs_failure_table_columns(tmp_path: Path):
    from backend.app.eval.models import EvalAttributionSummary, EvalReport, EvalScenarioResult
    from backend.app.eval.runner import write_attribution_csv

    report = EvalReport(
        total=1,
        passed=0,
        failed=1,
        attribution_summary=EvalAttributionSummary(
            attribution_n=1,
            planner_pass_rate=0.0,
            clarification_block_rate=1.0,
            pre_filter_recall_at_20=0.0,
            post_filter_recall_at_20=0.0,
            final_recall_at_5=0.0,
            primary_hit_at_1=0.0,
        ),
        results=[
            EvalScenarioResult(
                id="case_1",
                passed=False,
                planner_ok=False,
                clarification_blocked=True,
                retrieval_query="phone",
                hard_constraints={"category": "electronics"},
                gold_ids=["p1"],
                gold_primary_ids=["p1"],
                pre_filter_top20=["p2"],
                post_filter_top20=[],
                final_top5=[],
                miss_reason="clarification_blocked",
            )
        ],
    )
    detail_path = tmp_path / "detail.csv"
    summary_path = tmp_path / "summary.csv"

    write_attribution_csv(report, detail_path, summary_path)

    detail = detail_path.read_text(encoding="utf-8")
    summary = summary_path.read_text(encoding="utf-8")
    assert "scenario,planner_ok,clarification_blocked,retrieval_query,hard_constraints,gold_ids,gold_primary_ids" in detail
    assert "miss_reason" in detail
    assert "predicted_top" in detail
    assert "planner_pass_rate" in summary


def test_attribution_summary_uses_primary_gold_ids_for_hit_at_one():
    from backend.app.eval.models import EvalScenarioResult
    from backend.app.eval.runner import _summarize_attribution

    summary = _summarize_attribution(
        [
            EvalScenarioResult(
                id="case_primary",
                passed=True,
                planner_ok=True,
                gold_ids=["p1", "p2"],
                gold_primary_ids=["p1"],
                final_top5=["p2", "p1"],
            )
        ]
    )

    assert summary.final_recall_at_5 == 1.0
    assert summary.primary_hit_at_1 == 0.0


def load_scenarios_from_dict(raw: dict):
    from backend.app.eval.models import EvalScenario

    return EvalScenario.model_validate(raw)


def test_eval_loader_populates_gold_ids_from_adjacent_golden_products(tmp_path: Path):
    scenarios_path = tmp_path / "recommend.json"
    golden_path = tmp_path / "golden_products.json"
    scenarios_path.write_text(
        """
        [
          {
            "id": "case_gold",
            "message": "recommend sunscreen",
            "session_id": "eval_gold",
            "golden_id": "gold_sunscreen",
            "expect": {"min_product_items": 1}
          }
        ]
        """,
        encoding="utf-8",
    )
    golden_path.write_text(
        """
        {
          "_meta": {},
          "gold_sunscreen": {
            "ideal_top": ["p1", "p2"],
            "acceptable": ["p1", "p2", "p3"]
          }
        }
        """,
        encoding="utf-8",
    )

    scenarios = load_scenarios(scenarios_path)

    assert scenarios[0].golden_id == "gold_sunscreen"
    assert scenarios[0].expect.gold_product_ids == ["p1", "p2"]
    assert scenarios[0].expect.gold_primary_ids == ["p1", "p2"]


def test_attribution_summary_uses_fractional_gold_recall():
    from backend.app.eval.models import EvalScenarioResult
    from backend.app.eval.runner import _summarize_attribution

    summary = _summarize_attribution(
        [
            EvalScenarioResult(
                id="case_partial",
                passed=True,
                planner_ok=True,
                gold_ids=["p1", "p2"],
                final_top5=["p2", "p3"],
                pre_filter_top20=["p1", "p2"],
                post_filter_top20=["p2"],
            )
        ]
    )

    assert summary.pre_filter_recall_at_20 == 1.0
    assert summary.post_filter_recall_at_20 == 0.5
    assert summary.final_recall_at_5 == 0.5


def test_evaluate_events_enforces_recommend_ablation_expectations():
    from backend.app.eval.metrics import evaluate_events
    from backend.app.eval.models import EvalExpectation, EvalScenario

    scenario = EvalScenario(
        id="case_metrics",
        message="recommend",
        session_id="eval_metrics",
        expect=EvalExpectation(
            min_product_items=1,
            price_min=100,
            expected_brands=["BrandA"],
            forbidden_brands=["BrandB"],
            expect_product_ids_subset_of=["p1", "p2"],
        ),
    )
    events = [
        {
            "type": "product_item",
            "product": {
                "product_id": "p3",
                "name": "Product",
                "description": "",
                "price": 50,
                "brand": "BrandB",
            },
        }
    ]

    result = evaluate_events(scenario, events)

    assert result.passed is False
    assert any("below min" in failure for failure in result.failures)
    assert any("missing expected brand" in failure for failure in result.failures)
    assert any("forbidden brand" in failure for failure in result.failures)
    assert any("outside expected subset" in failure for failure in result.failures)


def test_evaluate_events_accepts_clarification_request():
    from backend.app.eval.metrics import evaluate_events
    from backend.app.eval.models import EvalExpectation, EvalScenario

    scenario = EvalScenario(
        id="case_clarify",
        message="recommend phone",
        session_id="eval_clarify",
        expect=EvalExpectation(expect_clarification=True),
    )

    result = evaluate_events(scenario, [{"type": "clarification_request"}])

    assert result.passed is True


def test_miss_reason_marks_gold_constraint_conflict_before_filter_removed():
    from backend.app.eval.runner import _classify_miss_reason
    from backend.app.models import HardConstraints, Product

    products = {
        "gold": Product(
            product_id="gold",
            title="Gold",
            brand="Brand",
            category="cat",
            sub_category="sub",
            price=1000,
            image_path="",
            search_text="gold",
        )
    }

    reason = _classify_miss_reason(
        gold_ids=["gold"],
        product_ids=set(products),
        product_map=products,
        hard_constraints=HardConstraints(price_max=500),
        planner_ok=True,
        clarification_blocked=False,
        pre_filter_top20=["gold"],
        post_filter_top20=[],
        final_top5=[],
    )

    assert reason == "gold_conflicts_with_constraints"


def test_miss_reason_marks_empty_final_emission_after_retrieval_hit():
    from backend.app.eval.runner import _classify_miss_reason
    from backend.app.models import HardConstraints

    reason = _classify_miss_reason(
        gold_ids=["gold"],
        product_ids={"gold"},
        product_map={},
        hard_constraints=HardConstraints(),
        planner_ok=True,
        clarification_blocked=False,
        pre_filter_top20=["gold"],
        post_filter_top20=["gold"],
        final_top5=[],
    )

    assert reason == "final_emission_empty"
