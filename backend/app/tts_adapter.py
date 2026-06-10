from __future__ import annotations

import base64
import io
import json
import logging
import uuid
import wave

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class TTSAdapter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or _default_settings()
        self.client = httpx.AsyncClient(timeout=self.settings.tts_timeout_seconds)

    async def synthesize_events(
        self,
        text: str,
        enabled: bool = False,
        voice: str | None = None,
        message_id: str = "",
    ) -> list[dict]:
        if not enabled or not text.strip():
            return []
        if not self.settings.tts_enabled:
            return []

        text = text[: self.settings.tts_max_text_length]
        provider = self.settings.tts_provider.lower()

        try:
            if provider in {"mimo", "xiaomi_mimo"}:
                audio_bytes, response_format = await self._request_mimo_audio(text, voice)
            elif provider in {"doubao_chunked_v3", "doubao_tts", "volc_tts"}:
                audio_bytes, response_format = await self._request_doubao_chunked_audio(text, voice)
            else:
                audio_bytes = await self._request_openai_audio(text, voice)
                response_format = self.settings.tts_response_format
        except Exception as exc:
            logger.warning("TTS request failed: %s", exc)
            return [
                {
                    "type": "audio_error",
                    "message_id": message_id,
                    "message": "语音合成失败",
                }
            ]

        events: list[dict] = []
        audio_payload = self._android_audio_payload(audio_bytes, response_format)
        audio_data = audio_payload["data"]
        if not audio_data:
            return events

        chunk_size = self._chunk_size_for(audio_data, audio_payload["sample_rate"])
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i : i + chunk_size]
            encoded = base64.b64encode(chunk).decode("ascii")
            events.append({
                "type": "audio_delta",
                "message_id": message_id,
                "encoding": audio_payload["encoding"],
                "sample_rate": audio_payload["sample_rate"],
                "channels": audio_payload["channels"],
                "data": encoded,
                "audio_base64": encoded,
                "is_last": False,
            })

        events.append({
            "type": "audio_done",
            "message_id": message_id,
        })
        return events

    async def _request_openai_audio(self, text: str, voice: str | None) -> bytes:
        instructions = self.settings.voice_preset.get(
            voice or self.settings.tts_default_voice,
            self.settings.tts_default_instructions,
        )
        payload = {
            "model": self.settings.tts_model,
            "input": text,
            "task_type": self.settings.tts_task_type,
            "instructions": instructions,
            "response_format": self.settings.tts_response_format,
            "stream": self.settings.tts_stream,
        }
        resp = await self.client.post(
            f"{self.settings.tts_base_url.rstrip('/')}/v1/audio/speech",
            json=payload,
            headers={"Authorization": f"Bearer {self.settings.tts_api_key}"},
        )
        resp.raise_for_status()
        return resp.content

    async def _request_mimo_audio(self, text: str, voice: str | None) -> tuple[bytes, str]:
        payload = {
            "model": self.settings.tts_model,
            "messages": [
                {
                    "role": "user",
                    "content": text,
                }
            ],
            "audio": {
                "voice": voice or self.settings.tts_default_voice,
                "format": self.settings.tts_response_format,
            },
        }
        resp = await self.client.post(
            f"{self.settings.tts_base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={"api-key": self.settings.tts_api_key},
        )
        resp.raise_for_status()
        payload = resp.json()
        audio = payload.get("choices", [{}])[0].get("message", {}).get("audio", {})
        encoded = audio.get("data") or audio.get("audio_base64")
        if not encoded:
            raise RuntimeError("MiMo TTS response did not include audio.data")
        return base64.b64decode(encoded), audio.get("format") or self.settings.tts_response_format

    async def _request_doubao_chunked_audio(self, text: str, voice: str | None) -> tuple[bytes, str]:
        if not self.settings.doubao_tts_api_key:
            raise RuntimeError("Doubao TTS API key is not configured")

        speaker = self._doubao_speaker(voice)
        audio_format = self.settings.doubao_tts_format.lower()
        payload = {
            "req_params": {
                "text": text,
                "model": self.settings.doubao_tts_model,
                "speaker": speaker,
                "audio_params": {
                    "format": audio_format,
                    "sample_rate": self.settings.doubao_tts_sample_rate,
                    "speech_rate": self.settings.doubao_tts_speech_rate,
                    "loudness_rate": self.settings.doubao_tts_loudness_rate,
                },
            }
        }
        headers = {
            "X-Api-Key": self.settings.doubao_tts_api_key,
            "X-Api-Resource-Id": self.settings.doubao_tts_resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }
        chunks: list[bytes] = []
        async with self.client.stream(
            "POST",
            self.settings.doubao_tts_url,
            json=payload,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                if chunk:
                    chunks.append(chunk)
        return _decode_doubao_tts_chunks(chunks), audio_format

    def _doubao_speaker(self, voice: str | None) -> str:
        if voice and voice not in self.settings.voice_preset:
            return voice
        return self.settings.doubao_tts_speaker

    def _android_audio_payload(self, audio_bytes: bytes, response_format: str) -> dict:
        sample_rate = self.settings.doubao_tts_sample_rate or 24000
        channels = 1
        encoding = response_format
        data = audio_bytes

        normalized_format = response_format.lower()
        if normalized_format in {"pcm", "pcm_s16le", "raw"}:
            return {
                "data": data,
                "encoding": "pcm_s16le",
                "sample_rate": sample_rate,
                "channels": channels,
            }

        if normalized_format != "wav":
            return {
                "data": data,
                "encoding": encoding,
                "sample_rate": sample_rate,
                "channels": channels,
            }

        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
                sample_width = wav.getsampwidth()
                sample_rate = wav.getframerate()
                channels = wav.getnchannels()
                data = wav.readframes(wav.getnframes())
        except (EOFError, wave.Error):
            logger.warning("TTS response_format=wav but response is not a readable WAV payload")
            return {
                "data": audio_bytes,
                "encoding": "wav",
                "sample_rate": sample_rate,
                "channels": channels,
            }

        if sample_width != 2:
            logger.warning("Unsupported TTS WAV sample width for AudioTrack PCM: %s", sample_width)
            return {
                "data": audio_bytes,
                "encoding": "wav",
                "sample_rate": sample_rate,
                "channels": channels,
            }

        return {
            "data": data,
            "encoding": "pcm_s16le",
            "sample_rate": sample_rate,
            "channels": channels,
        }

    def _chunk_size_for(self, audio_bytes: bytes, sample_rate: int = 24000) -> int:
        bytes_per_second = sample_rate * 2 * 1
        return max(
            1024,
            int(bytes_per_second * self.settings.tts_chunk_duration_ms / 1000),
        )


def _default_settings() -> Settings:
    from .config import get_settings

    return get_settings()


def _decode_doubao_tts_chunks(chunks: list[bytes]) -> bytes:
    body = b"".join(chunks)
    if not body:
        return b""

    text = body.decode("utf-8", errors="ignore").strip()
    json_objects = _parse_doubao_json_objects(text)
    if not json_objects:
        return body

    audio_parts: list[bytes] = []
    for item in json_objects:
        code = item.get("code", 0)
        if code is not None and str(code) not in {"0", "20000000"}:
            raise RuntimeError(f"Doubao TTS error {code}: {item.get('message', '')}")
        encoded = item.get("data") or item.get("audio") or item.get("audio_base64")
        if encoded:
            audio_parts.append(base64.b64decode(encoded))
    if audio_parts:
        return b"".join(audio_parts)
    return body


def _parse_doubao_json_objects(text: str) -> list[dict]:
    if not text:
        return []

    decoder = json.JSONDecoder()
    items: list[dict] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        if text.startswith("data:", index):
            line_end = text.find("\n", index)
            line = text[index + 5 : line_end if line_end != -1 else length].strip()
            if line:
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        items.append(parsed)
                except json.JSONDecodeError:
                    return []
            if line_end == -1:
                break
            index = line_end + 1
            continue
        try:
            parsed, next_index = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, dict):
            items.append(parsed)
        index = next_index
    return items
