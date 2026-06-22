#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$SERVER_DIR/.." && pwd)"
SEED_PYTHON="${SEED_PYTHON:-$REPO_ROOT/env/venv_vllm_cu128/bin/python}"
BACKEND_VENV="${BACKEND_VENV:-$REPO_ROOT/env/venv_shopguide_backend}"

if [[ ! -x "$SEED_PYTHON" ]]; then
  echo "Seed Python not found: $SEED_PYTHON" >&2
  echo "Set SEED_PYTHON to a Python 3.12 interpreter." >&2
  exit 1
fi

"$SEED_PYTHON" -m venv "$BACKEND_VENV"
"$BACKEND_VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$BACKEND_VENV/bin/python" -m pip install -r "$SERVER_DIR/requirements.txt"

echo "Backend environment ready: $BACKEND_VENV"
echo "Run tests with:"
echo "  cd $SERVER_DIR && $BACKEND_VENV/bin/python -m pytest -q"
