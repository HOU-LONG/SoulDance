"""Tests for session REST API endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _app():
    return TestClient(create_app(use_fake_llm=True, use_fake_retriever=True))


def test_get_sessions_allows_anonymous_user():
    client = _app()
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []


def test_sessions_crud_isolated_by_user():
    client = _app()
    # user a creates session
    client.get("/api/sessions/latest", headers={"X-User-Id": "demo_user_a"})
    client.post("/api/chat", json={
        "type": "user_message",
        "session_id": "demo_user_a_session_default",
        "message": "hello",
    }, headers={"X-User-Id": "demo_user_a"})

    # user b should not see a's session
    resp = client.get("/api/sessions", headers={"X-User-Id": "demo_user_b"})
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []

    # user a sees one
    resp = client.get("/api/sessions", headers={"X-User-Id": "demo_user_a"})
    assert len(resp.json()["sessions"]) == 1
    sid = resp.json()["sessions"][0]["session_id"]

    # load detail
    resp = client.get(f"/api/sessions/{sid}", headers={"X-User-Id": "demo_user_a"})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == sid

    # delete
    resp = client.delete(f"/api/sessions/{sid}", headers={"X-User-Id": "demo_user_a"})
    assert resp.status_code == 204

    resp = client.get("/api/sessions", headers={"X-User-Id": "demo_user_a"})
    assert resp.json()["sessions"] == []
