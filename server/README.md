# SoulDance Server

FastAPI backend for product retrieval, recommendation orchestration, cart state, ASR, and TTS streaming.

## Layout

```text
server/
  backend/app/     Python package; import path remains backend.app
  tests/           Backend tests
  scripts/         Setup, launch, smoke, and STT helper scripts
  requirements.txt Python dependencies
```

Runtime data, `.env`, model assets, and virtualenvs are resolved from the repository root first so the existing remote deployment keeps working after the directory migration. A server-local `.env` can override root `.env` values.

## Host Runtime

The project uses the existing remote vLLM/conda-derived environment, not a Docker image.

Default paths:

```text
env/venv_vllm_cu128/bin/python        setup seed Python
env/conda_gcc12/bin/python            alternate conda-style Python
env/venv_shopguide_backend/bin/python backend runtime
```

## Setup

From the repository root:

```bash
bash server/scripts/setup_backend_env.sh
```

Override the seed runtime only when needed:

```bash
SEED_PYTHON=/home/huadabioa/houlong/SoulDance/env/conda_gcc12/bin/python \
  bash server/scripts/setup_backend_env.sh
```

## Run

```bash
bash server/scripts/start_backend.sh
```

Equivalent module target:

```bash
cd server
../env/venv_shopguide_backend/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl -fsS http://127.0.0.1:8000/health
```

## Test

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
```

## Smoke On A Non-Live Port

```bash
HOST=127.0.0.1 PORT=18083 USE_EMBEDDING=0 TTS_ENABLED=false STT_ENABLED=false \
  ARK_API_KEY= LLM_API_KEY= bash server/scripts/start_backend.sh
curl -fsS http://127.0.0.1:18083/health
```

Use the normal remote scripts for the live Cloudflare-backed demo runtime.
