# Development Runbook

## Remote Primary Workspace

Use the remote checkout as the source of truth:

```bash
ssh mix_A100
cd /home/huadabioa/houlong/SoulDance
```

Current Stage 0/01 branch:

```bash
git status --short --branch
```

## Backend Host Runtime

The current project uses the existing vLLM/conda-derived remote environment, not a Docker image.

Default runtime paths:

```text
env/venv_vllm_cu128/bin/python       seed Python for setup_backend_env.sh
env/conda_gcc12/bin/python           alternate conda-style Python if needed
env/venv_shopguide_backend/bin/python backend FastAPI runtime
```

Setup:

```bash
bash server/scripts/setup_backend_env.sh
```

If the seed runtime changes:

```bash
SEED_PYTHON=/home/huadabioa/houlong/SoulDance/env/conda_gcc12/bin/python \
  bash server/scripts/setup_backend_env.sh
```

Run live backend:

```bash
bash server/scripts/start_backend.sh
```

Compatibility wrapper:

```bash
bash start_backend.sh
```

Health:

```bash
curl -fsS http://127.0.0.1:8000/health
```

Tests:

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
```

Host-runtime smoke on a non-live port:

```bash
HOST=127.0.0.1 PORT=18083 USE_EMBEDDING=0 TTS_ENABLED=false STT_ENABLED=false \
  ARK_API_KEY= LLM_API_KEY= bash server/scripts/start_backend.sh
curl -fsS http://127.0.0.1:18083/health
```

## Android

Build on `mix_A100`. The remote default Java is 11, which is too old for the current Gradle plugin; use the Android Studio bundled JBR and set the SDK roots explicitly:

```bash
cd /home/huadabioa/houlong/SoulDance/client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export ANDROID_SDK_ROOT=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
./gradlew :app:testDebugUnitTest :app:assembleDebug --no-daemon
```

APK output:

```text
/home/huadabioa/houlong/SoulDance/client/app/build/outputs/apk/debug/app-debug.apk
```

## Eval Runner

Run the fixed scenario set against the in-process backend:

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python scripts/run_eval.py --scenarios ../data/eval/shopguide_core_scenarios.json
```

Expected output: JSON report with `"failed": 0`.

The scenario file is tracked at `data/eval/shopguide_core_scenarios.json`. Update expectations there when product facts change; do not weaken production constraints to make a scenario pass.

## Cloudflare Device Debugging

The preferred real-device path is Cloudflare tunnel access, not `adb reverse`.

1. Start the backend on the remote host.
2. Start or refresh the Cloudflare tunnel to the backend port.
3. Update `client/app/src/main/java/com/example/shopguideagent/config/AppConfig.kt` if the tunnel domain changed.
4. Rebuild the APK and install it on the device.
