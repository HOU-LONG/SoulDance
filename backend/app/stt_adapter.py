from __future__ import annotations

import logging

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class STTAdapter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or _default_settings()
        self.client = httpx.AsyncClient(timeout=self.settings.stt_timeout_seconds)

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
    ) -> dict:
        if not self.settings.stt_enabled:
            return {"text": "", "is_final": True, "confidence": None}

        max_size = self.settings.stt_max_audio_size_mb * 1024 * 1024
        if len(audio_bytes) > max_size:
            raise ValueError(f"Audio exceeds {self.settings.stt_max_audio_size_mb}MB limit")

        if self.settings.stt_provider == "funasr":
            return await self._transcribe_funasr(audio_bytes, audio_format)

        if self.settings.stt_provider == "whisper":
            return await self._transcribe_whisper(audio_bytes, audio_format)

        raise ValueError(f"Unsupported STT provider: {self.settings.stt_provider}")

    async def _transcribe_funasr(self, audio_bytes: bytes, audio_format: str) -> dict:
        # FunASR HTTP service inference endpoint. Adjust to /inference if needed.
        url = f"{self.settings.stt_base_url}/asr"
        files = {"audio": ("audio.wav", audio_bytes, f"audio/{audio_format}")}
        data = {
            "model": self.settings.stt_model,
            "sample_rate": str(self.settings.stt_sample_rate),
            "language": "zh",
        }
        try:
            resp = await self.client.post(url, files=files, data=data)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("STT request failed: %s", exc)
            raise RuntimeError("语音识别服务不可用") from exc

        payload = resp.json()
        # FunASR common response: {"text": "...", "timestamp": [...]}
        return {
            "text": payload.get("text", "").strip(),
            "is_final": True,
            "confidence": payload.get("confidence"),
            "language": "zh",
        }

    async def _transcribe_whisper(self, audio_bytes: bytes, audio_format: str) -> dict:
        url = f"{self.settings.stt_base_url}/v1/audio/transcriptions"
        files = {"file": ("audio.wav", audio_bytes, f"audio/{audio_format}")}
        data = {"model": self.settings.stt_model, "language": "zh"}
        try:
            resp = await self.client.post(url, files=files, data=data)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("STT request failed: %s", exc)
            raise RuntimeError("语音识别服务不可用") from exc

        payload = resp.json()
        return {
            "text": payload.get("text", "").strip(),
            "is_final": True,
            "confidence": None,
            "language": "zh",
        }


def _default_settings() -> Settings:
    from .config import get_settings

    return get_settings()
