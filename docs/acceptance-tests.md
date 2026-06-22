# Stage 0/01 Acceptance Tests

Run these checks before considering the monorepo baseline complete.

## Release Acceptance CLI

Run the full post-gap-fill release matrix from the remote source-of-truth checkout:

```bash
cd /home/huadabioa/houlong/SoulDance
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --list-checks
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py
```

For targeted verification while iterating:

```bash
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --dry-run
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check backend-tests --check eval-runner --check script-syntax
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check android-build
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check host-health-smoke
```

Expected: selected checks exit `0`. The full matrix stops at the first failing check.

## Structure

```bash
test -d client
test -d server
test -d docs
test -d deploy
test -f deploy/env.example
test -f deploy/README.md
```

## Backend

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
```

Expected: all backend tests pass.

## Eval Runner

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
../env/venv_shopguide_backend/bin/python scripts/run_eval.py --scenarios ../data/eval/shopguide_core_scenarios.json
```

Expected: all pytest tests pass and the eval report shows `"failed": 0`.

## Android

```bash
cd client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export ANDROID_SDK_ROOT=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
./gradlew :app:testDebugUnitTest :app:assembleDebug --no-daemon
```

Expected: unit tests and debug APK build pass.

APK path:

```text
client/app/build/outputs/apk/debug/app-debug.apk
```

## Scripts

```bash
for script in start_backend.sh server/scripts/setup_backend_env.sh server/scripts/start_backend.sh server/scripts/start_stt.sh client/gradlew; do
  bash -n "$script"
done
```

Expected: syntax checks pass.

## Host Runtime Health

Use a non-live port so verification does not interfere with the Cloudflare-backed backend:

```bash
HOST=127.0.0.1 PORT=18083 USE_EMBEDDING=0 TTS_ENABLED=false STT_ENABLED=false \
  ARK_API_KEY= LLM_API_KEY= bash server/scripts/start_backend.sh
curl -fsS http://127.0.0.1:18083/health
```

Expected: `/health` returns HTTP 200 with `status=ok`. Stop the smoke process after the check.

## Contract Guards

- `/health` exists.
- `/ws/chat` exists.
- WebSocket request types include `user_message`, `product_followup`, and `cart_action`.
- `product_followup` requests include `focus_product_id`.
- Android source contains no LLM, ASR, or TTS provider secrets.
