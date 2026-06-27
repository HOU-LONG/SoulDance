from __future__ import annotations

import os

# Disable network-dependent rerankers before importing the app, since main.py
# builds the app (and the reranker) at import time.
os.environ["RERANK_ENABLED"] = "false"
os.environ["RERANK_LLM_ENABLED"] = "false"

from fastapi.testclient import TestClient

from backend.app.main import create_app


PRODUCT_TITLE_SNIPPET = "李宁 韦德之道 全城12"


def _app():
    return TestClient(create_app(use_fake_llm=True, use_fake_retriever=True))


def test_product_analysis_in_catalog():
    client = _app()
    # Mention a real product title; this should be resolved and analyzed.
    resp = client.post("/api/chat", json={
        "type": "user_message",
        "session_id": "analysis_test",
        "message": f"{PRODUCT_TITLE_SNIPPET} 性价比怎么样",
    }, headers={"X-User-Id": "demo_user_a"})
    assert resp.status_code == 200
    events = resp.json()
    texts = "".join(e.get("text", "") for e in events if e.get("type") in {"text_delta", "focus_text_delta"})
    # A real analysis should mention the product title or brand.
    assert "李宁" in texts or PRODUCT_TITLE_SNIPPET in texts


def test_product_analysis_unknown_product_no_fake_card():
    client = _app()
    resp = client.post("/api/chat", json={
        "type": "user_message",
        "session_id": "analysis_unknown",
        "message": "小米17max 性价比",
    }, headers={"X-User-Id": "demo_user_a"})
    assert resp.status_code == 200
    events = resp.json()
    assert not any(e.get("type") == "product_item" for e in events)
    texts = "".join(e.get("text", "") for e in events if e.get("type") in {"text_delta", "focus_text_delta"})
    assert "没有" in texts or "商品库" in texts
