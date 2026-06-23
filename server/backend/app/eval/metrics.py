"""评测断言层。

每个 EvalExpectation 字段对应一组断言函数，命中失败追加到 failures。
新断言通过分析 event 列表 + 解释文本（text_delta 拼接）+ cart/order 状态完成。
"""

from __future__ import annotations

from typing import Any

from .models import EvalExpectation, EvalScenario, EvalScenarioResult, EvalStep, EvalStepResult


def evaluate_events(scenario: EvalScenario, events: list[dict]) -> EvalScenarioResult:
    """旧 API：把整个 scenario 当作单 step 求值。

    主要给现有 5 条核心场景和旧测试用，保证向后兼容。
    """
    expectation = scenario.expect
    step_result = _evaluate_expectation(expectation, events, step_index=0, scenario_vars={})
    return EvalScenarioResult(
        id=scenario.id,
        passed=step_result.passed,
        failures=step_result.failures,
        event_count=step_result.event_count,
        product_ids=step_result.product_ids,
        steps=[step_result],
        metrics=step_result.metrics,
    )


def evaluate_step(
    expectation: EvalExpectation,
    events: list[dict],
    step_index: int,
    scenario_vars: dict[str, Any],
) -> EvalStepResult:
    """单步断言入口。

    scenario_vars 在 runner 跨 step 维护，用于 ${var_name} 占位符替换。
    """
    return _evaluate_expectation(expectation, events, step_index, scenario_vars)


def _evaluate_expectation(
    expectation: EvalExpectation,
    events: list[dict],
    step_index: int,
    scenario_vars: dict[str, Any],
) -> EvalStepResult:
    expectation = _resolve_placeholders(expectation, scenario_vars)
    failures: list[str] = []

    event_types = [event.get("type") for event in events]
    product_events = [event for event in events if event.get("type") == "product_item"]
    product_ids = _extract_product_ids(product_events)
    explanation_text = _join_text_deltas(events).lower()

    # ---- 基础断言（旧版） ----
    if len(product_events) < expectation.min_product_items:
        failures.append(
            f"expected at least {expectation.min_product_items} product_item events, got {len(product_events)}"
        )

    for required in expectation.event_types:
        if required not in event_types:
            failures.append(f"missing event type: {required}")

    for expected_product_id in expectation.expected_product_ids:
        if expected_product_id not in product_ids:
            failures.append(f"missing expected product: {expected_product_id}")

    for forbidden_product_id in expectation.forbidden_product_ids:
        if forbidden_product_id in product_ids:
            failures.append(f"forbidden product returned: {forbidden_product_id}")

    for product_event in product_events:
        product = product_event.get("product", {})
        if not isinstance(product, dict):
            continue
        product_name = product.get("name", "")
        product_description = product.get("description", "")
        product_text = f"{product_name} {product_description}".lower()
        for term in expectation.forbid_terms:
            if term.lower() in product_text:
                failures.append(f"forbidden term '{term}' found in product: {product_name}")
                break
        price = product.get("price")
        if expectation.price_max is not None and price is not None:
            if price > expectation.price_max:
                failures.append(
                    f"product {product_name} price {price} exceeds max {expectation.price_max}"
                )
        if expectation.price_min is not None and price is not None:
            if price < expectation.price_min:
                failures.append(
                    f"product {product_name} price {price} below min {expectation.price_min}"
                )

    if expectation.require_cart_success:
        cart_events = [event for event in events if event.get("type") == "cart_update"]
        if not cart_events:
            failures.append("missing cart_update event for require_cart_success")
        else:
            for cart_event in cart_events:
                success = cart_event.get("success", False)
                if not success:
                    failures.append("cart_update event reported failure")
                    break

    if expectation.require_order_completed:
        order_events = [event for event in events if event.get("type") == "order_flow"]
        if not order_events:
            failures.append("missing order_flow event for require_order_completed")
        else:
            for order_event in order_events:
                if order_event.get("status") != "completed":
                    failures.append("order_flow event reported incomplete")
                    break

    # ---- Phase 2 新断言 ----
    _check_brands(failures, product_events, expectation.expected_brands, expectation.forbidden_brands)
    _check_clarification(failures, events, expectation.expect_clarification)
    _check_no_match(failures, events, explanation_text, expectation.expect_no_match)
    _check_comparison(failures, events, expectation.expect_comparison)
    _check_order_status(failures, events, expectation.expect_order_status)
    _check_cart_quantity(failures, events, expectation.expect_cart_quantity)
    _check_error_kind(failures, events, explanation_text, expectation.expect_error_kind)
    _check_product_subset(failures, product_ids, expectation.expect_product_ids_subset_of)
    _check_explanation_forbidden_terms(failures, explanation_text, expectation.forbidden_terms_in_explanation)
    _check_focus_product(failures, events, expectation.expected_focus_product)

    return EvalStepResult(
        step_index=step_index,
        passed=not failures,
        failures=failures,
        event_count=len(events),
        product_ids=product_ids,
    )


