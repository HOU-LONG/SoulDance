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

Implemented (Stage 0/01):

- **RAG 混合检索**（`server/backend/app/rag/`）：BM25 关键词检索 + 向量语义检索 + RRF/weighted 融合，CrossEncoder 重排（默认）与 LLM 重排（comparison/refinement 等强场景的兜底），失败均静默降级回原序，不影响可用性。
- **SQLite + SQLAlchemy 持久化**（`server/backend/app/db/`）：购物车、订单、会话、用户画像、反馈事件均已接入 SQLite 存储，Alembic 迁移就绪（`server/alembic/`），数据库 URL 通过 `SHOPGUIDE_DATABASE_URL` 环境变量配置，留空自动落到仓库根 `data/shopguide.db`。
- **订单状态机**（`server/backend/app/order_service.py`）：支持 `address_required → awaiting_confirmation → completed` 三态流转，含 `confirmation_token` 生命周期、`idempotency_key` 去重、内存/DB 双写，REST API 通过 `/api/order/*` 暴露。

Deferred (genuine roadmap):

- PostgreSQL + pgvector 迁移（当前 SQLite 可支撑演示与单机部署，向量检索使用本地 FAISS dense index）。
- 多模态上传持久化（图片/视频的端到端存储管线）。
- Android 多模块拆分。
- 容器化部署（当前使用 vLLM/conda 宿主机运行时）。
