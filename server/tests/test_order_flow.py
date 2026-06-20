from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_order_initiate_rejects_empty_cart():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    session_id = "order_flow_empty"
    client.post("/api/cart/clear", json={"session_id": session_id})

    response = client.post("/api/order/initiate", json={"session_id": session_id})

    assert response.status_code == 400
    assert "购物车" in response.json()["detail"]


def test_order_happy_path_and_idempotent_confirm():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    session_id = "order_flow_happy"
    product_id = client.get("/api/products").json()["products"][0]["product_id"]
    client.post("/api/cart/clear", json={"session_id": session_id})
    client.post(
        "/api/cart/add",
        json={"session_id": session_id, "product_id": product_id, "quantity": 2},
    )

    initiated = client.post("/api/order/initiate", json={"session_id": session_id})
    assert initiated.status_code == 200
    order_id = initiated.json()["order_id"]
    assert initiated.json()["status"] == "address_required"
    assert initiated.json()["total_amount"] > 0

    addresses = client.get("/api/order/addresses")
    assert addresses.status_code == 200
    address_id = addresses.json()["addresses"][0]["address_id"]

    selected = client.post(
        "/api/order/select_address",
        json={"order_id": order_id, "address_id": address_id},
    )
    assert selected.status_code == 200
    token = selected.json()["confirmation_token"]
    assert selected.json()["status"] == "awaiting_confirmation"
    assert token

    wrong_token = client.post(
        "/api/order/confirm",
        json={
            "order_id": order_id,
            "confirmation_token": "wrong-token",
            "idempotency_key": "confirm_wrong",
        },
    )
    assert wrong_token.status_code == 400

    confirm_payload = {
        "order_id": order_id,
        "confirmation_token": token,
        "idempotency_key": "confirm_once",
    }
    confirmed = client.post("/api/order/confirm", json=confirm_payload)
    repeated = client.post("/api/order/confirm", json=confirm_payload)

    assert confirmed.status_code == 200
    assert repeated.status_code == 200
    assert confirmed.json()["status"] == "completed"
    assert repeated.json()["status"] == "completed"
    assert repeated.json()["order_id"] == confirmed.json()["order_id"]
