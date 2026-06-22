#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$SERVER_DIR/.." && pwd)"
BACKEND_VENV="${BACKEND_VENV:-$REPO_ROOT/env/venv_shopguide_backend}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

if [[ ! -x "$BACKEND_VENV/bin/python3" ]]; then
    echo "Backend Python environment not found: $BACKEND_VENV" >&2
    echo "Create it first with: bash server/scripts/setup_backend_env.sh" >&2
    exit 1
fi

export PATH="$BACKEND_VENV/bin:$PATH"
export VIRTUAL_ENV="$BACKEND_VENV"
export PYTHONPATH="$SERVER_DIR${PYTHONPATH:+:$PYTHONPATH}"
export SERVER_BASE_URL="${SERVER_BASE_URL:-}"

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
if [[ -n "$PID_USING_PORT" ]]; then
    CMDLINE=$(cat /proc/$PID_USING_PORT/cmdline 2>/dev/null | tr '\0' ' ' || echo "unknown")
    if echo "$CMDLINE" | grep -q "adb-bridge"; then
        echo "Cleaning stale adb-bridge process on port $PORT (PID: $PID_USING_PORT)..."
        kill -9 "$PID_USING_PORT" 2>/dev/null || true
        sleep 1
    else
        echo "Port $PORT is already used by PID $PID_USING_PORT" >&2
        echo "Command: $CMDLINE" >&2
        exit 1
    fi
fi

LLM_LABEL="${LLM_PROVIDER:-backend runtime config/.env}"
echo "============================================"
echo " SoulDance ShopGuide Backend"
echo " Python:   $(python3 --version)"
echo " Venv:     ${VIRTUAL_ENV}"
echo " Server:   ${SERVER_DIR}"
echo " Listen:   http://${HOST}:${PORT}"
echo " Health:   http://${HOST}:${PORT}/health"
echo " WS Chat:  ws://${HOST}:${PORT}/ws/chat"
echo " LLM:      ${LLM_LABEL}"
echo "============================================"

cd "$SERVER_DIR"
exec python3 -m uvicorn backend.app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info \
    --timeout-keep-alive 120 \
    --ws-ping-interval 20 \
    --ws-ping-timeout 10 \
    --limit-concurrency 20
