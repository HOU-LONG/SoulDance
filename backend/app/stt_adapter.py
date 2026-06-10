from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import struct
import uuid
import wave

import httpx
import websockets

from .config import Settings

logger = logging.getLogger(__name__)

_ASR_VERSION = 0x1
_ASR_HEADER_SIZE = 0x1
_ASR_FULL_CLIENT_REQUEST = 0x1
_ASR_AUDIO_ONLY_REQUEST = 0x2
_ASR_FULL_SERVER_RESPONSE = 0x9
_ASR_ERROR_RESPONSE = 0xF
_ASR_FLAG_NONE = 0x0
_ASR_FLAG_WITH_SEQUENCE = 0x1
_ASR_FLAG_LAST_NO_SEQUENCE = 0x2
_ASR_FLAG_LAST_WITH_SEQUENCE = 0x3
_ASR_SERIALIZATION_NONE = 0x0
_ASR_SERIALIZATION_JSON = 0x1
_ASR_COMPRESSION_NONE = 0x0
_ASR_COMPRESSION_GZIP = 0x1


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

        provider = self.settings.stt_provider.lower()

        if provider == "funasr":
            return await self._transcribe_funasr(audio_bytes, audio_format)

        if provider == "whisper":
            return await self._transcribe_whisper(audio_bytes, audio_format)

        if provider in {"doubao_ws", "doubao_asr", "volc_asr"}:
            return await self._transcribe_doubao_ws(audio_bytes, audio_format)

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

    async def _transcribe_doubao_ws(self, audio_bytes: bytes, audio_format: str) -> dict:
        request_id = str(uuid.uuid4())
        headers = self._doubao_asr_headers(request_id)
        audio_payload, payload_format, sample_rate, channels = self._prepare_doubao_audio(
            audio_bytes,
            audio_format,
        )
        first_request = {
            "user": {
                "uid": self.settings.doubao_asr_uid,
            },
            "audio": {
                "format": payload_format,
                "rate": sample_rate,
                "bits": 16,
                "channel": channels,
                "language": self.settings.doubao_asr_language,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": self.settings.doubao_asr_enable_itn,
                "enable_punc": self.settings.doubao_asr_enable_punc,
                "result_type": self.settings.doubao_asr_result_type,
            },
        }
        first_frame = _build_doubao_asr_frame(
            _ASR_FULL_CLIENT_REQUEST,
            _ASR_FLAG_NONE,
            _ASR_SERIALIZATION_JSON,
            _ASR_COMPRESSION_GZIP,
            json.dumps(first_request, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

        last_text = ""
        final_payload: dict | None = None

        async def receive_results(ws) -> None:
            nonlocal last_text, final_payload
            while True:
                parsed = _parse_doubao_asr_message(await ws.recv())
                payload = parsed.get("payload")
                if isinstance(payload, dict):
                    text = _extract_doubao_asr_text(payload)
                    if text:
                        last_text = text
                        final_payload = payload
                if parsed.get("is_final"):
                    return

        timeout = self.settings.stt_timeout_seconds
        try:
            async with websockets.connect(
                self.settings.doubao_asr_ws_url,
                additional_headers=headers,
                max_size=None,
                open_timeout=timeout,
                close_timeout=5,
            ) as ws:
                receiver = asyncio.create_task(receive_results(ws))
                await ws.send(first_frame)

                chunks = list(self._doubao_audio_chunks(audio_payload, sample_rate, channels))
                if not chunks:
                    chunks = [b""]
                for index, chunk in enumerate(chunks):
                    is_last = index == len(chunks) - 1
                    await ws.send(
                        _build_doubao_asr_frame(
                            _ASR_AUDIO_ONLY_REQUEST,
                            _ASR_FLAG_LAST_NO_SEQUENCE if is_last else _ASR_FLAG_NONE,
                            _ASR_SERIALIZATION_NONE,
                            _ASR_COMPRESSION_GZIP,
                            chunk,
                        )
                    )
                    delay_ms = self.settings.doubao_asr_inter_chunk_delay_ms
                    if delay_ms > 0 and not is_last:
                        await asyncio.sleep(delay_ms / 1000)

                try:
                    await asyncio.wait_for(receiver, timeout=timeout)
                except asyncio.TimeoutError:
                    receiver.cancel()
                    if not last_text:
                        raise RuntimeError("Doubao ASR timed out")
        except Exception as exc:
            logger.warning("Doubao ASR request failed: %s", exc)
            raise RuntimeError("语音识别服务不可用") from exc

        return {
            "text": last_text.strip(),
            "is_final": True,
            "confidence": None,
            "language": self.settings.doubao_asr_language,
            "raw": final_payload,
        }

    def _doubao_asr_headers(self, request_id: str) -> dict[str, str]:
        headers = {
            "X-Api-Resource-Id": self.settings.doubao_asr_resource_id,
            "X-Api-Request-Id": request_id,
            "X-Api-Connect-Id": request_id,
            "X-Api-Sequence": "-1",
        }
        if self.settings.doubao_asr_api_key:
            headers["X-Api-Key"] = self.settings.doubao_asr_api_key
            return headers
        if self.settings.doubao_asr_app_key and self.settings.doubao_asr_access_key:
            headers["X-Api-App-Key"] = self.settings.doubao_asr_app_key
            headers["X-Api-Access-Key"] = self.settings.doubao_asr_access_key
            return headers
        raise RuntimeError("Doubao ASR API key is not configured")

    def _prepare_doubao_audio(self, audio_bytes: bytes, audio_format: str) -> tuple[bytes, str, int, int]:
        target_format = self.settings.doubao_asr_audio_format.lower()
        if target_format == "pcm" and _looks_like_wav(audio_bytes, audio_format):
            try:
                with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
                    sample_width = wav.getsampwidth()
                    sample_rate = wav.getframerate()
                    channels = wav.getnchannels()
                    if sample_width != 2:
                        raise ValueError("Doubao ASR requires 16-bit PCM audio")
                    return wav.readframes(wav.getnframes()), "pcm", sample_rate, channels
            except wave.Error as exc:
                raise ValueError("Invalid WAV audio for Doubao ASR") from exc
        return audio_bytes, target_format or audio_format, self.settings.stt_sample_rate, 1

    def _doubao_audio_chunks(self, audio_bytes: bytes, sample_rate: int, channels: int):
        bytes_per_sample = 2 * max(1, channels)
        chunk_size = int(sample_rate * bytes_per_sample * self.settings.doubao_asr_chunk_ms / 1000)
        chunk_size = max(bytes_per_sample, chunk_size)
        chunk_size -= chunk_size % bytes_per_sample
        for start in range(0, len(audio_bytes), chunk_size):
            yield audio_bytes[start : start + chunk_size]


def _default_settings() -> Settings:
    from .config import get_settings

    return get_settings()


def _looks_like_wav(audio_bytes: bytes, audio_format: str) -> bool:
    return audio_format.lower() == "wav" or audio_bytes.startswith(b"RIFF")


def _build_doubao_asr_frame(
    message_type: int,
    flags: int,
    serialization: int,
    compression: int,
    payload: bytes,
) -> bytes:
    if compression == _ASR_COMPRESSION_GZIP:
        payload = gzip.compress(payload)
    header = bytes(
        [
            (_ASR_VERSION << 4) | _ASR_HEADER_SIZE,
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0x00,
        ]
    )
    return header + struct.pack(">I", len(payload)) + payload


def _parse_doubao_asr_message(message: bytes | str) -> dict:
    if isinstance(message, str):
        return {"payload": json.loads(message), "is_final": False}

    data = bytes(message)
    if len(data) < 4:
        raise RuntimeError("Doubao ASR returned an invalid frame")

    header_size = (data[0] & 0x0F) * 4
    message_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F
    offset = header_size

    if message_type == _ASR_ERROR_RESPONSE:
        if len(data) < offset + 8:
            raise RuntimeError("Doubao ASR returned an invalid error frame")
        code = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        message_size = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        error_message = data[offset : offset + message_size].decode("utf-8", errors="replace")
        raise RuntimeError(f"Doubao ASR error {code}: {error_message}")

    if message_type != _ASR_FULL_SERVER_RESPONSE:
        return {"payload": None, "is_final": False}

    sequence: int | None = None
    if flags in {_ASR_FLAG_WITH_SEQUENCE, _ASR_FLAG_LAST_WITH_SEQUENCE}:
        if len(data) < offset + 4:
            raise RuntimeError("Doubao ASR returned an invalid response frame")
        sequence = struct.unpack(">i", data[offset : offset + 4])[0]
        offset += 4

    if len(data) < offset + 4:
        raise RuntimeError("Doubao ASR returned an invalid response frame")
    payload_size = struct.unpack(">I", data[offset : offset + 4])[0]
    offset += 4
    payload = data[offset : offset + payload_size]
    if compression == _ASR_COMPRESSION_GZIP:
        payload = gzip.decompress(payload)

    decoded_payload: dict | bytes | None
    if serialization == _ASR_SERIALIZATION_JSON and payload:
        decoded_payload = json.loads(payload.decode("utf-8"))
    else:
        decoded_payload = payload

    return {
        "payload": decoded_payload,
        "sequence": sequence,
        "is_final": flags == _ASR_FLAG_LAST_WITH_SEQUENCE or (sequence is not None and sequence < 0),
    }


def _extract_doubao_asr_text(payload: dict) -> str:
    result = payload.get("result")
    if isinstance(result, dict):
        text = result.get("text")
        if text:
            return str(text)
        utterances = result.get("utterances")
        if isinstance(utterances, list):
            return "".join(str(item.get("text", "")) for item in utterances if isinstance(item, dict))
    if isinstance(result, list):
        parts = []
        for item in result:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        if parts:
            return "".join(parts)
    if payload.get("text"):
        return str(payload["text"])
    return ""
