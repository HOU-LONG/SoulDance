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
    return EvalScenarioResult(
        id=scenario.id,
        passed=not failures,
        failures=failures,
        event_count=len(events),
        product_ids=product_ids,
    )
