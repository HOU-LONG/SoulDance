"""GET /api/sessions/latest returns the user's most recent session id."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_latest_session_returns_new_id_for_unknown_user():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    response = client.get("/api/sessions/latest", headers={"X-User-Id": "demo_user_a"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


def test_latest_session_returns_different_ids_per_user():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)
    # Drive at least one chat turn for each user so each has a session row.
    client.post(
        "/api/chat",
        headers={"X-User-Id": "demo_user_a"},
        json={"type": "user_message", "session_id": "s_a", "message": "hi"},
    )
    client.post(
        "/api/chat",
        headers={"X-User-Id": "demo_user_b"},
        json={"type": "user_message", "session_id": "s_b", "message": "hi"},
    )
    a = client.get("/api/sessions/latest", headers={"X-User-Id": "demo_user_a"}).json()
    b = client.get("/api/sessions/latest", headers={"X-User-Id": "demo_user_b"}).json()
    assert a["session_id"] == "s_a"
    assert b["session_id"] == "s_b"
