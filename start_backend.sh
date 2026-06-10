#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# SoulDance ShopGuide Backend — 启动脚本（含 Android 支持）
# ============================================================
#
# 使用方式:
#   ./start_backend.sh              # 默认 localhost:8000
#   HOST=0.0.0.0 PORT=8000 ./start_backend.sh  # 允许局域网/Android 访问
#
# 环境变量（按需设置）:
#   BACKEND_VENV          — FastAPI 后端虚拟环境，默认 env/venv_shopguide_backend
#   LLM_PROVIDER          — LLM 后端: doubao (默认) | deepseek | custom
#   LLM_API_KEY           — LLM API Key（deepseek 时即 DeepSeek API Key）
#   LLM_MODEL             — 模型名（deepseek 默认 deepseek-chat）
#   ARK_API_KEY           — 豆包 API Key（LLM_PROVIDER=doubao 时使用）
#   SERVER_BASE_URL       — Android 端访问的完整地址，如 http://192.168.1.100:8000
#   SHOPGUIDE_SESSION_DIR — session 持久化目录
#   SHOPGUIDE_CART_PATH   — 购物车持久化文件路径

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
BACKEND_VENV="${BACKEND_VENV:-$ROOT/env/venv_shopguide_backend}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# 激活 Python 虚拟环境
if [ ! -x "$BACKEND_VENV/bin/python3" ]; then
    echo "❌ 找不到后端 Python 环境: $BACKEND_VENV" >&2
    echo "   请先运行: bash scripts/setup_backend_env.sh" >&2
    exit 1
fi
export PATH="$BACKEND_VENV/bin:$PATH"
export VIRTUAL_ENV="$BACKEND_VENV"

# Android/local debug goes through the app's configured base URL
# (for example 10.0.2.2:8000 via a local SSH tunnel), so keep asset URLs
# relative unless the caller explicitly exports SERVER_BASE_URL.
export SERVER_BASE_URL="${SERVER_BASE_URL:-}"

# ========== 端口清理：自动释放被占用的端口 ==========
PORT="${PORT:-8000}"
PID_USING_PORT="$(
    lsof -ti ":$PORT" 2>/dev/null \
        || ss -tlnp 2>/dev/null \
            | grep ":$PORT " \
            | awk '{print $7}' \
            | cut -d',' -f2 \
            | cut -d'=' -f2 \
            | head -1 \
        || true
)"
if [ -n "$PID_USING_PORT" ]; then
    CMDLINE=$(cat /proc/$PID_USING_PORT/cmdline 2>/dev/null | tr '\0' ' ' || echo "unknown")
    if echo "$CMDLINE" | grep -q "adb-bridge"; then
        echo ">>> 检测到 adb-bridge 的残留进程占用 $PORT 端口 (PID: $PID_USING_PORT)，正在清理..."
        kill -9 "$PID_USING_PORT" 2>/dev/null
        sleep 1
    else
        echo "⚠️  警告: $PORT 端口被进程 PID $PID_USING_PORT 占用"
        echo "    命令: $CMDLINE"
        echo "    请手动确认后重试: kill -9 $PID_USING_PORT"
        exit 1
    fi
fi
# ====================================================

LLM_LABEL="${LLM_PROVIDER:-backend runtime config/.env}"
echo "============================================"
echo " SoulDance ShopGuide Backend"
echo " Python:   $(python3 --version)"
echo " Venv:     ${VIRTUAL_ENV}"
echo " Listen:   http://${HOST}:${PORT}"
echo " Health:   http://${HOST}:${PORT}/health"
echo " WS Chat:  ws://${HOST}:${PORT}/ws/chat"
echo " LLM:      ${LLM_LABEL}"
echo "============================================"

cd "$ROOT"
exec python3 -m uvicorn backend.app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info \
    --timeout-keep-alive 120 \
    --ws-ping-interval 20 \
    --ws-ping-timeout 10 \
    --limit-concurrency 20
