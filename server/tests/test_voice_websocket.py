import io

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.stt_adapter import STTAdapter
from backend.app.tts_adapter import TTSAdapter


@pytest.fixture
def client():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    return TestClient(app)


@pytest.mark.asyncio
async def test_voice_input_flow(client, monkeypatch):
    async def fake_stt(*args, **kwargs):
        return {"text": "推荐防晒霜", "is_final": True, "confidence": 0.95}

    async def fake_tts(*args, **kwargs):
        if kwargs.get("enabled"):
            return [
                {"type": "audio_delta", "message_id": "msg_1", "data": "ZmFrZQ==", "encoding": "wav"},
                {"type": "audio_done", "message_id": "msg_1"},
            ]
        return []

    monkeypatch.setattr(STTAdapter, "transcribe", fake_stt)
    monkeypatch.setattr(TTSAdapter, "synthesize_events", fake_tts)

    # STT endpoint
    audio = io.BytesIO(b"RIFF" + b"\x00" * 100)
    resp = client.post(
        "/api/stt",
        files={"audio": ("a.wav", audio, "audio/wav")},
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "推荐防晒霜"

    # WS chat with voice + TTS enabled
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({
            "type": "user_message",
            "session_id": "voice_session_1",
            "message": "推荐防晒霜",
            "input_type": "voice",
            "tts_enabled": True,
            "voice": "calm_female",
        })
        events = []
        for _ in range(50):
            evt = ws.receive_json()
            events.append(evt)
            # audio events are emitted after `done`; keep reading until audio_done.
            if evt.get("type") == "audio_done":
                break

        types = [e["type"] for e in events]
        assert "audio_delta" in types, f"audio_delta not in events: {types}"
        assert "audio_done" in types, f"audio_done not in events: {types}"


def test_chat_request_rejects_invalid_input_type(client):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({
            "type": "user_message",
            "session_id": "voice_session_2",
            "message": "hello",
            "input_type": "invalid",
        })
        evt = ws.receive_json()
        assert evt["type"] == "error"
