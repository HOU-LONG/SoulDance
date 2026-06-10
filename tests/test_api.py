from fastapi.testclient import TestClient

from backend.app.agent import ShopGuideAgent
from backend.app.llm_client import FakeLLMClient
from backend.app.main import create_app


class SemanticCartLLM(FakeLLMClient):
    async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
        if "两件" not in message:
            return '{"intent": "recommend_product"}'
        return """
        {
          "intent": "cart_operation",
          "cart_operation": {
            "action": "add_to_cart",
            "quantity": 2,
            "target": {
              "reference": "last_recommendations",
              "selection_strategy": "primary"
            }
          }
        }
        """


class CountingSemanticLLM(FakeLLMClient):
    def __init__(self):
        self.parse_calls = 0

    async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
        self.parse_calls += 1
        return '{"intent": "recommend_product"}'


class CartCommandSemanticLLM(FakeLLMClient):
    def __init__(self):
        self.parse_calls = 0

    async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
        self.parse_calls += 1
        return '{"intent": "recommend_product"}'


def test_health_endpoint_reports_product_count():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["product_count"] == 100


def test_debug_plan_endpoint_uses_agent_schema():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    response = client.post(
        "/api/debug/retrieval_plan",
        json={"type": "user_message", "session_id": "demo", "message": "推荐一款适合油皮的洗面奶，预算100以内"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "recommend_product"
    assert body["hard_constraints"]["price_max"] == 100


def test_cart_rest_flow():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    product_id = client.get("/api/products").json()["products"][0]["product_id"]
    session_id = "demo_rest_flow"
    client.post("/api/cart/clear", json={"session_id": session_id})

    add_response = client.post(
        "/api/cart/add",
        json={"session_id": session_id, "product_id": product_id, "quantity": 1},
    )
    assert add_response.status_code == 200
    assert add_response.json()["success"] is True

    update_response = client.post(
        "/api/cart/update_quantity",
        json={"session_id": session_id, "product_id": product_id, "quantity": 2},
    )
    assert update_response.status_code == 200
    assert update_response.json()["success"] is True
    assert update_response.json()["items"][0]["quantity"] == 2

    checkout_response = client.post("/api/cart/checkout", json={"session_id": session_id})
    assert checkout_response.status_code == 200
    assert checkout_response.json()["success"] is True
    assert checkout_response.json()["status"] == "ok"
    assert checkout_response.json()["paid_amount"] > 0


def test_empty_cart_checkout_returns_clear_error():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    session_id = "demo_empty_checkout"
    client.post("/api/cart/clear", json={"session_id": session_id})

    checkout_response = client.post("/api/cart/checkout", json={"session_id": session_id})

    assert checkout_response.status_code == 400
    assert "购物车" in checkout_response.json()["detail"]


def test_websocket_recommendation_event_order_and_quick_actions():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_order",
                "message": "推荐防晒霜，但不要含酒精的，也不要日系品牌",
            }
        )
        events = []
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event["type"] == "done":
                break

    event_types = [event["type"] for event in events]
    assert event_types[0] == "assistant_state"
    assert events[0]["intent"] == "recommend_product"
    assert events[0]["retrieval_mode"] == "single"
    assert events[0]["llm_mode"] == "fake"
    selection_index = next(
        index
        for index, event in enumerate(events)
        if event.get("selection_mode") == "llm_selection" and "selected_count" in event
    )
    text_before_products = [
        event for event in events[: event_types.index("products_start")] if event["type"] == "text_delta"
    ]
    assert selection_index < event_types.index("products_start")
    assert text_before_products
    assert event_types.index("products_done") < event_types.index("quick_actions")


