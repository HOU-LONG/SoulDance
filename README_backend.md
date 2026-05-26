# SoulDance ShopGuide Backend

This backend implements the ShopGuide Agent RAG demo for `ecommerce_agent_dataset`.

## Environment Layout

The project now uses two separate Python environments:

```text
env/venv_shopguide_backend  FastAPI + RAG + tests + smoke demo
env/venv_vllm_cu128         Qwen3-TTS / vLLM-Omni only
env/conda_gcc12             GCC/libstdc++ runtime for vLLM-Omni
```

Do not install ShopGuide backend dependencies into `env/venv_vllm_cu128`; that environment is reserved for Qwen3-TTS and vLLM-Omni.

## Create Backend Environment

```bash
cd /home/huadabioa/houlong/SoulDance
bash scripts/setup_backend_env.sh
```

The script creates:

```text
env/venv_shopguide_backend
```

using Python 3.12 from `env/venv_vllm_cu128`, then installs `requirements-backend.txt`.

## Runtime Config

Set the API key at runtime. Do not write the real key into source files.

```bash
export ARK_API_KEY="your-runtime-key"
export ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3/"
export ARK_MODEL="ep-20260514111645-lmgt2"
export EMBEDDING_MODEL_DIR="model/bge-small-zh-v1.5"
```

For quick local/backend-only checks without dense embedding:

```bash
export USE_EMBEDDING=0
```

## Commands

```bash
env/venv_shopguide_backend/bin/python -m pytest tests/test_agent_core.py tests/test_api.py -v
env/venv_shopguide_backend/bin/python scripts/check_embedding.py
ARK_API_KEY="$ARK_API_KEY" bash scripts/start_backend.sh
SHOPGUIDE_BASE_URL=http://127.0.0.1:18080 env/venv_shopguide_backend/bin/python scripts/smoke_demo.py
```

`scripts/start_backend.sh` defaults to:

```text
HOST=0.0.0.0
PORT=18080
BACKEND_VENV=env/venv_shopguide_backend
```

## API Surface

- `GET /health`
- `GET /api/products`
- `GET /api/products/{product_id}`
- `POST /api/debug/retrieval_plan`
- `WS /ws/chat`
- `GET /api/cart?session_id=...`
- `POST /api/cart/add`
- `POST /api/cart/update_quantity`
- `POST /api/cart/remove`
- `POST /api/cart/clear`
- `POST /api/cart/checkout`

## Qwen3-TTS

Qwen3-TTS runs as a separate HTTP service through vLLM-Omni. See:

```text
docs/qwen3_tts_usage.md
```

The ShopGuide backend should call that service over HTTP when TTS wiring is enabled; it should not import or run vLLM-Omni inside the backend environment.

