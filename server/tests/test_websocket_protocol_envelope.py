from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_websocket_sends_ack_before_stream_events_with_trace_and_seq():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_envelope",
                "message": "推荐防晒霜",
            }
        )
        ack = websocket.receive_json()
        first = websocket.receive_json()

    assert ack["type"] == "ack"
    assert ack["seq"] == 0
    assert first["seq"] == 1
    assert first["trace_id"] == ack["trace_id"]
    assert first["session_id"] == "demo_ws_envelope"
