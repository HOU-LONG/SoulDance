# SoulDance Architecture

SoulDance is a monorepo for a native Android shopping-guide client and a FastAPI backend. Stage 0/01 keeps the current implementation intact and makes the project layout, runtime commands, and contracts explicit.

## Boundaries

- Android owns UI state, streaming rendering, voice capture, and playback.
- The backend owns product retrieval, recommendation orchestration, cart mutations, ASR/TTS adapters, and all LLM/API credentials.
- The Android client must render backend-returned products only. It must not invent recommendation, price, inventory, discount, or order facts.
- RAG content can explain products. Live commerce state must come from business APIs and controlled tools.

## Repository Layout

```text
SoulDance/
  client/                  Android Kotlin + Jetpack Compose app
  server/                  FastAPI backend package, scripts, tests, requirements
  docs/                    Architecture, API, realtime protocol, runbooks, acceptance checks
  deploy/                  Host runtime notes and non-secret environment template
  ecommerce_agent_dataset/ Product fixture dataset and image assets
  data/                    Runtime sessions and carts; ignored by git
  env/                     Remote Python/vLLM/conda environments; ignored by git
  model/                   Local embedding/model assets; ignored by git
```

## Runtime Topology

```text
Android client
  HTTPS + WebSocket
FastAPI backend: server/backend/app/main.py
  ShopGuideAgent, CartService, STTAdapter, TTSAdapter
Remote host runtime
  env/venv_vllm_cu128 or env/conda_gcc12 -> env/venv_shopguide_backend
Local runtime assets
  ecommerce_agent_dataset, data, model
```

The current public-device debugging path uses a Cloudflare tunnel. The app points to the tunnel URL in `client/app/src/main/java/com/example/shopguideagent/config/AppConfig.kt`.

## Stage 0/01 Scope

Included:

- Monorepo layout under `client`, `server`, `docs`, and `deploy`.
- Stable backend and Android build commands.
- Health-checkable backend runtime on the existing remote host environment.
- Documented API and WebSocket contract.
- Non-secret deployment/runtime environment template.

Deferred:

- PostgreSQL, pgvector, Alembic migrations, and database models.
- Full RAG ingestion and hybrid retrieval evaluation.
- Checkout/order state machine.
- Multimodal upload persistence beyond the current STT path.
- Android multi-module split.
- Container image deployment; the current project uses the vLLM/conda-derived remote host runtime.
