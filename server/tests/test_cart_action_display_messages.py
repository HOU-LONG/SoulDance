import os

# Disable network-dependent rerankers before importing the app, since main.py
# builds the app (and the reranker) at import time.
os.environ["RERANK_ENABLED"] = "false"
os.environ["RERANK_LLM_ENABLED"] = "false"

from fastapi.testclient import TestClient
from backend.app.main import create_app


PRODUCT_ID = "p_clothes_013"


def test_cart_action_records_display_message():
    client = TestClient(create_app(use_fake_llm=True, use_fake_retriever=True))
    with client.websocket_connect("/ws/chat", headers={"X-User-Id": "demo_user_a"}) as ws:
        ws.send_json({"type": "cart_action", "session_id": "cart_display_test", "action": "add_to_cart", "product_id": PRODUCT_ID, "quantity": 1})
        events = []
        while True:
            evt = ws.receive_json()
            events.append(evt)
            if evt.get("type") == "done":
                break

    ctx = client.get("/api/debug/session", params={"session_id": "cart_display_test"}, headers={"X-User-Id": "demo_user_a"}).json()
    assert len(ctx["display_messages"]) >= 1
    assert ctx["display_messages"][0]["role"] == "system"
    assert "购物车操作" in ctx["display_messages"][0]["text"] or "add_to_cart" in ctx["display_messages"][0]["text"]
