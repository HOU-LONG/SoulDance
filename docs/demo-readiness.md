# SoulDance Demo Readiness

This document is the handoff checklist after the gap-fill A/B/C plans are implemented. It is not a new feature roadmap; it proves the current SQLite + FastAPI + Android + Cloudflare path is ready to demo.

## Automated Gate

Run from the remote source-of-truth checkout:

```bash
cd /home/huadabioa/houlong/SoulDance
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --list-checks
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py
```

For quicker preflight while iterating:

```bash
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --dry-run
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check backend-tests --check eval-runner --check script-syntax
```

The full matrix covers:

- `backend-tests`: all backend pytest checks.
- `eval-runner`: fixed scenario set at `data/eval/shopguide_core_scenarios.json`; expected `failed=0` in the report.
- `android-build`: `:app:testDebugUnitTest` and `:app:assembleDebug` with remote Android Studio JBR.
- `script-syntax`: shell syntax checks for launch scripts and Gradle wrapper.
- `host-health-smoke`: starts backend on a non-live port and verifies `/health`.

## Manual Device Gate

Use Cloudflare tunnel as the default real-device route. Do not switch the normal demo path to `adb reverse` unless the tunnel is unavailable and the change is explicitly called out in the demo notes.

1. Start backend on `mix_A100`:

```bash
cd /home/huadabioa/houlong/SoulDance
bash server/scripts/start_backend.sh
curl -fsS http://127.0.0.1:8000/health
```

2. Start or refresh the Cloudflare tunnel to backend port `8000`.

3. Update the Android endpoint only if the temporary Cloudflare domain changed:

```text
client/app/src/main/java/com/example/shopguideagent/config/AppConfig.kt
```

4. Rebuild APK:

```bash
cd /home/huadabioa/houlong/SoulDance/client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export ANDROID_SDK_ROOT=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
./gradlew :app:testDebugUnitTest :app:assembleDebug --no-daemon
```

APK path:

```text
/home/huadabioa/houlong/SoulDance/client/app/build/outputs/apk/debug/app-debug.apk
```

## Demo Script

Use one clean session id for the demo and avoid mutating production secrets.

1. Chat: ask for a constrained recommendation, for example `Recommend a commuter sunscreen under 150, avoid strong alcohol smell`.
2. Product card: verify one primary product appears first, with at most a small number of alternatives.
3. Product follow-up: open the product BottomSheet and ask around the current product. Confirm the request path carries `focus_product_id`.
4. Cart: add the primary product, change quantity, and verify cart badge and total update.
5. Checkout: start checkout, choose address, show preview, confirm with server-provided `confirmation_token`.
6. Voice smoke: record a short voice request and verify ASR text appears; if TTS is enabled, verify audio starts and can be stopped.
7. Reconnect/error: briefly interrupt the network or refresh tunnel and confirm the app shows an error/reconnect state instead of crashing.

## Demo Evidence To Record

Before handoff, record these values in the release note or issue comment:

- Git commit hash.
- Cloudflare domain used for the APK build.
- APK path and build timestamp.
- `run_release_acceptance.py` command and exit status.
- Eval runner total/passed/failed counts.
- Manual device checklist result.
- Any skipped step and why.

## Failure Rule

If a gate fails, keep the fix narrow:

- Automated failure: preserve the failing command and add/adjust the smallest regression test.
- Manual device failure: write exact device, tunnel domain, APK path, screen, and user action.
- Do not add new features while fixing release readiness failures.
