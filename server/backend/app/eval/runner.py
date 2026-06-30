"""Phase 2 评测 runner。

设计要点：
- 一个 scenario 串多个 step，共享 session_id 和 WebSocket（保留多轮上下文）
- 每 step 独立断言，scenario 级别聚合
- step 间通过 bind 字段把 product_ids[0]/cart_quantity 等值存入 scenario_vars，
  下一步用 ${var_name} 占位符引用
- fault 字段在 scenario 开始前对 app.state.agent.llm / stt_adapter 等 monkeypatch
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..planning.constraint_filter import hard_filter
from ..models import RetrievalPlan
from .metrics import evaluate_step
from .models import (
    EvalAttributionSummary,
    EvalReport,
    EvalScenario,
    EvalScenarioResult,
    EvalStep,
    EvalStepResult,
)

_RECOMMEND_INTENTS = {"recommend_product", "product_followup"}

try:
    from .fixtures import apply_fault
except Exception:  # pragma: no cover - fixtures are optional
    apply_fault = None  # type: ignore[assignment]


def load_scenarios(path: str | Path) -> list[EvalScenario]:
    """Load scenarios from a JSON file or from all JSON files in a directory."""
    p = Path(path)
    if p.is_dir():
        items: list[dict] = []
        for file in sorted(p.glob("*.json")):
            if file.name == "golden_products.json":
                continue
            file_items = json.loads(file.read_text(encoding="utf-8"))
            if isinstance(file_items, list):
                items.extend(file_items)
        scenarios = [EvalScenario.model_validate(item) for item in items]
        golden = _load_adjacent_golden_products(p / "_scenarios.json")
    else:
        data = json.loads(p.read_text(encoding="utf-8"))
        scenarios = [EvalScenario.model_validate(item) for item in data]
        golden = _load_adjacent_golden_products(p)
    if golden:
        scenarios = [_apply_golden_products(scenario, golden) for scenario in scenarios]
    return scenarios



def _load_adjacent_golden_products(path: Path) -> dict[str, dict[str, Any]]:
    golden_path = path.parent / "golden_products.json"
    if not golden_path.exists():
        return {}
    raw = json.loads(golden_path.read_text(encoding="utf-8"))
    return {
        key: value
        for key, value in raw.items()
        if not key.startswith("_") and isinstance(value, dict)
    }


def _apply_golden_products(scenario: EvalScenario, golden: dict[str, dict[str, Any]]) -> EvalScenario:
    if not scenario.golden_id or scenario.golden_id not in golden:
        return scenario
    entry = golden[scenario.golden_id]
    ideal_top = [str(item) for item in entry.get("ideal_top", [])]
    if not ideal_top:
        return scenario
    expect = scenario.expect.model_copy(
        update={
            "gold_product_ids": scenario.expect.gold_product_ids or ideal_top,
            "gold_primary_ids": scenario.expect.gold_primary_ids or ideal_top,
        }
    )
    return scenario.model_copy(update={"expect": expect})


def run_scenarios(app: FastAPI, scenarios: list[EvalScenario]) -> EvalReport:
    client = TestClient(app)
    results: list[EvalScenarioResult] = []
    for scenario in scenarios:
        result = _run_scenario(app, client, scenario)
        results.append(result)
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
    context = agent.sessions.get("anonymous", scenario.session_id)
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
        product_map=agent.product_map,
        hard_constraints=plan.hard_constraints,
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
    product_map: dict[str, Any] | None = None,
    hard_constraints: Any = None,
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
    if _gold_conflicts_with_constraints(gold_ids, product_map or {}, hard_constraints):
        return "gold_conflicts_with_constraints"
    if not any(gold_id in post_filter_top20 for gold_id in gold_ids):
        return "hard_filter_removed_gold"
    if not final_top5 and any(gold_id in post_filter_top20 for gold_id in gold_ids):
        return "final_emission_empty"
    if any(gold_id in post_filter_top20 for gold_id in gold_ids):
        return "rerank_demoted_gold"
    return "fusion_no_gain"


def _gold_conflicts_with_constraints(gold_ids: list[str], product_map: dict[str, Any], hard_constraints: Any) -> bool:
    if hard_constraints is None or not product_map:
        return False
    for gold_id in gold_ids:
        product = product_map.get(gold_id)
        if product is not None and hard_filter(product, hard_constraints):
            return False
    return True


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
    recalls: list[float] = []
    for result in results:
        predicted = set(getattr(result, field_name))
        gold = set(result.gold_ids)
        if not gold:
            continue
        recalls.append(len(predicted & gold) / len(gold))
    if not recalls:
        return None
    return sum(recalls) / len(recalls)


def _primary_hit_at_1(results: list[EvalScenarioResult]) -> float | None:
    if not results:
        return None
    hits = 0
    for result in results:
        primary_gold_ids = result.gold_primary_ids or result.gold_ids
        if result.final_top5 and result.final_top5[0] in primary_gold_ids:
            hits += 1
    return hits / len(results)


def _run_scenario(app: FastAPI, client: TestClient, scenario: EvalScenario) -> EvalScenarioResult:
    """单 scenario 执行：可选 fault 注入 → 多 step 依次执行 → 聚合结果。"""
    # 评测隔离：清掉本 session_id 在 cart 持久化里的残留，避免跨次累加
    try:
        client.post("/api/cart/clear", json={"session_id": scenario.session_id})
    except Exception:
        pass
    # 评测隔离：清掉跨 scenario 共享的内存缓存（plan→ranked、推荐记忆等），
    # 否则后跑的 scenario 会因为前一个相同 plan 的缓存直接命中，跳过真实检索
    _reset_inprocess_caches(app)

    cleanup = None
    if scenario.fault and apply_fault is not None:
        try:
            cleanup = apply_fault(app, scenario.fault)
        except Exception as exc:
            return EvalScenarioResult(
                id=scenario.id,
                passed=False,
                failures=[f"failed to apply fault {scenario.fault!r}: {exc}"],
            )

    scenario_vars: dict[str, Any] = {}
    step_results: list[EvalStepResult] = []
    all_failures: list[str] = []
    all_product_ids: list[str] = []
    total_events = 0
    all_events: list[dict] = []

    try:
        for index, step in enumerate(scenario.steps):
            resolved_step = _resolve_step_placeholders(step, scenario_vars)
            try:
                events = _run_step(client, scenario, resolved_step)
            except Exception as exc:
                step_results.append(
                    EvalStepResult(
                        step_index=index,
                        passed=False,
                        failures=[f"step crashed: {exc}"],
                    )
                )
                all_failures.append(f"step {index} crashed: {exc}")
                continue

            all_events.extend(events)
            step_result = evaluate_step(resolved_step.expect, events, index, scenario_vars)
            step_results.append(step_result)
            total_events += step_result.event_count
            all_product_ids.extend(step_result.product_ids)
            if step_result.failures:
                all_failures.extend(
                    f"step {index}: {failure}" for failure in step_result.failures
                )

            # 应用 bind：把本步的执行结果存入 scenario_vars 供后续 step 引用
            _apply_bindings(resolved_step.bind, step_result, events, scenario_vars)
    finally:
        if cleanup is not None:
            try:
                cleanup()
            except Exception:
                pass

    result = EvalScenarioResult(
        id=scenario.id,
        passed=not all_failures,
        failures=all_failures,
        event_count=total_events,
        product_ids=all_product_ids,
        steps=step_results,
    )
    return _merge_attribution(result, _build_retrieval_attribution(app, scenario, all_events))


def _run_step(client: TestClient, scenario: EvalScenario, step: EvalStep) -> list[dict]:
    action = step.action
    if action == "user_message":
        return _run_user_message(client, scenario.session_id, step.message)
    if action == "cart_action":
        return _run_cart_action(client, scenario.session_id, step.payload)
    if action == "order_action":
        return _run_order_action(client, scenario.session_id, step.payload)
    if action == "websocket_disconnect":
        return _run_websocket_disconnect(client, scenario.session_id)
    if action == "wait":
        return []
    return [{"type": "error", "message": f"unknown action {action!r}"}]


def _resolve_step_placeholders(step: EvalStep, scenario_vars: dict[str, Any]) -> EvalStep:
    """把 step.message 和 step.payload 中的 ${var_name} 替换成实际值。

    expect 字段的占位符替换在 evaluate_step 内部完成；这里只处理执行时需要的输入。
    """
    if not scenario_vars:
        return step
    new_message = _substitute_text(step.message, scenario_vars)
    new_payload = _substitute_any(step.payload, scenario_vars)
    if new_message == step.message and new_payload == step.payload:
        return step
    return step.model_copy(update={"message": new_message, "payload": new_payload})


def _substitute_text(text: str, scenario_vars: dict[str, Any]) -> str:
    if not isinstance(text, str) or "${" not in text:
        return text
    for var, val in scenario_vars.items():
        text = text.replace("${" + var + "}", str(val))
    return text


def _substitute_any(value: Any, scenario_vars: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _substitute_text(value, scenario_vars)
    if isinstance(value, list):
        return [_substitute_any(item, scenario_vars) for item in value]
    if isinstance(value, dict):
        return {key: _substitute_any(item, scenario_vars) for key, item in value.items()}
    return value


_WS_EVENT_TIMEOUT_SECONDS = 30.0  # 单条事件最长等待时间，避免 LLM 卡死把整个评测拖死


def _receive_event_with_timeout(websocket, timeout: float = _WS_EVENT_TIMEOUT_SECONDS) -> dict:
    """TestClient 的 receive_json 默认无超时。为评测安全包一层。"""
    import queue as _queue

    try:
        # starlette TestClient 用 anyio，receive_json 实际是同步 queue.get
        # 直接传 timeout 参数 starlette >= 0.30 支持
        return websocket.receive_json(timeout=timeout)
    except TypeError:
        # 老版本 starlette 不接受 timeout 参数，退化为同步获取（评测全局超时会兜底）
        return websocket.receive_json()
    except _queue.Empty:
        return {"type": "error", "message": f"no event within {timeout}s, presumed stuck"}


def _run_user_message(client: TestClient, session_id: str, message: str) -> list[dict]:
    events: list[dict] = []
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": session_id,
                "message": message,
            }
        )
        while True:
            event = _receive_event_with_timeout(websocket)
            events.append(event)
            if event.get("type") in {"done", "error"}:
                break
    return events


def _run_cart_action(client: TestClient, session_id: str, payload: dict[str, Any]) -> list[dict]:
    """通过 WebSocket 推 cart_action，断言响应事件。

    支持两种 payload 形态：
    - 直接指定 product_id（新版）
    - legacy: 不指定 product_id，runner 自动用 /api/products 的第一个商品（旧测试兼容）
    """
    product_id = payload.get("product_id")
    if not product_id:
        product_id = client.get("/api/products").json()["products"][0]["product_id"]
    action_name = payload.get("action") or "add_to_cart"
    quantity = int(payload.get("quantity") or 1)

    events: list[dict] = []
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "cart_action",
                "session_id": session_id,
                "action": action_name,
                "product_id": product_id,
                "quantity": quantity,
            }
        )
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event.get("type") == "done":
                break
    return events


def _run_order_action(client: TestClient, session_id: str, payload: dict[str, Any]) -> list[dict]:
    """HTTP 订单流程驱动，根据 payload.kind 决定具体调用。

    kind 取值：
    - full: 旧 order_flow 完整端到端（加车 → initiate → select_address → confirm）
    - initiate / select_address / confirm: 单步驱动，便于多 step 场景断言中间状态
    """
    kind = payload.get("kind") or "full"
    if kind == "full":
        return _run_order_flow_legacy(client, session_id, payload)

    if kind == "initiate":
        result = client.post("/api/order/initiate", json={"session_id": session_id}).json()
        return [{"type": "order_status", "status": result.get("status"), "order_id": result.get("order_id")}]

    if kind == "select_address":
        order_id = payload["order_id"]
        address_id = payload.get("address_id") or _first_address_id(client)
        result = client.post(
            "/api/order/select_address",
            json={"order_id": order_id, "address_id": address_id},
        ).json()
        return [
            {
                "type": "order_status",
                "status": result.get("status"),
                "order_id": result.get("order_id"),
                "confirmation_token": result.get("confirmation_token"),
            }
        ]

    if kind == "confirm":
        result = client.post(
            "/api/order/confirm",
            json={
                "order_id": payload["order_id"],
                "confirmation_token": payload.get("confirmation_token"),
                "idempotency_key": payload.get("idempotency_key", f"eval_{session_id}"),
            },
        ).json()
        return [{"type": "order_status", "status": result.get("status"), "order_id": result.get("order_id")}]

    return [{"type": "error", "message": f"unknown order kind {kind!r}"}]


def _run_order_flow_legacy(client: TestClient, session_id: str, payload: dict[str, Any]) -> list[dict]:
    """旧 order_flow 类型的完整 happy path，保留供 5 条核心场景使用。"""
    product_id = payload.get("product_id") or client.get("/api/products").json()["products"][0]["product_id"]
    client.post("/api/cart/clear", json={"session_id": session_id})
    client.post("/api/cart/add", json={"session_id": session_id, "product_id": product_id, "quantity": 1})
    initiated = client.post("/api/order/initiate", json={"session_id": session_id}).json()
    address_id = _first_address_id(client)
    selected = client.post(
        "/api/order/select_address",
        json={"order_id": initiated["order_id"], "address_id": address_id},
    ).json()
    confirmed = client.post(
        "/api/order/confirm",
        json={
            "order_id": initiated["order_id"],
            "confirmation_token": selected["confirmation_token"],
            "idempotency_key": payload.get("idempotency_key", f"eval_{session_id}"),
        },
    ).json()
    return [{"type": "order_flow", "status": confirmed.get("status"), "order_id": confirmed.get("order_id")}]


def _run_websocket_disconnect(client: TestClient, session_id: str) -> list[dict]:
    """打开-关闭 WebSocket，再打开新连接确认 session 可以继续接收消息。"""
    events: list[dict] = []
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "session_id": session_id, "message": "ping"})
        # 收第一个 ack 后立即关闭
        try:
            first = websocket.receive_json()
            events.append(first)
        except Exception:
            pass
    # 重连验证 session_id 仍可用
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "session_id": session_id, "message": "你还在吗"})
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event.get("type") == "done":
                break
    return events


def _first_address_id(client: TestClient) -> str:
    return client.get("/api/order/addresses").json()["addresses"][0]["address_id"]


def _reset_inprocess_caches(app: FastAPI) -> None:
    """评测隔离：清空 plan→ranked 和推荐记忆等进程内缓存。

    生产代码里这些 cache 提升响应速度，但评测时它会让"后跑的 scenario 命中前一个相同 plan
    的缓存"导致检索被跳过、断言失真。仅在评测路径调用。
    """
    agent = getattr(app.state, "agent", None)
    if agent is None:
        return
    for attr in ("memory_cache", "recommendation_memory"):
        cache = getattr(agent, attr, None)
        items = getattr(cache, "_items", None)
        if isinstance(items, dict):
            items.clear()
    # 同时清掉 session_store 里这个 session 的历史
    sessions = getattr(agent, "sessions", None)
    if sessions is not None:
        inner = getattr(sessions, "_sessions", None)
        if isinstance(inner, dict):
            inner.clear()


def _apply_bindings(
    bindings: dict[str, str],
    step_result: EvalStepResult,
    events: list[dict],
    scenario_vars: dict[str, Any],
) -> None:
    """把本步结果中的命名值存入 scenario_vars。

    支持的 selector 语法：
    - product_ids[0]: 商品事件中第 0 个 product_id
    - product_ids[N]: 第 N 个
    - last_order_id: 最近一次 order_status 的 order_id
    - last_confirmation_token: 最近一次 order_status 的 confirmation_token
    - last_cart_quantity[<product_id>]: 最新 cart_update 中指定 product 的 quantity
    """
    for var_name, selector in bindings.items():
        value = _resolve_binding_selector(selector, step_result, events)
        if value is not None:
            scenario_vars[var_name] = value


def _resolve_binding_selector(
    selector: str,
    step_result: EvalStepResult,
    events: list[dict],
) -> Any:
    if selector.startswith("product_ids[") and selector.endswith("]"):
        try:
            index = int(selector[len("product_ids[") : -1])
            if 0 <= index < len(step_result.product_ids):
                return step_result.product_ids[index]
        except ValueError:
            return None
        return None

    if selector == "last_order_id":
        for event in reversed(events):
            if event.get("type") in {"order_status", "order_flow"}:
                return event.get("order_id")
        return None

    if selector == "last_confirmation_token":
        for event in reversed(events):
            if event.get("type") in {"order_status", "order_flow"}:
                token = event.get("confirmation_token")
                if token:
                    return token
        return None

    if selector.startswith("last_cart_quantity[") and selector.endswith("]"):
        target = selector[len("last_cart_quantity[") : -1]
        for event in reversed(events):
            if event.get("type") not in {"cart_update", "cart_snapshot"}:
                continue
            items = event.get("items") or event.get("cart", {}).get("items") or []
            for item in items:
                if isinstance(item, dict) and item.get("product_id") == target:
                    return int(item.get("quantity") or 0)
        return None

    return None
