import base64
import io
import json
import wave

import pytest
import respx
from httpx import Response

from backend.app.tts_adapter import TTSAdapter
from backend.app.tts_adapter import _decode_doubao_tts_chunks
from backend.app.tts_adapter import markdown_to_tts_text
from backend.app.config import Settings


def _wav_bytes(sample_rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x01" * 120)
    return buffer.getvalue()


def test_decode_doubao_tts_accepts_success_code_20000000():
    pcm = b"\x00\x01" * 8
    payload = {
        "code": 20000000,
        "message": "OK",
        "data": base64.b64encode(pcm).decode("ascii"),
    }

    assert _decode_doubao_tts_chunks([json.dumps(payload).encode("utf-8")]) == pcm


def test_markdown_to_tts_text_matches_rendered_plain_text():
    source = (
        "**结论：** 优先看「东鹏特饮」。\n\n"
        "**主推：** 类目精确匹配。\n"
        "- [查看商品](https://example.com)\n"
        "- `功能饮料`"
    )

    text = markdown_to_tts_text(source)

    assert text == "结论： 优先看「东鹏特饮」。\n\n主推： 类目精确匹配。\n查看商品\n功能饮料"
    assert "**" not in text
    assert "`" not in text
    assert "https://example.com" not in text


@pytest.mark.asyncio
async def test_synthesize_events_sends_plain_text_to_tts_provider(adapter):
    fake_wav = _wav_bytes()
    source = "**结论：** 优先看「东鹏特饮」。\n\n**主推：** 类目精确匹配。"
    with respx.mock:
        route = respx.post("http://127.0.0.1:18880/v1/audio/speech").mock(
            return_value=Response(200, content=fake_wav)
        )
        await adapter.synthesize_events(source, enabled=True)

    body = json.loads(route.calls.last.request.content)
    assert body["input"] == "结论： 优先看「东鹏特饮」。\n\n主推： 类目精确匹配。"
    assert "**" not in body["input"]


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
    fake_wav = _wav_bytes()
    with respx.mock:
        route = respx.post("http://127.0.0.1:18880/v1/audio/speech").mock(
            return_value=Response(200, content=fake_wav)
        )
        events = await adapter.synthesize_events("你好", enabled=True)

    assert route.called
    audio_deltas = [e for e in events if e["type"] == "audio_delta"]
    assert len(audio_deltas) >= 1
    assert audio_deltas[0]["encoding"] == "pcm_s16le"
    assert audio_deltas[0]["sample_rate"] == 24000
    assert audio_deltas[0]["data"]
    assert audio_deltas[0]["audio_base64"] == audio_deltas[0]["data"]
    assert events[-1]["type"] == "audio_done"


@pytest.mark.asyncio
async def test_synthesize_events_calls_mimo_chat_completions():
    fake_wav = _wav_bytes()
    encoded_wav = base64.b64encode(fake_wav).decode("ascii")
    settings = Settings(
        tts_enabled=True,
        tts_provider="mimo",
        tts_base_url="https://api.mimo.example/v1",
        tts_api_key="test-key",
        tts_model="mimo-v2.5-tts",
        tts_response_format="wav",
        tts_default_voice="default_zh",
    )
    adapter = TTSAdapter(settings)

    with respx.mock:
        route = respx.post("https://api.mimo.example/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "audio": {
                                    "data": encoded_wav,
                                    "format": "wav",
                                }
                            }
                        }
                    ]
                },
            )
        )
        events = await adapter.synthesize_events("你好", enabled=True, voice="default_zh")

    request = route.calls.last.request
    assert request.headers["api-key"] == "test-key"
    assert b'"voice":"default_zh"' in request.content
    assert b'"format":"wav"' in request.content
    audio_deltas = [e for e in events if e["type"] == "audio_delta"]
    assert audio_deltas[0]["encoding"] == "pcm_s16le"
    assert audio_deltas[0]["audio_base64"] == audio_deltas[0]["data"]


@pytest.mark.asyncio
async def test_synthesize_events_calls_doubao_chunked_v3():
    pcm = b"\x00\x01" * 120
    encoded_pcm = base64.b64encode(pcm).decode("ascii")
    settings = Settings(
        tts_enabled=True,
        tts_provider="doubao_chunked_v3",
        doubao_voice_api_key="test-key",
        doubao_tts_api_key="test-key",
        doubao_tts_url="https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        doubao_tts_resource_id="seed-tts-2.0",
        doubao_tts_model="seed-tts-2.0-standard",
        doubao_tts_speaker="zh_female_wenroushunv_uranus_bigtts",
        doubao_tts_format="pcm",
        doubao_tts_sample_rate=24000,
    )
    adapter = TTSAdapter(settings)

    with respx.mock:
        route = respx.post("https://openspeech.bytedance.com/api/v3/tts/unidirectional").mock(
            return_value=Response(
                200,
                content=(
                    json.dumps({"code": 0, "message": "ok", "data": encoded_pcm}) + "\n"
                ).encode("utf-8"),
            )
        )
        events = await adapter.synthesize_events("你好", enabled=True, voice="calm_female")

    request = route.calls.last.request
    assert request.headers["X-Api-Key"] == "test-key"
    assert request.headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    body = json.loads(request.content)
    assert body["req_params"]["text"] == "你好"
    assert body["req_params"]["model"] == "seed-tts-2.0-standard"
    assert body["req_params"]["speaker"] == "zh_female_wenroushunv_uranus_bigtts"
    assert body["req_params"]["audio_params"]["format"] == "pcm"
    audio_deltas = [e for e in events if e["type"] == "audio_delta"]
    assert audio_deltas[0]["encoding"] == "pcm_s16le"
    assert audio_deltas[0]["sample_rate"] == 24000
    assert base64.b64decode(audio_deltas[0]["data"]) == pcm
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
