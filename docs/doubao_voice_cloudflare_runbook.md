# Doubao Voice + Cloudflare Runbook

Last updated: 2026-06-10

## Scope

This backend is configured for the Android voice flow below:

| Step | Implementation |
| --- | --- |
| User speech input | Doubao large-model streaming ASR API over WebSocket |
| Shopping-guide answer | Existing backend LLM/retrieval/cart logic |
| Answer to speech | Doubao HTTP Chunked unidirectional TTS V3 |
| Android playback | Backend emits `audio_delta` PCM chunks over `/ws/chat` |

API keys stay on `mix_A100` in `.env`. Do not put TTS, ASR, or LLM keys in the Android client.

## Source Documents

The implementation follows the local PDFs in the project root:

- `豆包语音_大模型流式语音识别API_1780023003.pdf`
- `豆包语音_HTTP单向流式语音合成_1781063540.pdf`

Important protocol choices:

- ASR WebSocket endpoint: `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`
- ASR auth: `X-Api-Key` plus `X-Api-Resource-Id`, `X-Api-Request-Id`, `X-Api-Connect-Id`
- ASR audio frame size: 200 ms, gzip-compressed binary protocol frames
- ASR payload format sent to Doubao: `pcm`, 16-bit, mono, 16000 Hz
- TTS endpoint: `https://openspeech.bytedance.com/api/v3/tts/unidirectional`
- TTS auth: `X-Api-Key`, `X-Api-Resource-Id`, `X-Api-Request-Id`
- TTS output format: `pcm`, 24000 Hz, so Android `AudioTrack` can play it directly

## Server Configuration

Edit `/home/huadabioa/houlong/SoulDance/.env` on `mix_A100`.

Minimum required secret:

```env
DOUBAO_VOICE_API_KEY=your-doubao-voice-api-key
```

The backend uses that shared key for both ASR and TTS unless either specific key is set:

```env
DOUBAO_ASR_API_KEY=
DOUBAO_TTS_API_KEY=
```

Current voice provider settings:

```env
STT_ENABLED=true
STT_PROVIDER=doubao_ws
DOUBAO_ASR_WS_URL=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
DOUBAO_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
DOUBAO_ASR_AUDIO_FORMAT=pcm
DOUBAO_ASR_LANGUAGE=zh-CN
DOUBAO_ASR_CHUNK_MS=200

TTS_ENABLED=true
TTS_PROVIDER=doubao_chunked_v3
DOUBAO_TTS_URL=https://openspeech.bytedance.com/api/v3/tts/unidirectional
DOUBAO_TTS_RESOURCE_ID=seed-tts-2.0
DOUBAO_TTS_MODEL=seed-tts-2.0-standard
DOUBAO_TTS_SPEAKER=zh_female_wenroushunv_uranus_bigtts
DOUBAO_TTS_FORMAT=pcm
DOUBAO_TTS_SAMPLE_RATE=24000
```

If Doubao returns a speaker permission or speaker-not-found error, replace `DOUBAO_TTS_SPEAKER` with an enabled voice ID from the console voice library.

## Restart Backend

```bash
cd /home/huadabioa/houlong/SoulDance
pkill -f 'uvicorn backend.app.main:app' || true
nohup env/venv_shopguide_backend/bin/python -m uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level info \
  --timeout-keep-alive 120 \
  --ws-ping-interval 20 \
  --ws-ping-timeout 10 \
  --limit-concurrency 20 \
  > logs/backend.log 2>&1 &
```

Health check:

```bash
curl -sS http://127.0.0.1:8000/health
```

Confirm non-secret voice config:

```bash
cd /home/huadabioa/houlong/SoulDance
env/venv_shopguide_backend/bin/python - <<'PY'
from backend.app.config import get_settings
s = get_settings()
print({
    "stt_provider": s.stt_provider,
    "tts_provider": s.tts_provider,
    "doubao_asr_resource_id": s.doubao_asr_resource_id,
    "doubao_tts_resource_id": s.doubao_tts_resource_id,
    "doubao_tts_format": s.doubao_tts_format,
    "has_voice_api_key": bool(s.doubao_voice_api_key),
})
PY
```

## Cloudflare Temporary Public URL

Keep the backend on port `8000`, then expose it:

```bash
mkdir -p /home/huadabioa/houlong/SoulDance/logs
nohup /home/huadabioa/bin/cloudflared tunnel --url http://127.0.0.1:8000 \
  > /home/huadabioa/houlong/SoulDance/logs/cloudflared.log 2>&1 &
tail -f /home/huadabioa/houlong/SoulDance/logs/cloudflared.log
```

Use the `https://*.trycloudflare.com` URL printed by `cloudflared` as Android's backend base URL.

## Android Configuration

Point the Android app to the Cloudflare URL:

- HTTP base URL: `https://<trycloudflare-host>/`
- WebSocket URL: `wss://<trycloudflare-host>/ws/chat`

The Android client should keep uploading user audio to `/api/stt` and keep reading chat/TTS events from `/ws/chat`. No client-side Doubao key is needed.

## Verification

Run backend tests:

```bash
cd /home/huadabioa/houlong/SoulDance
env/venv_shopguide_backend/bin/python -m pytest \
  tests/test_stt_adapter.py \
  tests/test_stt_endpoint.py \
  tests/test_tts_adapter.py \
  tests/test_voice_websocket.py \
  -q
```

Expected result on 2026-06-10:

```text
16 passed
```

After `DOUBAO_VOICE_API_KEY` is filled, verify with the Android app:

1. Record a short Chinese voice query.
2. Confirm `/api/stt` returns text instead of a 502 voice error.
3. Send the recognized text through `/ws/chat` with `tts_enabled=true`.
4. Confirm `audio_delta` events have `encoding=pcm_s16le`, `sample_rate=24000`, and the app plays audio.

Latest server-side smoke on 2026-06-10:

- Doubao TTS returned `audio_delta` events with `encoding=pcm_s16le`, `sample_rate=24000`.
- Backend `/api/stt` returned HTTP 200 using Doubao WebSocket ASR.
- Backend `/ws/chat` returned text/product events followed by TTS `audio_delta` and `audio_done`.

## Troubleshooting

- `Doubao ASR API key is not configured`: set `DOUBAO_VOICE_API_KEY` or `DOUBAO_ASR_API_KEY`.
- `Doubao TTS API key is not configured`: set `DOUBAO_VOICE_API_KEY` or `DOUBAO_TTS_API_KEY`.
- TTS speaker permission error: change `DOUBAO_TTS_SPEAKER` to a voice ID enabled in the console.
- ASR audio format error: verify Android uploads 16 kHz 16-bit mono WAV/PCM. The backend converts WAV to raw PCM before calling Doubao.
- No Cloudflare URL visible: restart `cloudflared` with output redirected to `logs/cloudflared.log`, then read that log.
