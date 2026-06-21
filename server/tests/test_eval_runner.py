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
