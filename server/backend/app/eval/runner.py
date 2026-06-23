from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..constraint_filter import hard_filter
from ..models import ChatRequest, RetrievalPlan
from .metrics import evaluate_events
from .models import EvalAttributionSummary, EvalReport, EvalScenario, EvalScenarioResult

_RECOMMEND_INTENTS = {"recommend_product", "product_followup"}
_MISS_REASONS = {
    "hit",
    "planner_wrong",
    "clarification_blocked",
    "hard_filter_removed_gold",
    "lexical_miss",
    "dense_miss",
    "fusion_no_gain",
    "rerank_demoted_gold",
    "gold_label_mismatch",
}


def load_scenarios(path: str | Path) -> list[EvalScenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalScenario.model_validate(item) for item in data]


def run_scenarios(app: FastAPI, scenarios: list[EvalScenario]) -> EvalReport:
    client = TestClient(app)
    results: list[EvalScenarioResult] = []
    for scenario in scenarios:
        if scenario.type == "user_message":
            events = _run_user_message(client, scenario)
            result = evaluate_events(scenario, events)
            result = _merge_attribution(result, _build_retrieval_attribution(app, scenario, events))
            results.append(result)
        elif scenario.type == "cart_action":
            events = _run_cart_action(client, scenario)
            results.append(evaluate_events(scenario, events))
        elif scenario.type == "order_flow":
            events = _run_order_flow(client, scenario)
            results.append(evaluate_events(scenario, events))
        else:
            results.append(
                evaluate_events(scenario, [{"type": "error", "message": f"unknown scenario type {scenario.type}"}])
            )
    passed = sum(1 for result in results if result.passed)
    return EvalReport(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
        attribution_summary=_summarize_attribution(results),
    )


def write_attribution_csv(report: EvalReport, detail_path: str | Path, summary_path: str | Path) -> None:
    detail_path = Path(detail_path)
    summary_path = Path(summary_path)
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    detail_fields = [
        "scenario",
        "planner_ok",
        "clarification_blocked",
        "retrieval_query",
        "hard_constraints",
        "gold_ids",
        "gold_primary_ids",
        "pre_filter_top20",
        "post_filter_top20",
        "final_top5",
        "predicted_top",
        "miss_reason",
    ]
    with detail_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields)
        writer.writeheader()
        for result in report.results:
            writer.writerow(
                {
                    "scenario": result.id,
                    "planner_ok": result.planner_ok,
                    "clarification_blocked": result.clarification_blocked,
                    "retrieval_query": result.retrieval_query or "",
                    "hard_constraints": json.dumps(result.hard_constraints, ensure_ascii=False, sort_keys=True),
                    "gold_ids": "|".join(result.gold_ids),
                    "gold_primary_ids": "|".join(result.gold_primary_ids),
                    "pre_filter_top20": "|".join(result.pre_filter_top20),
                    "post_filter_top20": "|".join(result.post_filter_top20),
                    "final_top5": "|".join(result.final_top5),
                    "predicted_top": result.final_top5[0] if result.final_top5 else "",
                    "miss_reason": result.miss_reason or "",
                }
            )
    summary = report.attribution_summary or EvalAttributionSummary()
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary.model_dump(mode="json").keys()))
        writer.writeheader()
        writer.writerow(summary.model_dump(mode="json"))


def _merge_attribution(result: EvalScenarioResult, attribution: dict[str, Any]) -> EvalScenarioResult:
    return result.model_copy(update=attribution)


def _build_retrieval_attribution(app: FastAPI, scenario: EvalScenario, events: list[dict]) -> dict[str, Any]:
    agent = getattr(app.state, "agent", None)
    if agent is None:
        return {}
    context = agent.sessions.get(scenario.session_id)
    plan = getattr(context, "last_plan", None)
    final_top5 = _event_product_ids(events)[:5]
    gold_ids = _scenario_gold_ids(scenario)
    gold_primary_ids = _scenario_primary_gold_ids(scenario)
    clarification_blocked = _clarification_blocked(plan, events)
    attribution: dict[str, Any] = {
        "gold_ids": gold_ids,
        "gold_primary_ids": gold_primary_ids,
        "final_top5": final_top5,
        "clarification_blocked": clarification_blocked,
    }
    if plan is None:
        attribution.update({"planner_ok": False, "miss_reason": _miss_reason_without_plan(gold_ids)})
        return attribution
    planner_ok = plan.intent in _RECOMMEND_INTENTS and not plan.need_clarification
    pre_filter_top20 = _pre_filter_top20(agent, plan)
    post_filter_top20 = _post_filter_top20(agent, plan, pre_filter_top20)
    miss_reason = _classify_miss_reason(
        gold_ids=gold_ids,
        product_ids=set(agent.product_map.keys()),
        planner_ok=planner_ok,
        clarification_blocked=clarification_blocked,
        pre_filter_top20=pre_filter_top20,
        post_filter_top20=post_filter_top20,
        final_top5=final_top5,
    )
    attribution.update(
        {
            "planner_ok": planner_ok,
            "retrieval_query": plan.retrieval_query,
            "hard_constraints": plan.hard_constraints.model_dump(mode="json"),
            "pre_filter_top20": pre_filter_top20,
            "post_filter_top20": post_filter_top20,
            "miss_reason": miss_reason,
        }
    )
    return attribution


def _scenario_gold_ids(scenario: EvalScenario) -> list[str]:
    if scenario.expect.gold_product_ids:
        return list(scenario.expect.gold_product_ids)
    return list(scenario.expect.expected_product_ids)


def _scenario_primary_gold_ids(scenario: EvalScenario) -> list[str]:
    if scenario.expect.gold_primary_ids:
        return list(scenario.expect.gold_primary_ids)
    return _scenario_gold_ids(scenario)


