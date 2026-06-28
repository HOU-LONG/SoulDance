# SoulDance — AI Personalized Dynamic Shopping Guide

SoulDance is a monorepo for a low-pressure AI shopping-guide experience. It contains a native Android client (Kotlin + Jetpack Compose) and a FastAPI backend that owns recommendation, product retrieval, multi-turn context management, cart state, ASR, and streaming TTS integration. The client never implements recommendation logic or stores LLM/TTS/STT keys — it renders backend-owned results only.

---

## Repository Layout

```text
SoulDance/
  client/                  Android Kotlin + Jetpack Compose app
  server/                  FastAPI backend, tests, scripts, dependencies
  docs/                    Architecture, API, realtime protocol, runbooks, evaluation docs
  deploy/                  Host runtime notes and environment template
  ecommerce_agent_dataset/ Shared product dataset and image assets
  data/                    Runtime sessions/carts (git-ignored)
  env/                     Remote Python/vLLM/conda environments (git-ignored)
  model/                   Local embedding/model assets (git-ignored)
```

---

## Core Capabilities

### Shopping Guide Dialogue Engine
- **Five-Scene Demo End-to-End**: skincare serum recommendation → cheaper alternative follow-up → named product + fuzzy reference comparison → cross-domain long-session anchor recall → cart add/view/SKU switch. All 10 turns pass strict-assertion golden regression.
- **Multi-Turn Context Memory Architecture** (added 2026-06):
  - Form A: full `[{role, content}]` dialog log (`dialog_turns`), 100-message sliding window
  - Form B: structured constraint state (`ConstraintState`) + product parameter cache (`entity_params`) + long-session summary compression (`LivingSummary`, triggered at 16 messages)
  - Prompt injection: dialog history + constraint notes injected into Response LLM evidence payload in real time
- **Semantic Intent Compilation**: LLM + rule-based dual-path parsing, confidence gating with contextual fallback re-judgment
- **Intent Routing**: 8 intents (`recommend_product`, `product_followup`, `compare_products`, `cart_operation`, `scenario_bundle`, `clarification`, `small_talk`, `unclear_input`) with tool-based dispatch

### Retrieval & Ranking
- **Hybrid RAG**: BM25 keyword + vector semantic search with RRF/weighted fusion, CrossEncoder reranking (default) + LLM reranking (strong-scenario fallback), silent degradation on failure
- **Mid-Price Primary Promotion**: when same-tier candidates span ≥2× price range, a mid-price product is promoted to primary, leaving room for cheaper-alternative follow-ups
- **Cache System**: B1 recommendation memory cache (exact + semantic match) + B2 rank cache, bypassing LLM selection on hit

### Product Comparison
- **Named Product Resolution**: brand + title n-gram matching → `_product_mention_score` hierarchical scoring (brand 45 / sub_category 35 / alias 160+ / title 160), with sub_category anchor filtering to prevent same-brand false matches
- **Fuzzy Reference Resolution**: "the cheaper one from earlier" → `reference_anchors[last_cheaper_alternative]`
- **Hard Constraint Bypass**: user-explicitly-named products skip historical-turn `hard_filter` constraints

### Cart Operations
- **Action Separation**: `view_cart` (read-only), `add_to_cart`, `update_sku`, `update_quantity`, `remove`, `clear_cart`, `checkout`
- **SKU Switching**: natural-language "switch to the 50ml one" → flexible property matching (`50ml in value`), returning available-option clarification on mismatch
- **Dual-Mode Persistence**: SQLite (DB path) + JSON file, with `_sku_selections` persistence and clean/remove cleanup

### Context & Constraint Management
- **Soft Preference Extraction**: skin type (dry/oily/sensitive), season (autumn-winter/spring-summer), effects (moisturizing/repair) auto-detected
- **Domain Switch Detection**: category change triggers soft-constraint reset + recommendation memory clear, preserving dialog log and summary
- **Long-Session Anchors**: first-turn brand/category/product_ids stored as `reference_anchors`; "go back to the first round" triggers brand hard-constraint binding

### Voice Interaction
- STT (streaming WebSocket) + TTS (chunked streaming playback), Doubao voice engine support

### Inline Product Anchor
- **Unified inline product entry**: products in AI messages are embedded as `[[name#product_id]]` anchors inside the message text, replacing standalone product cards
- **Tap to expand details**: every anchor opens the `ProductDetailBottomSheet`, covering recommendation, comparison, bundle, and follow-up flows
- **Cross-stack protocol alignment**:
  - Backend prompts inject `[[title#product_id]]` into primary, alternative, comparison, and bundle text, and validate that `product_id` belongs to `allowed_products`
  - Invalid or missing anchors degrade gracefully: markup is stripped and a warning is logged, preventing frontend parse failures
  - Dialogue history compresses anchors to `[product:product_id]` to save tokens while preserving references
- **Implementation plan**: `docs/superpowers/plans/2026-06-27-inline-product-anchor.md`

### Feedback Loop
- Explicit feedback (ratings/action labels) + implicit signal aggregation, driving personalized ranking and user preference profiles

### Evaluation Framework
- WebSocket real-time smoke test (`server/scripts/demo_ws_smoke.py`), 10-turn demo with per-turn assertions and non-zero exit
- Long-session evaluation framework (`eval/`): token budget limits, compression effectiveness, degradation detection

---

## Demo Backend

```text
HTTP API: https://missouri-traveling-seat-diverse.trycloudflare.com/
WebSocket: wss://missouri-traveling-seat-diverse.trycloudflare.com/ws/chat
```

The Cloudflare URL is a temporary tunnel endpoint. If it changes, update `client/.../AppConfig.kt` and rebuild the APK.

---

## Build & Run

### Android Client (Linux)

```bash
cd client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
chmod +x gradlew
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug
```

APK output: `client/app/build/outputs/apk/debug/app-debug.apk`

### Backend Server

```bash
bash server/scripts/setup_backend_env.sh
bash server/scripts/start_backend.sh
```

Run tests:

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
```

Smoke check:

```bash
HOST=127.0.0.1 PORT=18083 USE_EMBEDDING=0 TTS_ENABLED=false STT_ENABLED=false \
  ARK_API_KEY= LLM_API_KEY= bash server/scripts/start_backend.sh
curl -fsS http://127.0.0.1:18083/health
```

---

## Key API Surface

```text
GET  /health
GET  /api/products
GET  /api/products/{product_id}
GET  /api/cart
POST /api/cart/add
POST /api/cart/clear
POST /api/cart/checkout
POST /api/stt
WS   /ws/chat
```

WebSocket event types: `text_delta`, `product_item`, `replacement_product`, `comparison_result`, `cart_update`, `quick_actions`, `audio_delta`, `done`, `error`.

---

## Documentation Index

| Document | Content |
|----------|---------|
| `docs/architecture.md` | System architecture |
| `docs/api-contract.md` | API contract |
| `docs/realtime-protocol.md` | Realtime communication protocol |
| `docs/runbook.md` | Development runbook |
| `docs/superpowers/specs/` | Design specs (demo agent flow, context memory architecture, etc.) |
| `docs/superpowers/plans/` | Implementation plans |
| `deploy/README.md` | Deployment guide |
| `client/AGENTS.md` | Client development guide |
