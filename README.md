# SoulDance / ShopGuide Agent

SoulDance is a monorepo for a low-pressure AI shopping-guide experience. It contains a native Android client and a FastAPI backend that owns recommendation, product matching, cart state, ASR, and streaming TTS integration.

## Repository Layout

```text
SoulDance/
  client/                  Android Kotlin + Jetpack Compose app
  server/                  FastAPI backend package, tests, scripts, requirements
  docs/                    Architecture, API, realtime protocol, runbooks, evaluation docs
  deploy/                  Host runtime notes and non-secret environment template
  ecommerce_agent_dataset/ Shared product dataset and image assets
  data/                    Runtime sessions/carts, ignored by git
  env/                     Remote Python/vLLM/conda environments, ignored by git
  model/                   Local embedding/model assets, ignored by git
```

The client never implements product recommendation logic or stores LLM/TTS/STT keys. It sends typed payloads and renders backend-owned results. The backend is the source of truth for product retrieval, filtering, cart operations, voice adapters, and WebSocket events.

## Current Public Demo Backend

```text
HTTP API: https://continually-replication-allowing-editions.trycloudflare.com/
WebSocket: wss://continually-replication-allowing-editions.trycloudflare.com/ws/chat
```

The Cloudflare URL is a temporary tunnel endpoint. If it changes, update `client/app/src/main/java/com/example/shopguideagent/config/AppConfig.kt` and rebuild the APK.

## Client Build

```bash
cd client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
./gradlew :app:testDebugUnitTest --no-daemon
./gradlew :app:assembleDebug --no-daemon
```

APK output:

```text
client/app/build/outputs/apk/debug/app-debug.apk
```

For Windows local builds, use `client/gradlew.bat`. If a Chinese-path workspace causes Android/JUnit classpath issues, set `SHOPGUIDE_ANDROID_BUILD_DIR` to an ASCII path before running Gradle.

## Server Build And Run

The project uses the existing remote vLLM/conda-derived host runtime, not a container image.

```bash
bash server/scripts/setup_backend_env.sh
bash server/scripts/start_backend.sh
```

The root `start_backend.sh` is kept as a compatibility wrapper for existing remote operations.

Run backend tests:

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
```

Main backend entrypoint:

```text
server/backend/app/main.py
uvicorn backend.app.main:app
```

Host-runtime smoke on a non-live port:

```bash
HOST=127.0.0.1 PORT=18083 USE_EMBEDDING=0 TTS_ENABLED=false STT_ENABLED=false \
  ARK_API_KEY= LLM_API_KEY= bash server/scripts/start_backend.sh
curl -fsS http://127.0.0.1:18083/health
```

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

Important WebSocket request types:

```text
user_message
product_followup   # must include focus_product_id
cart_action
```

Important stream events include `text_delta`, `product_item`, `recommendations_ready`, `cart_update`, `audio_delta`, `audio_done`, `done`, and `error`.

## Documentation

- Architecture: `docs/architecture.md`
- API contract: `docs/api-contract.md`
- Realtime protocol: `docs/realtime-protocol.md`
- Development runbook: `docs/runbook.md`
- Stage 0/01 acceptance tests: `docs/acceptance-tests.md`
- Runtime environment: `deploy/README.md` and `deploy/env.example`
- Client docs: `docs/client/`
- Server docs: `docs/server/`
- Product and competition docs: `docs/product/` and root-level docs under `docs/`