def test_websocket_chat_uses_agent_stream_message(monkeypatch):
    async def explode_handle_message(self, request):
        raise AssertionError("websocket should stream events instead of awaiting handle_message")

    async def fake_stream_message(self, request, compiled_ir=None):
        yield {"type": "assistant_state", "message_id": "assistant_test", "phase": "retrieving", "label": "streaming"}
        yield {"type": "done", "message_id": "assistant_test"}

    monkeypatch.setattr(ShopGuideAgent, "handle_message", explode_handle_message)
    monkeypatch.setattr(ShopGuideAgent, "stream_message", fake_stream_message, raising=False)
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_stream_method",
                "message": "推荐防晒霜",
            }
        )
        first_event = websocket.receive_json()
        done_event = websocket.receive_json()

    assert first_event["type"] == "assistant_state"
    assert done_event["type"] == "done"


def test_websocket_recommendation_uses_one_semantic_parse():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    llm = CountingSemanticLLM()
    app.state.agent.llm_client = llm
    app.state.agent.semantic_parser.llm_client = llm
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_single_parse",
                "message": "推荐防晒霜，但不要含酒精",
            }
        )
        while True:
            event = websocket.receive_json()
            if event["type"] == "done":
                break

    assert llm.parse_calls == 1


def test_websocket_natural_language_cart_action_uses_agent_context():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_cart",
                "message": "推荐适合油皮的洗面奶",
            }
        )
        primary_product_id = None
        while True:
            event = websocket.receive_json()
            if event["type"] == "product_item" and event["role"] == "primary":
                primary_product_id = event["product"]["product_id"]
            if event["type"] == "done":
                break

        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_cart",
                "message": "把刚才那款加到购物车",
            }
        )
        cart_event = websocket.receive_json()
        done_event = websocket.receive_json()

    assert cart_event["type"] == "cart_update"
    assert cart_event["action"] == "add_to_cart"
    assert cart_event["cart"]["items"][0]["product_id"] == primary_product_id
    assert done_event["type"] == "done"


def test_websocket_explicit_cart_action_updates_agent_cart_memory():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    product_id = client.get("/api/products").json()["products"][0]["product_id"]

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "cart_action",
                "session_id": "demo_ws_explicit_cart",
                "action": "add_to_cart",
                "product_id": product_id,
                "quantity": 1,
            }
        )
        cart_event = websocket.receive_json()
        done_event = websocket.receive_json()

    context = app.state.agent.sessions.get("demo_ws_explicit_cart")
    assert cart_event["type"] == "cart_update"
    assert cart_event["product_id"] == product_id
    assert context.state.cart_memory.recent_product_id == product_id
    assert context.recent_cart_product_id == product_id
    assert done_event["type"] == "done"


def test_websocket_cart_operation_can_be_detected_by_semantic_frame_without_keywords():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    app.state.agent.llm_client = SemanticCartLLM()
    app.state.agent.semantic_parser.llm_client = app.state.agent.llm_client
    client = TestClient(app)
    client.post("/api/cart/clear", json={"session_id": "demo_ws_semantic_cart"})

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_semantic_cart",
                "message": "推荐防晒霜",
            }
        )
        primary_product_id = None
        while True:
            event = websocket.receive_json()
            if event["type"] == "product_item" and event["role"] == "primary":
                primary_product_id = event["product"]["product_id"]
            if event["type"] == "done":
                break

        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_semantic_cart",
                "message": "就这个来两件",
            }
        )
        cart_event = websocket.receive_json()
        done_event = websocket.receive_json()

    assert cart_event["type"] == "cart_update"
    assert cart_event["action"] == "add_to_cart"
    assert cart_event["product_id"] == primary_product_id
    assert cart_event["cart"]["items"][0]["quantity"] == 2
    assert done_event["type"] == "done"


def test_websocket_oral_cart_followup_is_rule_guarded_after_recommendation():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    client.post("/api/cart/clear", json={"session_id": "demo_ws_oral_cart"})

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_oral_cart",
                "message": "推荐一款手机，预算4000，拍照优先",
            }
        )
        primary_product_id = None
        while True:
            event = websocket.receive_json()
            if event["type"] == "product_item" and event["role"] == "primary":
                primary_product_id = event["product"]["product_id"]
            if event["type"] == "done":
                break

        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_oral_cart",
                "message": "要这个",
            }
        )
        cart_event = websocket.receive_json()
        done_event = websocket.receive_json()

    assert cart_event["type"] == "cart_update"
    assert cart_event["action"] == "add_to_cart"
    assert cart_event["product_id"] == primary_product_id
    assert cart_event["cart"]["items"][0]["quantity"] == 1
    assert done_event["type"] == "done"


