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


## Release and Demo Readiness

Use this gate after implementing the gap-fill A/B/C plans and before a handoff or live demo:

```bash
cd /home/huadabioa/houlong/SoulDance
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --list-checks
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py
```

The demo checklist is tracked in `docs/demo-readiness.md`. Cloudflare tunnel remains the preferred real-device path; use `adb reverse` only as an explicitly noted fallback.

## Cloudflare Device Debugging

The preferred real-device path is Cloudflare tunnel access, not `adb reverse`.

1. Start the backend on the remote host.
2. Start or refresh the Cloudflare tunnel to the backend port.
3. Update `client/app/src/main/java/com/example/shopguideagent/config/AppConfig.kt` if the tunnel domain changed.
4. Rebuild the APK and install it on the device.

## 故障排查

### "连接中断，请重试"
- 先确认后端存活：`curl http://127.0.0.1:8000/api/products?limit=1`
- 后端正常但客户端超时（>60s）→ 检查 LLM provider 延迟；DeepSeek v4 的 `plan_tool` + `stream_response` 两轮调用合计可能 20-40s
- Android 超时阈值：`STREAM_TIMEOUT_MILLIS = 60_000L`（`ChatViewModel.kt`）
- 后端首 chunk 超时：`DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS = 25.0`（`agent.py`）

### LLM 回复模板化（理解/结论/主推标签）
- 确认 `prompts/v1/response.txt` 为自然回复版本（不含"必须按以下顺序输出"）
- 后端改过代码后需重启（prompt 已支持热更新，无需重启）：
  ```bash
  kill $(ps aux | grep "uvicorn.*8000" | grep -v grep | awk '{print $2}') 2>/dev/null
  sleep 2 && cd server && nohup python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --log-level info --timeout-keep-alive 120 --ws-ping-interval 20 --ws-ping-timeout 10 --limit-concurrency 20 > /tmp/souldance-backend.log 2>&1 &
  ```

### 商品查询被拒答（"我没太抓到你的购物需求"）
- 旧规则栈残留；确认 `tool_planner.txt` 和 `chitchat.txt` 为最新版本 + 重启后端

### 复合需求（情绪+购物）只聊天不推荐
- 确认 `tool_planner.txt` 第 6 条优先级（复合需求→chitchat）存在
- chitchat 流自动注入 catalog top-5，LLM 会用真实 ID 生成锚点