def _event_product_ids(events: list[dict]) -> list[str]:
    product_ids: list[str] = []
    for event in events:
        if event.get("type") != "product_item":
            continue
        product = event.get("product", {})
        if isinstance(product, dict) and product.get("product_id"):
            product_ids.append(str(product["product_id"]))
    return product_ids


def _clarification_blocked(plan: RetrievalPlan | None, events: list[dict]) -> bool:
    event_types = {event.get("type") for event in events}
    if "clarification_request" in event_types:
        return True
    if plan is None:
        return False
    return plan.need_clarification or plan.intent == "clarification"


def _pre_filter_top20(agent, plan: RetrievalPlan) -> list[str]:
    try:
        results = agent.retriever.search(plan.retrieval_query or "", top_k=20)
    except Exception:
        return []
    return [product.product_id for product, _ in results[:20]]


def _post_filter_top20(agent, plan: RetrievalPlan, pre_filter_top20: list[str]) -> list[str]:
    product_map = agent.product_map
    filtered: list[str] = []
    for product_id in pre_filter_top20:
        product = product_map.get(product_id)
        if product is not None and hard_filter(product, plan.hard_constraints):
            filtered.append(product_id)
    return filtered[:20]


def _classify_miss_reason(
    *,
    gold_ids: list[str],
    product_ids: set[str],
    planner_ok: bool,
    clarification_blocked: bool,
    pre_filter_top20: list[str],
    post_filter_top20: list[str],
    final_top5: list[str],
) -> str | None:
    if not gold_ids:
        return None
    if any(gold_id not in product_ids for gold_id in gold_ids):
        return "gold_label_mismatch"
    if any(gold_id in final_top5 for gold_id in gold_ids):
        return "hit"
    if clarification_blocked:
        return "clarification_blocked"
    if not planner_ok:
        return "planner_wrong"
    if not any(gold_id in pre_filter_top20 for gold_id in gold_ids):
        return "lexical_miss"
    if not any(gold_id in post_filter_top20 for gold_id in gold_ids):
        return "hard_filter_removed_gold"
    if any(gold_id in post_filter_top20 for gold_id in gold_ids):
        return "rerank_demoted_gold"
    return "fusion_no_gain"


def _miss_reason_without_plan(gold_ids: list[str]) -> str | None:
    if not gold_ids:
        return None
    return "planner_wrong"


def _summarize_attribution(results: list[EvalScenarioResult]) -> EvalAttributionSummary | None:
    attributed = [result for result in results if result.planner_ok is not None]
    if not attributed:
        return None
    gold_results = [result for result in attributed if result.gold_ids]
    return EvalAttributionSummary(
        attribution_n=len(attributed),
        planner_pass_rate=_mean_bool(result.planner_ok for result in attributed),
        clarification_block_rate=_mean_bool(result.clarification_blocked for result in attributed),
        pre_filter_recall_at_20=_gold_recall(gold_results, "pre_filter_top20"),
        post_filter_recall_at_20=_gold_recall(gold_results, "post_filter_top20"),
        final_recall_at_5=_gold_recall(gold_results, "final_top5"),
        primary_hit_at_1=_primary_hit_at_1(gold_results),
    )


def _mean_bool(values) -> float | None:
    items = [bool(value) for value in values if value is not None]
    if not items:
        return None
    return sum(1 for value in items if value) / len(items)


def _gold_recall(results: list[EvalScenarioResult], field_name: str) -> float | None:
    if not results:
        return None
    hits = 0
    for result in results:
        predicted = set(getattr(result, field_name))
        if any(gold_id in predicted for gold_id in result.gold_ids):
            hits += 1
    return hits / len(results)


def _primary_hit_at_1(results: list[EvalScenarioResult]) -> float | None:
    if not results:
        return None
    hits = 0
    for result in results:
        primary_gold_ids = result.gold_primary_ids or result.gold_ids
        if result.final_top5 and result.final_top5[0] in primary_gold_ids:
            hits += 1
    return hits / len(results)


def _run_user_message(client: TestClient, scenario: EvalScenario) -> list[dict]:
    events: list[dict] = []
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": scenario.session_id,
                "message": scenario.message,
            }
        )
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event.get("type") == "done":
                break
    return events


def _run_cart_action(client: TestClient, scenario: EvalScenario) -> list[dict]:
    product_id = client.get("/api/products").json()["products"][0]["product_id"]
    events: list[dict] = []
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "cart_action",
                "session_id": scenario.session_id,
                "action": "add_to_cart",
                "product_id": product_id,
                "quantity": 1,
            }
        )
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event.get("type") == "done":
                break
    return events


def _run_order_flow(client: TestClient, scenario: EvalScenario) -> list[dict]:
    product_id = client.get("/api/products").json()["products"][0]["product_id"]
    client.post("/api/cart/clear", json={"session_id": scenario.session_id})
    client.post("/api/cart/add", json={"session_id": scenario.session_id, "product_id": product_id, "quantity": 1})
    initiated = client.post("/api/order/initiate", json={"session_id": scenario.session_id}).json()
    address_id = client.get("/api/order/addresses").json()["addresses"][0]["address_id"]
    selected = client.post(
        "/api/order/select_address",
        json={"order_id": initiated["order_id"], "address_id": address_id},
    ).json()
    confirmed = client.post(
        "/api/order/confirm",
        json={
            "order_id": initiated["order_id"],
            "confirmation_token": selected["confirmation_token"],
            "idempotency_key": f"eval_{scenario.id}",
        },
    ).json()
    return [{"type": "order_flow", "status": confirmed.get("status"), "order_id": confirmed.get("order_id")}]