# ---------- 工具函数 ----------


def _extract_product_ids(product_events: list[dict]) -> list[str]:
    ids: list[str] = []
    for event in product_events:
        product = event.get("product")
        if isinstance(product, dict):
            pid = product.get("product_id", "")
            if pid:
                ids.append(pid)
    return ids


def _join_text_deltas(events: list[dict]) -> str:
    parts: list[str] = []
    for event in events:
        if event.get("type") != "text_delta":
            continue
        delta = event.get("delta") or event.get("text") or ""
        if isinstance(delta, str):
            parts.append(delta)
    return "".join(parts)


def _resolve_placeholders(expectation: EvalExpectation, scenario_vars: dict[str, Any]) -> EvalExpectation:
    """把 expectation 中的 ${var_name} 替换为 scenario_vars 中的值。

    仅处理字符串/字符串列表字段，避免触碰数值字段（price_min/price_max）。
    """
    if not scenario_vars:
        return expectation
    data = expectation.model_dump()
    for key, value in list(data.items()):
        data[key] = _resolve_value(value, scenario_vars)
    return EvalExpectation.model_validate(data)


def _resolve_value(value: Any, scenario_vars: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _substitute_string(value, scenario_vars)
    if isinstance(value, list):
        return [_resolve_value(item, scenario_vars) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_value(item, scenario_vars) for key, item in value.items()}
    return value


def _substitute_string(text: str, scenario_vars: dict[str, Any]) -> str:
    if "${" not in text:
        return text
    result = text
    for var_name, var_value in scenario_vars.items():
        token = "${" + var_name + "}"
        if token in result:
            result = result.replace(token, str(var_value))
    return result


# ---------- 新断言函数 ----------


def _check_brands(
    failures: list[str],
    product_events: list[dict],
    expected_brands: list[str],
    forbidden_brands: list[str],
) -> None:
    if not expected_brands and not forbidden_brands:
        return
    returned_brands = []
    for event in product_events:
        product = event.get("product")
        if isinstance(product, dict):
            brand = product.get("brand") or ""
            if brand:
                returned_brands.append(brand)
    returned_lower = {brand.lower() for brand in returned_brands}
    for expected in expected_brands:
        if expected.lower() not in returned_lower:
            failures.append(f"expected brand '{expected}' not found in returned products")
    for forbidden in forbidden_brands:
        if forbidden.lower() in returned_lower:
            failures.append(f"forbidden brand '{forbidden}' returned")


def _check_clarification(failures: list[str], events: list[dict], expected: bool) -> None:
    if not expected:
        return
    has_clarification = any(event.get("type") == "clarification_request" for event in events)
    if not has_clarification:
        failures.append("missing clarification_request event")


def _check_no_match(failures: list[str], events: list[dict], explanation_text: str, expected: bool) -> None:
    if not expected:
        return
    no_match_markers = ["没有完全满足", "没有匹配", "没找到匹配"]
    has_marker = any(marker in explanation_text for marker in no_match_markers)
    # 同时要求没有真实 product_item 事件
    has_products = any(event.get("type") == "product_item" for event in events)
    if not has_marker:
        failures.append("missing no_match degradation text")
    if has_products:
        failures.append("expected no_match but product_item events still emitted")


def _check_comparison(failures: list[str], events: list[dict], expected: bool) -> None:
    if not expected:
        return
    has_comparison = any(event.get("type") == "comparison_result" for event in events)
    if not has_comparison:
        failures.append("missing comparison_result event")


def _check_order_status(failures: list[str], events: list[dict], expected_status: str | None) -> None:
    if not expected_status:
        return
    # order_action 步的执行结果由 runner 包装为 type='order_status' 事件
    statuses: list[str] = []
    for event in events:
        kind = event.get("type")
        if kind in {"order_status", "order_flow"}:
            status = event.get("status")
            if status:
                statuses.append(status)
    if expected_status not in statuses:
        failures.append(f"expected order status '{expected_status}', got {statuses}")


def _check_cart_quantity(failures: list[str], events: list[dict], expected: dict[str, int]) -> None:
    if not expected:
        return
    # 取最新一次的 cart_update / cart_snapshot
    latest_items: dict[str, int] = {}
    for event in events:
        if event.get("type") not in {"cart_update", "cart_snapshot"}:
            continue
        items = event.get("items") or event.get("cart", {}).get("items") or []
        if not isinstance(items, list):
            continue
        latest_items = {}
        for item in items:
            if isinstance(item, dict):
                pid = item.get("product_id") or ""
                qty = item.get("quantity") or 0
                if pid:
                    latest_items[pid] = int(qty)
    for product_id, expected_qty in expected.items():
        actual = latest_items.get(product_id, 0)
        if actual != expected_qty:
            failures.append(
                f"cart quantity for {product_id}: expected {expected_qty}, got {actual}"
            )


def _check_error_kind(
    failures: list[str],
    events: list[dict],
    explanation_text: str,
    expected_kind: str | None,
) -> None:
    if not expected_kind:
        return
    kind_markers = {
        "llm_timeout": ["生成详细解释暂时超时", "暂时超时"],
        "retrieval_error": ["检索服务暂时不稳定"],
        "stt_unavailable": ["语音识别服务不可用"],
        "websocket_closed": ["连接已断开", "websocket"],
    }
    markers = kind_markers.get(expected_kind, [])
    error_events = [event for event in events if event.get("type") == "error"]
    # 在 error 事件 message 和 text_delta 文本中都允许匹配
    haystack = explanation_text + " " + " ".join(
        (event.get("message") or "").lower() for event in error_events
    )
    hit = any(marker.lower() in haystack for marker in markers)
    if not hit:
        failures.append(f"expected error_kind '{expected_kind}' marker not found")


def _check_product_subset(failures: list[str], product_ids: list[str], whitelist: list[str]) -> None:
    if not whitelist:
        return
    allowed = set(whitelist)
    for pid in product_ids:
        if pid not in allowed:
            failures.append(f"product_id '{pid}' not in allowed whitelist {sorted(allowed)}")


def _check_explanation_forbidden_terms(
    failures: list[str],
    explanation_text: str,
    terms: list[str],
) -> None:
    if not terms:
        return
    for term in terms:
        if term.lower() in explanation_text:
            failures.append(f"forbidden term '{term}' found in explanation text")


def _check_focus_product(failures: list[str], events: list[dict], expected_focus: str | None) -> None:
    if not expected_focus:
        return
    focus_ids: list[str] = []
    for event in events:
        # focus 信息可能挂在 product_item.product 上，也可能挂在 followup_summary 事件
        if event.get("type") == "product_item":
            product = event.get("product")
            if isinstance(product, dict):
                pid = product.get("product_id")
                if pid:
                    focus_ids.append(pid)
        if event.get("type") == "followup_summary":
            pid = event.get("product_id")
            if pid:
                focus_ids.append(pid)
    if expected_focus not in focus_ids:
        failures.append(f"expected focus_product '{expected_focus}' not found in step events")


# ---------- IR 指标 ----------


def compute_ranking_metrics(
    predicted_ids: list[str],
    expected_ids: list[str],
    *,
    k_values: tuple[int, ...] = (5, 10),
) -> dict[str, float]:
    """计算 Recall@K 和 NDCG@K，仅当 expected_ids 非空时返回非零结果。

    expected_ids 是有顺序的"理想 top 列表"，靠前的 product_id 在 NDCG 中权重更大。
    """
    metrics: dict[str, float] = {}
    if not expected_ids:
        return metrics
    expected_set = set(expected_ids)
    for k in k_values:
        prefix = predicted_ids[:k]
        hit = sum(1 for pid in prefix if pid in expected_set)
        metrics[f"recall@{k}"] = hit / len(expected_set)
        metrics[f"ndcg@{k}"] = _ndcg_at_k(prefix, expected_ids, k)
    return metrics


def _ndcg_at_k(prediction: list[str], expected_ranked: list[str], k: int) -> float:
    import math

    rel_map = {pid: (len(expected_ranked) - idx) for idx, pid in enumerate(expected_ranked)}
    dcg = 0.0
    for idx, pid in enumerate(prediction[:k]):
        rel = rel_map.get(pid, 0)
        if rel <= 0:
            continue
        dcg += rel / math.log2(idx + 2)
    ideal_dcg = 0.0
    for idx, pid in enumerate(expected_ranked[:k]):
        rel = rel_map.get(pid, 0)
        ideal_dcg += rel / math.log2(idx + 2)
    if ideal_dcg == 0:
        return 0.0
    return dcg / ideal_dcg
