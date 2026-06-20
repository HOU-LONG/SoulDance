from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.observability import InMemoryMetrics


def test_in_memory_metrics_counts_and_snapshot_are_copy_safe():
    metrics = InMemoryMetrics()
    metrics.increment("ws.messages.received")
    snapshot = metrics.snapshot()
    snapshot["counters"]["ws.messages.received"] = 999

    assert metrics.snapshot()["counters"]["ws.messages.received"] == 1


def test_health_includes_observability_section():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    body = client.get("/health").json()

    assert "observability" in body
    assert "counters" in body["observability"]
