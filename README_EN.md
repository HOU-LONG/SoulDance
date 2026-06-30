# SoulDance — AI Personalized Dynamic Shopping Guide

SoulDance is an **LLM Agent-driven intelligent shopping assistant** — conversational shopping from natural language to product recommendation to cart, all in one flow. Unlike keyword-search + filter e-commerce, SoulDance transforms "purchase decisions" into "dialogue experiences."

## Product Highlights

1. **Sprite Companion Space**: A 2D virtual sprite "SoulDance" as your shopping companion — posture changes in real-time with the conversation (thinking/searching/recommending/celebrating), with level progression + Mars points + outfit system, giving AI shopping a human touch
2. **Empathy Before Recommendation**: Recognizes compound needs like "I feel down, recommend something sweet" — the LLM first offers emotional comfort, then naturally surfaces real product cards
3. **Dialogue Is Decision**: Recommend → inline card → detail sheet → add to cart, all without leaving the chat interface — zero page jumps

---

SoulDance is a monorepo for a low-pressure AI shopping-guide experience. It contains a native Android client (Kotlin + Jetpack Compose) and a FastAPI backend that owns recommendation, product retrieval, multi-turn context management, cart state, ASR, and streaming TTS integration. The client never implements recommendation logic or stores LLM/TTS/STT keys — it renders backend-owned results only.

---

## Repository Layout

```text
SoulDance/
  client/                  Android Kotlin + Jetpack Compose app
    scripts/               Build helper scripts (tunnel auto-check, etc.)
  server/                  FastAPI backend, tests, scripts, dependencies
  docs/                    Architecture, API, realtime protocol, runbooks, evaluation docs
  deploy/                  Host runtime notes and environment template
  ecommerce_agent_dataset/ Shared product dataset and image assets
  data/                    Runtime sessions/carts (git-ignored)
  env/                     Remote Python/vLLM/conda environments (git-ignored)
  model/                   Local embedding/model assets (git-ignored)
```

---

## Recent Updates (v2.0 — 2026-06)

v2.0 brings an architectural overhaul focused on **reliability** and **efficiency**:

- **Fact-Grounded Pipeline** — The LLM can ONLY reference products that exist in the database. Fabricated product_ids are intercepted and replaced in real-time during streaming. Cross-turn focus drift is detected and hallucination is automatically blocked.
- **UnifiedPlan Architecture** — Merged ToolPlan + SemanticFrame + RetrievalPlan into a single LLM call, reducing LLM invocations from 3 to 2 per turn. The IntentCompiler (redundant LLM semantic parsing) has been deleted.
- **3-Stage Session Checkpoint** — Auto-save at turn_start / post_retrieve / turn_end. Context and cached products are preserved across service interruptions.
- **Context-Aware Degradation** — Fallback messages for LLM timeout, retrieval errors, hallucination blocks, and contradiction detection include the user's last query and focused products.
- **CJK-ASCII Tokenization Normalization** — Auto-insert spaces between CJK↔ASCII and digit↔letter boundaries before jieba tokenization, fixing failures like "小米17Max" failing to match database entry "小米 17 Max".
- **Product Analysis Enhancement** — Matched product facts are injected directly into the LLM prompt, eliminating "product not found" false negatives when BM25 correctly matches the product.

---

## Core Capabilities

### Fact-Grounded Pipeline

End-to-end guarantee that the LLM references only real database products:

- **FactContextBuilder** — Builds `[[product_id]]` anchor fact sheets from current-turn products + cross-turn caches, injected into the LLM prompt
- **AnchorValidator** — Streaming cyclic state machine validates `[[...]]` anchors chunk-by-chunk: normal text passes through with zero delay, `[[` triggers micro-buffering → closure check → validity comparison → invalid anchors replaced in real-time
- **ConsistencyTracker** — Cross-turn denial cache (denied attributes won't be re-recommended) + focus drift detection (category drift triggers automatic alerts)
- **HallucinationChecker** — Post-hoc audit: detects fabricated product_ids, fabricated attributes, and contradictory claims

### Shopping Guide Dialogue Engine

- **UnifiedPlan Architecture**: Merges ToolPlan (tool selection) + SemanticFrame (slot filling) + RetrievalPlan (retrieval strategy) into a single LLM call, reducing LLM invocations from 3 to 2 per turn. IntentCompiler has been deleted.
- **ToolPlanner — LLM-First Tool Dispatcher**: Replaced the old multi-layer rule stack (5 exclusive rules → 1 LLM decision entry point). The LLM directly decides which tool to call and extracts parameters.
- **ProductMatcher — BM25 Fuzzy Product Recognition**: User shorthand like "Huawei Pura 70 Pro" / "Little Brown Bottle" / "Nescafe" auto-matches long-title products in the database
- **CJK-ASCII Tokenization Normalization**: Auto-inserts spaces between CJK↔ASCII and digit↔letter boundaries before jieba tokenization, fixing "小米17Max" failing to match database "小米 17 Max"
- **Natural Response Style**: Removed the five-segment label template (understanding/conclusion/primary recommendation/review summary/next steps). The LLM generates natural short-paragraph replies.
- **Compound Need Handling**: "I feel down, recommend something sweet" → LLM first empathizes "Hang in there — something sweet does help," then naturally surfaces product recommendations with real anchors
- **Chitchat with Embedded Product Recommendations**: Chitchat flow auto-injects top-5 relevant product summaries; the LLM can use `[[name#product_id]]` anchors to recommend real inventory products directly in conversation
- **Product Analysis Enhancement**: Matched product facts are directly injected into the LLM prompt, eliminating "product not found" false negatives when BM25 correctly matches

### Intent Routing (7 tools)

`recommend_product` / `product_analysis` / `compare_products` / `cart_operation` / `scenario_bundle` / `product_followup` / `chitchat`

### Multi-Turn Dialogue & Context

- **Multi-Turn Context Memory Architecture**: `dialog_turns` dialog log (100-message sliding window) + `ConstraintState` structured constraints + `LivingSummary` compression (triggered at 16 messages)
- **3-Stage Session Checkpoint**: Auto-save at Turn Start → Post-Retrieve → Turn End. Context and cached products preserved across service interruptions.
- **Context-Aware Degradation**: 6 fallback scenarios — LLM timeout / retrieval error / LLM error / hallucination detected / contradiction blocked / internal error — each fallback message includes the user's last query and focused products
- **Session History & User Isolation**: `SessionContext.display_messages` unified recording; REST API isolated by `X-User-Id` header; Android locally retains up to 30 sessions
- **Long-Session Anchors**: First-turn brand/category/product_ids stored as `reference_anchors`; "go back to the first round" triggers brand hard-constraint binding

### Retrieval & Ranking

- **Hybrid RAG**: BM25 keyword + vector semantic search with RRF/weighted fusion, CrossEncoder reranking (default) + LLM reranking (strong-scenario fallback), silent degradation on failure
- **Mid-Price Primary Promotion**: When same-tier candidates span ≥2× price range, a mid-price product is promoted to primary, leaving room for cheaper-alternative follow-ups
- **Cache System**: B1 recommendation memory cache (exact + semantic match) + B2 rank cache, bypassing LLM selection on hit

### Product Comparison

- **Named Product Resolution**: Brand + title n-gram matching → `_product_mention_score` hierarchical scoring (brand 45 / sub_category 35 / alias 160+ / title 160), with sub_category anchor filtering to prevent same-brand false matches
- **Fuzzy Reference Resolution**: "the cheaper one from earlier" → `reference_anchors[last_cheaper_alternative]`
- **Hard Constraint Bypass**: User-explicitly-named products skip historical-turn `hard_filter` constraints

### Cart Operations

- **Action Separation**: `view_cart` (read-only), `add_to_cart`, `update_sku`, `update_quantity`, `remove`, `clear_cart`, `checkout`
- **SKU Switching**: Natural-language "switch to the 50ml one" → flexible property matching (`50ml in value`), returning available-option clarification on mismatch
- **Dual-Mode Persistence**: SQLite (DB path) + JSON file, with `_sku_selections` persistence and clean/remove cleanup

### Context & Constraint Management

- **Soft Preference Extraction**: Skin type (dry/oily/sensitive), season (autumn-winter/spring-summer), effects (moisturizing/repair) auto-detected
- **Domain Switch Detection**: Category change triggers soft-constraint reset + recommendation memory clear, preserving dialog log and summary

### Voice Interaction

- STT (streaming WebSocket) + TTS (chunked streaming playback), Doubao voice engine support

### Inline Product Cards

- **Paragraph-Card Alternating Layout**: AI messages are split by `\n\n` into segments; segments containing anchors are followed by auto-inserted inline product cards (left thumbnail + right name/price/brand)
- **Primary/Alternative Hierarchy**: Primary product cards embedded inside the chat bubble; alternative products displayed as horizontal thumbnails below the bubble
- **Chitchat Also Supports Product Cards**: In compound-need scenarios, the LLM mentions products using `[[name#product_id]]` anchors in casual replies; the backend auto-scans and emits `product_item` events → frontend renders cards
- **Tap to Expand Details**: All anchors/cards uniformly invoke `ProductDetailBottomSheet`

### Feedback Loop

- Explicit feedback (ratings/action labels) + implicit signal aggregation, driving personalized ranking and user preference profiles

### Evaluation Framework

- WebSocket real-time smoke test (`server/scripts/demo_ws_smoke.py`), 10-turn demo with per-turn assertions and non-zero exit
- Long-session evaluation framework (`eval/`): token budget limits, compression effectiveness, degradation detection

---

## Demo Backend

```text
HTTP API: https://legs-committed-orange-tears.trycloudflare.com/
WebSocket: wss://legs-committed-orange-tears.trycloudflare.com/ws/chat
```

The Cloudflare URL is a temporary tunnel endpoint. The Gradle build automatically checks tunnel availability before compilation and updates `AppConfig.kt` when the hostname changes. To skip this check:

```bash
SKIP_TUNNEL_CHECK=true ./gradlew :app:assembleDebug
```

---

## Build & Run

### Prerequisites

- JDK 17+, Android SDK, Kotlin / Jetpack Compose toolchain
- Python 3.12+, FastAPI backend virtual environment

### Android Client (Linux)

```bash
cd client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
chmod +x gradlew

# Unit tests
./gradlew :app:testDebugUnitTest

# Build APK (auto-checks tunnel + auto-updates AppConfig URL)
./gradlew :app:assembleDebug
```

**Auto-incrementing version**: `versionCode` and `versionName` are derived from `git rev-list --count HEAD`. Each new commit automatically increments both — no manual version bump needed.

**Pre-build tunnel check**: Gradle runs `client/scripts/ensure_tunnel.sh` before `preBuild` to verify the backend server and Cloudflare tunnel are reachable. If the tunnel hostname has changed, `AppConfig.kt` is automatically updated before compilation. The check completes in < 1s when services are already running.

Skip the tunnel check (offline development, etc.):

```bash
SKIP_TUNNEL_CHECK=true ./gradlew :app:assembleDebug
```

APK output: `client/app/build/outputs/apk/debug/app-debug.apk`

### Backend Server

First-time setup:

```bash
bash server/scripts/setup_backend_env.sh
```

Start the backend (default port 8000):

```bash
bash server/scripts/start_backend.sh
```

Configure LLM provider in the repo-root `.env`:

```bash
# Use DeepSeek (current default)
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
LLM_REASONING_EFFORT=high

# Or use Doubao
#LLM_PROVIDER=doubao
#ARK_API_KEY=ark-xxx
#ARK_MODEL=ep-xxx
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

### Public Exposure (Cloudflare Tunnel)

```bash
cloudflared tunnel --url http://127.0.0.1:8000 &
# The URL is printed in the terminal output
```

Run `client/scripts/ensure_tunnel.sh` before building to automate the full flow: check backend → start tunnel → update AppConfig.

---

## Key API Surface

```text
GET  /health
GET  /api/products
GET  /api/products/{product_id}
GET  /api/sessions
GET  /api/sessions/latest
GET  /api/sessions/{session_id}
DELETE /api/sessions/{session_id}
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
| `docs/design.md` | **Design doc**: system architecture / tech stack / directory structure / configuration / key problems and solutions |
| `docs/highlights.md` | **Product & technical highlights**: sprite space / compound needs / dialogue closure / Agent architecture |
| `docs/deploy-and-experience.md` | **Deployment & experience guide**: 5-minute quick deploy / reviewer experience checklist |
| `docs/architecture.md` | System architecture |
| `docs/api-contract.md` | API contract |
| `docs/realtime-protocol.md` | Realtime communication protocol |
| `docs/runbook.md` | Development runbook + troubleshooting |
| `deploy/README.md` | Deployment guide |
| `client/AGENTS.md` | Client development guide |
