from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from .metrics import evaluate_events
from .models import EvalReport, EvalScenario


def load_scenarios(path: str | Path) -> list[EvalScenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalScenario.model_validate(item) for item in data]


def run_scenarios(app: FastAPI, scenarios: list[EvalScenario]) -> EvalReport:
    client = TestClient(app)
    results = []
    for scenario in scenarios:
        if scenario.type == "user_message":
            events = _run_user_message(client, scenario)
            results.append(evaluate_events(scenario, events))
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
    return EvalReport(total=len(results), passed=passed, failed=len(results) - passed, results=results)


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
