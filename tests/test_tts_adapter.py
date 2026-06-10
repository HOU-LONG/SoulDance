import pytest
import respx
from httpx import Response

from backend.app.tts_adapter import TTSAdapter
from backend.app.config import Settings


@pytest.fixture
def adapter():
    settings = Settings(
        tts_enabled=True,
        tts_base_url="http://127.0.0.1:18880",
        tts_api_key="EMPTY",
        tts_model="qwen3-tts",
        tts_response_format="wav",
        tts_task_type="VoiceDesign",
        tts_default_voice="calm_female",
        tts_default_instructions="A calm, clear female narrator voice.",
        tts_timeout_seconds=30.0,
        tts_stream=False,
        tts_max_text_length=500,
        tts_chunk_duration_ms=200,
    )
    return TTSAdapter(settings)


@pytest.mark.asyncio
async def test_synthesize_events_returns_audio_deltas(adapter):
    fake_wav = b"RIFF" + b"\x00" * 100  # pseudo WAV header
    with respx.mock:
        route = respx.post("http://127.0.0.1:18880/v1/audio/speech").mock(
            return_value=Response(200, content=fake_wav)
        )
        events = await adapter.synthesize_events("你好", enabled=True)

    assert route.called
    audio_deltas = [e for e in events if e["type"] == "audio_delta"]
    assert len(audio_deltas) >= 1
    assert audio_deltas[0]["encoding"] == "wav"
    assert audio_deltas[0]["sample_rate"] == 24000
    assert events[-1]["type"] == "audio_done"


@pytest.mark.asyncio
async def test_synthesize_events_disabled_returns_empty(adapter):
    events = await adapter.synthesize_events("你好", enabled=False)
    assert events == []


@pytest.mark.asyncio
async def test_synthesize_events_respects_tts_enabled_setting():
    settings = Settings(tts_enabled=False)
    adapter = TTSAdapter(settings)
    events = await adapter.synthesize_events("你好", enabled=True)
    assert events == []
