from fastapi.testclient import TestClient

from backend.app.cart import CartService
from backend.app.main import create_app
from backend.app.models import Product


def _product() -> Product:
    return Product(
        product_id="p1",
        title="Test Product",
        brand="BrandA",
        category="cat",
        sub_category="sub",
        price=100.0,
        image_path="img.jpg",
    )


def test_cart_add_idempotency_key_does_not_double_add():
    cart = CartService([_product()])

    first = cart.add("s1", "p1", 2, idempotency_key="idem-add-1")
    second = cart.add("s1", "p1", 2, idempotency_key="idem-add-1")

    assert first == second
    assert second["items"][0]["quantity"] == 2
    assert [entry["action"] for entry in cart.get_audit_log("s1")] == ["add"]


def test_cart_rejects_invalid_add_quantity():
    cart = CartService([_product()])

    try:
        cart.add("s1", "p1", 0)
    except ValueError as exc:
        assert "quantity" in str(exc)
    else:
        raise AssertionError("quantity=0 should be rejected for add")

    assert cart.get("s1")["items"] == []


def test_cart_rest_returns_400_for_invalid_quantity():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    product_id = client.get("/api/products?limit=1").json()["products"][0]["product_id"]

    response = client.post(
        "/api/cart/add",
        json={"session_id": "invalid_quantity", "product_id": product_id, "quantity": 0},
    )

    assert response.status_code == 400
    assert "quantity" in response.json()["detail"]


def test_order_initiate_rejects_empty_cart():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    session_id = "empty_order"
    client.post("/api/cart/clear", json={"session_id": session_id})

    response = client.post("/api/order/initiate", json={"session_id": session_id})

    assert response.status_code == 400
    assert response.json()["detail"]


def test_order_requires_confirmation_token_and_is_idempotent():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    session_id = "confirm_order"
    product_id = client.get("/api/products?limit=1").json()["products"][0]["product_id"]
    client.post("/api/cart/clear", json={"session_id": session_id})
    client.post(
        "/api/cart/add",
        json={"session_id": session_id, "product_id": product_id, "quantity": 1},
    )

    initiated = client.post("/api/order/initiate", json={"session_id": session_id}).json()
    assert initiated["status"] == "address_required"

    selected = client.post(
        "/api/order/select_address",
        json={"order_id": initiated["order_id"], "address_id": "addr_1"},
    ).json()
    assert selected["status"] == "awaiting_confirmation"
    token = selected["confirmation_token"]

    missing_token = client.post(
        "/api/order/confirm",
        json={"order_id": selected["order_id"], "idempotency_key": "confirm-1"},
    )
    assert missing_token.status_code == 400

    first = client.post(
        "/api/order/confirm",
        json={
            "order_id": selected["order_id"],
            "confirmation_token": token,
            "idempotency_key": "confirm-1",
        },
    )
    second = client.post(
        "/api/order/confirm",
        json={
            "order_id": selected["order_id"],
            "confirmation_token": token,
            "idempotency_key": "confirm-1",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["status"] == "completed"
    assert client.get(f"/api/cart?session_id={session_id}").json()["items"] == []


def test_order_persistence_stays_out_of_session_store_root(tmp_path):
    from backend.app.order_service import OrderService

    cart = CartService([_product()])
    cart.add("s1", "p1", 1)
    order_service = OrderService(cart, tmp_path)

    order_service.initiate_checkout("s1")

    assert (tmp_path / "orders" / "orders.json").exists()
    assert not (tmp_path / "orders.json").exists()
