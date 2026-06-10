import gzip
import io
import json
import struct
import wave

import pytest

from backend.app.config import Settings
from backend.app.stt_adapter import (
    STTAdapter,
    _ASR_AUDIO_ONLY_REQUEST,
    _ASR_COMPRESSION_GZIP,
    _ASR_FLAG_LAST_NO_SEQUENCE,
    _ASR_FLAG_LAST_WITH_SEQUENCE,
    _ASR_FLAG_NONE,
    _ASR_FULL_CLIENT_REQUEST,
    _ASR_FULL_SERVER_RESPONSE,
    _ASR_SERIALIZATION_JSON,
    _ASR_SERIALIZATION_NONE,
    _build_doubao_asr_frame,
    _extract_doubao_asr_text,
    _parse_doubao_asr_message,
)


def _wav_bytes(sample_rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x01" * 80)
    return buffer.getvalue()


def test_doubao_asr_builds_full_client_request_frame():
    frame = _build_doubao_asr_frame(
        _ASR_FULL_CLIENT_REQUEST,
        0,
        _ASR_SERIALIZATION_JSON,
        _ASR_COMPRESSION_GZIP,
        b'{"audio":{"format":"pcm"}}',
    )

    assert frame[:4] == bytes([0x11, 0x10, 0x11, 0x00])
    payload_size = struct.unpack(">I", frame[4:8])[0]
    assert payload_size == len(frame[8:])
    assert json.loads(gzip.decompress(frame[8:]))["audio"]["format"] == "pcm"


def test_doubao_asr_builds_final_audio_frame():
    frame = _build_doubao_asr_frame(
        _ASR_AUDIO_ONLY_REQUEST,
        _ASR_FLAG_LAST_NO_SEQUENCE,
        _ASR_SERIALIZATION_NONE,
        _ASR_COMPRESSION_GZIP,
        b"pcm-bytes",
    )

    assert frame[:4] == bytes([0x11, 0x22, 0x01, 0x00])
    assert gzip.decompress(frame[8:]) == b"pcm-bytes"


def test_doubao_asr_parses_final_server_response():
    payload = gzip.compress(
        json.dumps({"result": {"text": "推荐防晒霜"}}, ensure_ascii=False).encode("utf-8")
    )
    frame = (
        bytes([0x11, (_ASR_FULL_SERVER_RESPONSE << 4) | _ASR_FLAG_LAST_WITH_SEQUENCE, 0x11, 0x00])
        + struct.pack(">i", -1)
        + struct.pack(">I", len(payload))
        + payload
    )

    parsed = _parse_doubao_asr_message(frame)

    assert parsed["is_final"] is True
    assert parsed["sequence"] == -1
    assert _extract_doubao_asr_text(parsed["payload"]) == "推荐防晒霜"


def test_doubao_asr_parses_server_response_without_sequence():
    payload = json.dumps(
        {"result": {"additions": {"log_id": "test-logid"}}},
        ensure_ascii=False,
    ).encode("utf-8")
    frame = (
        bytes([0x11, (_ASR_FULL_SERVER_RESPONSE << 4) | _ASR_FLAG_NONE, 0x10, 0x00])
        + struct.pack(">I", len(payload))
        + payload
    )

    parsed = _parse_doubao_asr_message(frame)

    assert parsed["is_final"] is False
    assert parsed["sequence"] is None
    assert parsed["payload"]["result"]["additions"]["log_id"] == "test-logid"


def test_doubao_asr_prepare_wav_as_pcm():
    settings = Settings(stt_provider="doubao_ws", doubao_asr_api_key="test-key")
    adapter = STTAdapter(settings)

    pcm, audio_format, sample_rate, channels = adapter._prepare_doubao_audio(_wav_bytes(), "wav")

    assert audio_format == "pcm"
    assert sample_rate == 16000
    assert channels == 1
    assert pcm == b"\x00\x01" * 80


@pytest.mark.asyncio
async def test_transcribe_dispatches_to_doubao_ws(monkeypatch):
    settings = Settings(stt_provider="doubao_ws", doubao_asr_api_key="test-key")
    adapter = STTAdapter(settings)

    async def fake_doubao(audio_bytes, audio_format):
        return {"text": "推荐防晒霜", "is_final": True, "confidence": None}

    monkeypatch.setattr(adapter, "_transcribe_doubao_ws", fake_doubao)

    result = await adapter.transcribe(b"audio", "wav")

    assert result["text"] == "推荐防晒霜"
