from __future__ import annotations

import base64
import logging

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

        events: list[dict] = []
        try:
            resp = await self.client.post(
                f"{self.settings.tts_base_url}/v1/audio/speech",
                json=payload,
                headers={"Authorization": f"Bearer {self.settings.tts_api_key}"},
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("TTS request failed: %s", exc)
            return [
                {
                    "type": "audio_error",
                    "message_id": message_id,
                    "message": "语音合成失败",
                }
            ]

        audio_bytes = resp.content
        if not audio_bytes:
            return events

        chunk_size = self._chunk_size_for(audio_bytes)
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i : i + chunk_size]
            events.append({
                "type": "audio_delta",
                "message_id": message_id,
                "encoding": self.settings.tts_response_format,
                "sample_rate": 24000,
                "channels": 1,
                "data": base64.b64encode(chunk).decode("ascii"),
                "is_last": False,
            })

        events.append({
            "type": "audio_done",
            "message_id": message_id,
        })
        return events

    def _chunk_size_for(self, audio_bytes: bytes) -> int:
        # Simple estimate based on chunk_duration_ms.
        # Qwen3-TTS wav defaults to 24kHz mono 16bit.
        bytes_per_second = 24000 * 2 * 1
        return max(
            1024,
            int(bytes_per_second * self.settings.tts_chunk_duration_ms / 1000),
        )


def _default_settings() -> Settings:
    from .config import get_settings

    return get_settings()