def test_websocket_oral_cart_followup_without_recommendation_does_not_add_random_product():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_oral_cart_no_context",
                "message": "就这个来两件",
            }
        )
        cart_event = websocket.receive_json()
        done_event = websocket.receive_json()

    assert cart_event["type"] == "cart_update"
    assert cart_event["action"] == "get_cart"
    assert cart_event["product_id"] is None
    assert cart_event["cart"]["items"] == []
    assert done_event["type"] == "done"


def test_websocket_named_product_cart_command_adds_nestle_coffee():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    session_id = "demo_ws_named_cart_nestle"
    client.post("/api/cart/clear", json={"session_id": session_id})

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": session_id,
                "message": "将两份雀巢咖啡加入购物车",
            }
        )
        cart_event = websocket.receive_json()
        done_event = websocket.receive_json()

    assert cart_event["type"] == "cart_update"
    assert cart_event["action"] == "add_to_cart"
    assert cart_event["product_id"] == "p_food_002"
    assert cart_event["cart"]["items"][0]["quantity"] == 2
    assert "雀巢" in cart_event["cart"]["items"][0]["name"]
    assert "雀巢咖啡" in cart_event["message"]
    assert "p_food_002" not in cart_event["message"]
    assert done_event["type"] == "done"


def test_websocket_rule_cart_command_skips_semantic_llm_parse():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    llm = CartCommandSemanticLLM()
    app.state.agent.llm_client = llm
    app.state.agent.semantic_parser.llm_client = llm
    client = TestClient(app)
    session_id = "demo_ws_cart_fast_path"
    client.post("/api/cart/clear", json={"session_id": session_id})

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": session_id,
                "message": "把雀巢咖啡加入购物车",
            }
        )
        cart_event = websocket.receive_json()
        done_event = websocket.receive_json()

    assert cart_event["type"] == "cart_update"
    assert cart_event["action"] == "add_to_cart"
    assert cart_event["product_id"] == "p_food_002"
    assert done_event["type"] == "done"
    assert llm.parse_calls == 0


def test_websocket_natural_language_clear_cart_empties_same_session_cart():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    session_id = "demo_ws_clear_cart"
    product_id = client.get("/api/products").json()["products"][0]["product_id"]
    client.post(
        "/api/cart/add",
        json={"session_id": session_id, "product_id": product_id, "quantity": 2},
    )

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": session_id,
                "message": "清空购物车",
            }
        )
        cart_event = websocket.receive_json()
        done_event = websocket.receive_json()

    assert cart_event["type"] == "cart_update"
    assert cart_event["action"] == "clear_cart"
    assert cart_event["product_id"] is None
    assert cart_event["cart"]["items"] == []
    assert "清空" in cart_event["message"]
    assert done_event["type"] == "done"
    assert client.get(f"/api/cart?session_id={session_id}").json()["items"] == []


def test_product_image_asset_url_is_served_by_backend():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    product = client.get("/api/products?limit=1").json()["products"][0]
    image_url = product["main_image_url"]
    response = client.get(image_url)

    assert image_url.startswith("/assets/products/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    assert response.content


def test_product_image_url_ignores_private_server_base_url(monkeypatch):
    from backend.app.config import get_settings
    from backend.app.image_assets import _get_base_url, product_image_url_auto

    monkeypatch.setenv("SERVER_BASE_URL", "http://192.168.3.116:8000")
    get_settings.cache_clear()
    _get_base_url.cache_clear()
    try:
        image_url = product_image_url_auto("demo/images/product.jpg")
        assert image_url.startswith("/assets/products/")
        assert "192.168." not in image_url
    finally:
        get_settings.cache_clear()
        _get_base_url.cache_clear()
