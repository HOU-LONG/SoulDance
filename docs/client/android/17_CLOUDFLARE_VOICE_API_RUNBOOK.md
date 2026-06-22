# Cloudflare Voice API Runbook

> Last verified on 2026-06-10. This runbook is for exposing the `mix_A100`
> backend through a temporary Cloudflare public URL and using a hosted TTS API
> instead of self-hosting Qwen3-TTS.

## 1. Recommended Architecture

```text
Android app
  -> Cloudflare temporary URL
  -> mix_A100 FastAPI backend
     -> /api/stt for speech-to-text
     -> /ws/chat for chat, product cards, cart events, and audio_delta
     -> hosted TTS API such as Xiaomi MiMo
```

Key rule: Android never stores TTS or LLM API keys. The backend calls the hosted
TTS API and normalizes audio into WebSocket events:

```json
{
  "type": "audio_delta",
  "message_id": "...",
  "encoding": "pcm_s16le",
  "sample_rate": 24000,
  "channels": 1,
  "data": "...base64...",
  "audio_base64": "...base64..."
}
```

Android accepts both `data` and `audio_base64`, then plays PCM through
`AudioTrack`.

## 2. Why Hosted TTS

Self-hosted Qwen3-TTS on `mix_A100` requires GPU scheduling, large model loading,
vLLM-Omni runtime care, and process health checks. For demo and app integration,
hosted TTS is simpler:

- no local TTS GPU memory pressure;
- no model download or CUDA dependency drift;
- backend keeps one stable Android contract;
- provider can be changed by `.env` only.

Xiaomi's MiMo public site lists a MiMo-V2.5-TTS series and API platform, and the
Xiaomi MiMo LiteLLM provider documents `api_key` usage. A public OpenClaw issue
describes MiMo TTS as `POST /v1/chat/completions` with an `api-key` header and
base64 audio in `choices[0].message.audio.data`; verify final model names in
the Xiaomi MiMo API console before production use.

References:

- [Xiaomi MiMo](https://mimo.mi.com/)
- [Xiaomi MiMo API Open Platform](https://platform.xiaomimimo.com/)
- [LiteLLM Xiaomi MiMo provider](https://docs.litellm.ai/docs/providers/xiaomi_mimo)
- [OpenClaw MiMo TTS provider discussion](https://github.com/openclaw/openclaw/issues/52376)

## 3. Backend TTS Configuration

On `mix_A100`:

```bash
cd /home/huadabioa/houlong/SoulDance
```

Set `.env` for MiMo hosted TTS:

```bash
TTS_ENABLED=true
TTS_PROVIDER=mimo
TTS_BASE_URL=https://api.xiaomimimo.com/v1
TTS_API_KEY=<your_mimo_api_key>
TTS_MODEL=mimo-v2-tts
TTS_RESPONSE_FORMAT=wav
TTS_DEFAULT_VOICE=default_zh
TTS_TIMEOUT_SECONDS=30
TTS_MAX_TEXT_LENGTH=500
```

Notes:

- `TTS_MODEL` and `TTS_DEFAULT_VOICE` must match the Xiaomi API console.
- If using an OpenAI-compatible `/v1/audio/speech` provider instead, set:

```bash
TTS_PROVIDER=openai_audio
TTS_BASE_URL=<provider_base_url_without_trailing_slash>
TTS_API_KEY=<provider_key>
TTS_MODEL=<provider_tts_model>
TTS_RESPONSE_FORMAT=wav
```

## 4. Start Backend

Stop old backend if port `8000` is occupied:

```bash
pkill -f "uvicorn backend.app.main:app" || true
```

Start FastAPI:

```bash
cd /home/huadabioa/houlong/SoulDance
HOST=0.0.0.0 PORT=8000 nohup ./start_backend.sh > logs/backend-android-8000.log 2>&1 &
```

Verify:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/openapi.json | grep /api/stt
```

## 5. Expose With Cloudflare Temporary URL

Start a temporary Cloudflare tunnel on `mix_A100`:

```bash
/home/huadabioa/bin/cloudflared tunnel --url http://127.0.0.1:8000
```

Copy the generated `https://*.trycloudflare.com` URL from stdout.

For long-running demo sessions:

```bash
nohup /home/huadabioa/bin/cloudflared tunnel --url http://127.0.0.1:8000 \
  > logs/cloudflared-8000.log 2>&1 &
tail -f logs/cloudflared-8000.log
```

Verify public access from the local computer:

```powershell
curl.exe --noproxy "*" -sS https://<your-subdomain>.trycloudflare.com/health
```

## 6. Android AppConfig

Update Android config:

```kotlin
const val BASE_HTTP_URL = "https://<your-subdomain>.trycloudflare.com"
const val BASE_WS_URL = "wss://<your-subdomain>.trycloudflare.com"
const val WS_CHAT_PATH = "/ws/chat"
```

Then build:

```powershell
$env:JAVA_HOME='D:\项目\SoulDance\.tools\jdk17\jdk-17.0.19+10'
$env:PATH="$env:JAVA_HOME\bin;$env:PATH"
.\gradlew.bat :app:assembleDebug
.\gradlew.bat :app:testDebugUnitTest
```

## 7. Voice Smoke Test

Text + TTS over WebSocket should return:

```text
text_delta
product events when applicable
done
audio_delta
audio_done
```

The backend is allowed to return `audio_error` if the hosted TTS API key or model
is invalid; text and product cards must still render.

Android manual QA:

1. Install debug build.
2. Press and hold the mic button.
3. Speak a short buying request.
4. Confirm the transcribed text sends into the chat.
5. Confirm assistant text streams.
6. Confirm audio plays after response if TTS is enabled and API key is valid.

## 8. Troubleshooting

- `/api/stt` missing from OpenAPI: backend process is old; restart uvicorn.
- Cloudflare URL returns 502: backend on `127.0.0.1:8000` is not healthy.
- Android voice upload fails with 422: backend expects multipart field `audio`.
- TTS text works but no sound: inspect WebSocket for `audio_error`; check
  `TTS_API_KEY`, `TTS_MODEL`, `TTS_BASE_URL`, and hosted API quota.
- Audio sounds too fast or slow: ensure backend sends the real `sample_rate` and
  `encoding=pcm_s16le`.
- Do not start local Qwen3-TTS unless explicitly needed:

```bash
pkill -f "vllm_omni.entrypoints.cli.main serve .*qwen3_tts" || true
```
