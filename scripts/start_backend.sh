#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_VENV="${BACKEND_VENV:-$ROOT/env/venv_shopguide_backend}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-18080}"

if [[ ! -x "$BACKEND_VENV/bin/uvicorn" ]]; then
  echo "Backend venv is missing uvicorn: $BACKEND_VENV" >&2
  echo "Create it first with: scripts/setup_backend_env.sh" >&2
  exit 1
fi

export ARK_BASE_URL="${ARK_BASE_URL:-https://ark.cn-beijing.volces.com/api/v3/}"
export ARK_MODEL="${ARK_MODEL:-ep-20260514111645-lmgt2}"
export EMBEDDING_MODEL_DIR="${EMBEDDING_MODEL_DIR:-model/bge-small-zh-v1.5}"
export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-cuda:0}"
export USE_EMBEDDING="${USE_EMBEDDING:-1}"

cd "$ROOT"
exec "$BACKEND_VENV/bin/uvicorn" backend.app.main:app --host "$HOST" --port "$PORT"
