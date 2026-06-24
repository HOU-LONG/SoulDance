# Stage 0/01 Acceptance Tests

Run these checks before considering the monorepo baseline complete.

## Release Acceptance CLI

Run the full post-gap-fill release matrix from the remote source-of-truth checkout:

```bash
cd /home/huadabioa/houlong/SoulDance
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --list-checks
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py
```

Acceptance matrix（按执行顺序）：

| check | 用途 | 依赖 |
|---|---|---|
| `backend-tests` | `pytest -q`，覆盖 30+ 测试文件 | — |
| `eval-runner` | Fake LLM 跑 `core.json` 5 个场景，CI 离线烟囱 | — |
| `eval-full` | 真 LLM 跑 `data/eval/` 全部 22+ 场景，门槛 ≥ 80% | `.env` 里 `LLM_API_KEY` / `ARK_API_KEY`，未配则自动 skip |
| `android-build` | `:app:testDebugUnitTest` + `:app:assembleDebug` | JDK / Android SDK |
| `script-syntax` | `bash -n` 所有启动脚本 | — |
| `host-health-smoke` | 启动 backend 在非生产端口，curl `/health` | — |

For targeted verification while iterating:

```bash
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --dry-run
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check backend-tests --check eval-runner --check script-syntax
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check eval-full
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

ShopGuide RAG 评测 pipeline 已扩展为 22 个场景 + 5 个分类文件，覆盖答辩需要的 20 类场景，输出结构化 step 级断言。

### 快速烟囱（fake LLM，离线 CI 友好）

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
../env/venv_shopguide_backend/bin/python scripts/run_eval.py --scenarios ../data/eval/core.json --fake-llm
```

Expected: all pytest tests pass and the eval report shows `"failed": 0` on the 5 baseline scenarios.

### 全场景真 LLM 评测

需要 `.env` 里配置 `LLM_API_KEY` 或 `ARK_API_KEY`。

```bash
cd server
../env/venv_shopguide_backend/bin/python scripts/run_eval.py --scenarios ../data/eval/ --min-pass-rate 0.80
```

Expected: 通过率 ≥ 80%。当前基线 **23/27 = 85%**。低于门槛返回 `exit 1` 阻断 release。

### 场景分类（`data/eval/` 下）

| 文件 | 场景数 | 覆盖类别 |
|---|---|---|
| `core.json` | 5 | 历史保留的 baseline（明确推荐 / 预算 / 排除酒精 / 加购 / 订单完整路径） |
| `recommend.json` | 8 | 明确推荐 / 模糊推荐 / 预算上下限 / 指定品牌 / 排除品牌 / 排除成分 / 更便宜替代 |
| `multi_turn.json` | 5 | 多轮补充条件 / 取消旧条件 / 商品追问 / 商品比较 / 指代消解 |
| `edge.json` | 3 | 无匹配 / 非法类目 / 重复加购 |
| `cart_order.json` | 3 | 购物车 CRUD / 订单状态机三阶段 / 订单幂等确认 |
| `failure.json` | 3 | LLM 超时 / LLM 幻觉拦截 / WebSocket 断线重连 |

### 评测 DSL 字段速查

- 检索/排序断言：`expected_product_ids` / `forbidden_product_ids` / `expect_product_ids_subset_of` / `expected_brands` / `forbidden_brands` / `price_min` / `price_max` / `forbid_terms` / `forbidden_terms_in_explanation`
- 路径断言：`expect_clarification` / `expect_no_match` / `expect_comparison` / `expect_error_kind`（取值 `llm_timeout` / `stt_unavailable` / 等）
- 购物车 / 订单：`expect_cart_quantity: {product_id: quantity}` / `expect_order_status`（取值 `address_required` / `awaiting_confirmation` / `completed`）
- 多 step：`steps: [{action, message, payload, expect, bind}]`，`bind: {var: selector}` + `${var}` 占位符在后续 step 引用
- Fault 注入：scenario 顶层 `fault: llm_timeout | stt_unavailable | llm_hallucination`

### 消融实验

```bash
cd server
../env/venv_shopguide_backend/bin/python scripts/run_ablation.py --scenarios ../data/eval/recommend.json
```

产出 `data/eval/ablation_<timestamp>_{detail,summary}.csv`。9 个配置 × 8 场景，约 2 分钟跑完。CSV 字段：`config / scenario / passed / recall@5 / ndcg@5 / predicted_top`。

参数：
- `--dense-weights 0.3,0.5,0.65,0.8`（weighted 策略 α 值列表）
- `--rrf-ks 30,60,100`（rrf 策略 k 值列表）
- `--tag recommend`（按 scenario tag 筛选）

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
