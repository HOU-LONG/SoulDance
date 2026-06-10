import io

import pytest
from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.main import create_app
from backend.app.stt_adapter import STTAdapter


@pytest.fixture
def client(monkeypatch):
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    return TestClient(app)


def test_stt_endpoint_returns_text(client, monkeypatch):
    async def fake_transcribe(*args, **kwargs):
        return {"text": "推荐防晒霜", "is_final": True, "confidence": 0.95}

    monkeypatch.setattr(STTAdapter, "transcribe", fake_transcribe)

    audio = io.BytesIO(b"RIFF" + b"\x00" * 1000)
    resp = client.post(
        "/api/stt",
        files={"audio": ("test.wav", audio, "audio/wav")},
        data={"session_id": "s1", "audio_format": "wav"},
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "推荐防晒霜"


def test_stt_endpoint_returns_empty_text_clearly(client, monkeypatch):
    async def fake_transcribe(*args, **kwargs):
        return {"text": "", "is_final": True, "confidence": 0.0}

    monkeypatch.setattr(STTAdapter, "transcribe", fake_transcribe)

    audio = io.BytesIO(b"RIFF" + b"\x00" * 1000)
    resp = client.post(
        "/api/stt",
        files={"audio": ("test.wav", audio, "audio/wav")},
        data={"session_id": "s1", "audio_format": "wav"},
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == ""
    assert resp.json()["is_final"] is True


def test_stt_endpoint_returns_provider_runtime_error(client, monkeypatch):
    async def fake_transcribe(*args, **kwargs):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr(STTAdapter, "transcribe", fake_transcribe)

    audio = io.BytesIO(b"RIFF" + b"\x00" * 1000)
    resp = client.post(
        "/api/stt",
        files={"audio": ("test.wav", audio, "audio/wav")},
        data={"session_id": "s1", "audio_format": "wav"},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "provider timeout"


def test_stt_endpoint_returns_disabled_error(monkeypatch):
    monkeypatch.setenv("STT_ENABLED", "false")
    get_settings.cache_clear()
    try:
        app = create_app(use_fake_llm=True, use_fake_retriever=True)
        client = TestClient(app)
        audio = io.BytesIO(b"RIFF" + b"\x00" * 1000)

        resp = client.post(
            "/api/stt",
            files={"audio": ("test.wav", audio, "audio/wav")},
        )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "STT is disabled"
    finally:
        get_settings.cache_clear()


def test_stt_endpoint_rejects_oversized_audio(client):
    big = io.BytesIO(b"\x00" * (15 * 1024 * 1024))
    resp = client.post(
        "/api/stt",
        files={"audio": ("big.wav", big, "audio/wav")},
    )
    assert resp.status_code == 413
