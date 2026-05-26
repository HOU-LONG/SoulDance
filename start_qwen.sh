#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/huadabioa/houlong/SoulDance"
VENV="$ROOT/env/venv_vllm_cu128"
MODEL="$ROOT/model/qwen3_tts"
DEPLOY_CONFIG="$ROOT/qwen3_tts_local.yaml"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-18880}"
GPU="${GPU:-2}"

mkdir -p "$ROOT/logs" "$ROOT/.cache"

export PATH="$VENV/bin:$PATH"
export CUDA_VISIBLE_DEVICES="$GPU"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export FLASHINFER_WORKSPACE_BASE="$ROOT"
export LD_LIBRARY_PATH="$ROOT/env/conda_gcc12/lib:/usr/local/cuda-12.8/lib64:$VENV/lib/python3.12/site-packages/torch/lib:${LD_LIBRARY_PATH:-}"

if command -v ss >/dev/null 2>&1 && ss -ltn | awk '{print $4}' | grep -Eq "(:|\\])${PORT}$"; then
  echo "Port ${PORT} is already in use. The Qwen3-TTS service may already be running."
  echo "Check: curl http://127.0.0.1:${PORT}/health"
  exit 0
fi

cd "$ROOT/vllm-omni-main"
exec "$VENV/bin/python" -m vllm_omni.entrypoints.cli.main serve "$MODEL" \
  --omni \
  --deploy-config "$DEPLOY_CONFIG" \
  --host "$HOST" \
  --port "$PORT" \
  --trust-remote-code \
  --served-model-name qwen3-tts \
  --task-type VoiceDesign
