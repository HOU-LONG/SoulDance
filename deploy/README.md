# Deploy And Runtime Environment

Stage 0/01 uses the existing remote host environment on `mix_A100`; it does not build or run a Docker image.

Current runtime layout:

```text
env/venv_vllm_cu128/        Existing Python 3.12 seed runtime used by setup scripts
env/conda_gcc12/            Existing conda-style toolchain/runtime on the remote host
env/venv_shopguide_backend/ Backend virtualenv used to run FastAPI tests and service
deploy/env.example          Non-secret host runtime template
```

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

Run backend health smoke without touching the live port:

```bash
HOST=127.0.0.1 PORT=18083 USE_EMBEDDING=0 TTS_ENABLED=false STT_ENABLED=false \
  ARK_API_KEY= LLM_API_KEY= bash server/scripts/start_backend.sh
```

Then check:

```bash
curl -fsS http://127.0.0.1:18083/health
```

The real Cloudflare-backed demo should continue to use the existing host process and tunnel workflow.
