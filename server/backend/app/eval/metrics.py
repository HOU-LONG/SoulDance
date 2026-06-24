from __future__ import annotations

from .models import EvalScenario, EvalScenarioResult


def evaluate_events(scenario: EvalScenario, events: list[dict]) -> EvalScenarioResult:
    failures: list[str] = []
    event_types = [event.get("type") for event in events]
    product_events = [event for event in events if event.get("type") == "product_item"]
    product_ids = [
        event.get("product", {}).get("product_id", "")
        for event in product_events
        if isinstance(event.get("product"), dict)
    ]
    if len(product_events) < scenario.expect.min_product_items:
        failures.append(f"expected at least {scenario.expect.min_product_items} product_item events")
    for required in scenario.expect.event_types:
        if required not in event_types:
            failures.append(f"missing event type: {required}")
    for expected_product_id in scenario.expect.expected_product_ids:
        if expected_product_id not in product_ids:
            failures.append(f"missing expected product: {expected_product_id}")
    for forbidden_product_id in scenario.expect.forbidden_product_ids:
        if forbidden_product_id in product_ids:
            failures.append(f"forbidden product returned: {forbidden_product_id}")
    for product_event in product_events:
        product = product_event.get("product", {})
        if not isinstance(product, dict):
            continue
        product_name = product.get("name", "")
        product_description = product.get("description", "")
        product_text = f"{product_name} {product_description}".lower()
        for term in scenario.expect.forbid_terms:
            if term.lower() in product_text:
                failures.append(f"forbidden term '{term}' found in product: {product_name}")
                break
        price = product.get("price")
        if scenario.expect.price_max is not None and price is not None:
            if price > scenario.expect.price_max:
                failures.append(
                    f"product {product_name} price {price} exceeds max {scenario.expect.price_max}"
                )
        if scenario.expect.price_min is not None and price is not None:
            if price < scenario.expect.price_min:
                failures.append(
                    f"product {product_name} price {price} below min {scenario.expect.price_min}"
                )
    if scenario.expect.expect_clarification:
        if "clarification_request" not in event_types:
            failures.append("expected clarification_request event")
    if scenario.expect.expect_product_ids_subset_of and product_ids:
        allowed = set(scenario.expect.expect_product_ids_subset_of)
        for product_id in product_ids:
            if product_id not in allowed:
                failures.append(f"product {product_id} outside expected subset")
    if scenario.expect.expected_brands or scenario.expect.forbidden_brands:
        returned_brands = [
            str(event.get("product", {}).get("brand", ""))
            for event in product_events
            if isinstance(event.get("product"), dict)
        ]
        returned_lower = [brand.lower() for brand in returned_brands if brand]
        for expected_brand in scenario.expect.expected_brands:
            if not any(expected_brand.lower() in brand for brand in returned_lower):
                failures.append(f"missing expected brand: {expected_brand}")
        for forbidden_brand in scenario.expect.forbidden_brands:
            if any(forbidden_brand.lower() in brand or brand in forbidden_brand.lower() for brand in returned_lower):
                failures.append(f"forbidden brand returned: {forbidden_brand}")

    if scenario.expect.require_cart_success:
        cart_events = [event for event in events if event.get("type") == "cart_update"]
        if not cart_events:
            failures.append("missing cart_update event for require_cart_success")
        else:
            for cart_event in cart_events:
                success = cart_event.get("success", False)
                if not success:
                    failures.append("cart_update event reported failure")
                    break
    if scenario.expect.require_order_completed:
        order_events = [event for event in events if event.get("type") == "order_flow"]
        if not order_events:
            failures.append("missing order_flow event for require_order_completed")
        else:
            for order_event in order_events:
                if order_event.get("status") != "completed":
                    failures.append("order_flow event reported incomplete")
                    break
    return EvalScenarioResult(
        id=scenario.id,
        passed=not failures,
        failures=failures,
        event_count=len(events),
        product_ids=product_ids,
    )
