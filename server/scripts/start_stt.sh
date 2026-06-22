#!/usr/bin/env bash
set -euo pipefail

# FunASR STT local service launcher.
# Usage:
#   PORT=18090 bash scripts/start_stt.sh
#   PORT=18090 STT_MODEL=sensevoice-small bash scripts/start_stt.sh

SERVER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$SERVER_DIR/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/env/venv_shopguide_backend/bin/python"
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
    if [ -x "$VENV_PYTHON" ]; then
        PYTHON_BIN="$VENV_PYTHON"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python)"
    else
        echo "No usable Python found for STT service" >&2
        exit 1
    fi
fi

PORT="${PORT:-18090}"
HOST="${HOST:-0.0.0.0}"
MODEL="${STT_MODEL:-paraformer-zh}"
DEVICE="${STT_DEVICE:-0}"

echo "Starting FunASR STT service on ${HOST}:${PORT} with model ${MODEL} using ${PYTHON_BIN}..."

"$PYTHON_BIN" - <<PY
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()
model = AutoModel(
    model="${MODEL}",
    device="cuda:${DEVICE}" if int("${DEVICE}") >= 0 else "cpu",
    disable_update=True,
)


@app.post("/asr")
async def asr(audio: UploadFile = File(...)):
    data = await audio.read()
    res = model.generate(
        input=data,
        batch_size_s=300,
        language="zh",
    )
    text = ""
    if res and len(res) > 0 and isinstance(res[0], dict):
        text = rich_transcription_postprocess(res[0].get("text", ""))
    return JSONResponse({"text": text, "language": "zh"})


@app.get("/health")
def health():
    return {"status": "ok", "model": "${MODEL}", "provider": "funasr"}


uvicorn.run(app, host="${HOST}", port=int("${PORT}"))
PY
