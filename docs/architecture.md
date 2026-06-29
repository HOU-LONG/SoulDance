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

### LLM Agent 架构（Stage 1, 2026-06）

```
用户输入
  ↓
ToolPlanner (LLM → ToolPlan JSON)
  ↓
_dispatch_tool → 具体 tool 执行
  ├── product_analysis → ProductMatcher (BM25 模糊匹配) → LLM 流式分析
  ├── chitchat         → LLM 闲聊流（注入库内 top-5 商品供自然锚点）
  ├── recommend_product → IR 编译 + retrieval + ranking + LLM 生成
  ├── product_followup → context 焦点商品追问/替换
  ├── compare_products → 多维度对比
  ├── scenario_bundle  → 场景分解 + 逐 slot 检索
  └── cart_operation   → 购物车状态机
```

**核心模块**：
- `tool_planner.py` / `tool_plan.py`：LLM 优先的工具调度器，cart 等硬性短语 deterministic 前置，其它全部 LLM 决策
- `product_matcher.py`：共享 BM25/dense retriever 的模糊商品识别，top-5 候选 + gap 置信度
- `prompts/v1/tool_planner.txt`：Planner 系统提示（7 tool 判断标准 + 复合需求路由规则）
- `prompts/v1/response.txt`：推荐回复 prompt（自然短段落风格，主推锚点 + 备选纯文字）
- `prompts/v1/chitchat.txt`：闲聊 prompt（支持复合需求 + 内嵌商品锚点）

**与旧架构的关键区别**：
- 旧架构：5 层规则互斥（rule_semantic_frame → _merge_rule_guards → _normalize_intent → _apply_product_admission_gate → _primary_text_matches_selected），LLM 输出被 FakeLLM 模板覆盖
- 新架构：1 个 LLM 决策入口 → 单点分发，LLM 输出直接透传（仅 HallucinationChecker 保留为安全网）

- **Android 内联商品卡片**（`AiMessageBlock.kt`）：段落-卡片交替布局，主推内联卡 + 备选底部缩略图条

Deferred (genuine roadmap):

- PostgreSQL + pgvector 迁移（当前 SQLite 可支撑演示与单机部署，向量检索使用本地 FAISS dense index）。
- 多模态上传持久化（图片/视频的端到端存储管线）。
- Android 多模块拆分。
- 容器化部署（当前使用 vLLM/conda 宿主机运行时）。
