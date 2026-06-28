# Deploy And Runtime Environment

Stage 0/01 uses the existing remote host environment on `mix_A100`; it does not build or run a Docker image.

Current runtime layout:

```text
env/venv_vllm_cu128/        Existing Python 3.12 seed runtime used by setup scripts
env/conda_gcc12/            Existing conda-style toolchain/runtime on the remote host
env/venv_shopguide_backend/ Backend virtualenv used to run FastAPI tests and service
deploy/env.example          Non-secret host runtime template
```

## LLM Provider Configuration

Set `LLM_PROVIDER` in the repo-root `.env` file:

```bash
# DeepSeek（当前默认 / current default）
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
LLM_FAST_MODEL=deepseek-v4-flash
LLM_REASONING_EFFORT=high

# Doubao（豆包）
#LLM_PROVIDER=doubao
#ARK_API_KEY=ark-xxx
#ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/
#ARK_MODEL=ep-xxx
```

Changing `LLM_PROVIDER` requires restarting the backend for the new setting to take effect.

## Backend Setup

Create or refresh the backend venv:

```bash
cd /home/huadabioa/houlong/SoulDance
bash server/scripts/setup_backend_env.sh
```

`server/scripts/setup_backend_env.sh` defaults to `env/venv_vllm_cu128/bin/python` as `SEED_PYTHON`. Override it if the active vLLM/conda Python changes:

```bash
SEED_PYTHON=/home/huadabioa/houlong/SoulDance/env/conda_gcc12/bin/python \
  bash server/scripts/setup_backend_env.sh
```

## Start Backend

```bash
bash server/scripts/start_backend.sh
```

Verify:

```bash
curl -fsS http://127.0.0.1:8000/health
```

Run backend health smoke without touching the live port:

```bash
HOST=127.0.0.1 PORT=18083 USE_EMBEDDING=0 TTS_ENABLED=false STT_ENABLED=false \
  ARK_API_KEY= LLM_API_KEY= bash server/scripts/start_backend.sh
curl -fsS http://127.0.0.1:18083/health
```

## Cloudflare Tunnel

Expose the backend to the public internet:

```bash
cloudflared tunnel --url http://127.0.0.1:8000 &
```

The tunnel URL (e.g. `https://<random>.trycloudflare.com`) is printed in the terminal output. This URL is temporary — it changes every time `cloudflared` restarts.

### Auto-Check During Android Build

The Android Gradle build automatically runs `client/scripts/ensure_tunnel.sh` before compilation. The script:

1. Checks `127.0.0.1:8000/health` — auto-starts backend if needed
2. Checks whether the current tunnel URL (from `AppConfig.kt`) is reachable
3. If the tunnel is down, restarts `cloudflared`, captures the new URL, and updates `AppConfig.kt`
4. When services are already running, the check completes in < 1s

Skip the auto-check:

```bash
SKIP_TUNNEL_CHECK=true ./gradlew :app:assembleDebug
```
