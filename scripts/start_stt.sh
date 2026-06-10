#!/usr/bin/env bash
set -euo pipefail

# FunASR STT 本地服务启动脚本
# 用法：
#   PORT=18090 bash scripts/start_stt.sh
#   PORT=18090 STT_MODEL=sensevoice-small bash scripts/start_stt.sh

PORT="${PORT:-18090}"
HOST="${HOST:-0.0.0.0}"
MODEL="${STT_MODEL:-paraformer-zh}"
DEVICE="${STT_DEVICE:-0}"

echo "Starting FunASR STT service on ${HOST}:${PORT} with model ${MODEL}..."

python - <<PY
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
