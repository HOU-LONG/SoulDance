import pytest

from backend.app.main import create_app
from fastapi.testclient import TestClient


def test_stream_message_records_display_messages():
    client = TestClient(create_app(use_fake_llm=True, use_fake_retriever=True))
    resp = client.post("/api/chat", json={
        "type": "user_message",
        "session_id": "display_test",
        "message": "推荐手机",
    }, headers={"X-User-Id": "demo_user_a"})
    assert resp.status_code == 200
    ctx_resp = client.get("/api/debug/session", params={"session_id": "display_test"}, headers={"X-User-Id": "demo_user_a"})
    ctx = ctx_resp.json()
    assert len(ctx["display_messages"]) >= 2
    assert ctx["display_messages"][0]["role"] == "user"
    assert ctx["display_messages"][0]["text"] == "推荐手机"
    assistant_msgs = [m for m in ctx["display_messages"] if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
