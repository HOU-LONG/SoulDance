# FunASR STT 服务部署说明

本文档说明如何在本地/服务器部署 FunASR 语音识别服务，供 `backend/app/stt_adapter.py` 调用。

## 环境准备

确保已激活后端虚拟环境：

```bash
cd /home/huadabioa/houlong/SoulDance
source env/venv_shopguide_backend/bin/activate
```

安装依赖：

```bash
pip install funasr modelscope python-multipart
```

`python-multipart` 是 FastAPI `UploadFile` 必需的依赖。

## 启动服务

### 默认参数

```bash
PORT=18090 bash scripts/start_stt.sh
```

默认使用 `paraformer-zh` 模型，监听 `0.0.0.0:18090`，使用 GPU 0。

### 常用环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `18090` | HTTP 服务端口 |
| `HOST` | `0.0.0.0` | 监听地址 |
| `STT_MODEL` | `paraformer-zh` | FunASR 模型名称 |
| `STT_DEVICE` | `0` | GPU 编号；设 `-1` 使用 CPU |

示例：

```bash
PORT=18090 STT_MODEL=sensevoice-small STT_DEVICE=3 bash scripts/start_stt.sh
```

## 健康检查

```bash
curl -fsS http://127.0.0.1:18090/health
```

期望返回：

```json
{"status": "ok", "model": "paraformer-zh", "provider": "funasr"}
```

## 测试识别

```bash
curl -X POST http://127.0.0.1:18090/asr \
  -F audio=@sample.wav
```

期望返回：

```json
{"text": "推荐防晒霜", "language": "zh"}
```

## 模型缓存

FunASR 首次启动会自动从 ModelScope 下载模型，缓存到 `~/.cache/modelscope/hub/`。如果服务器无外网，请提前在有外网的机器下载后复制到目标机器对应路径。

## 常见问题

### `ModuleNotFoundError: No module named 'funasr'`

在正确的虚拟环境中安装：

```bash
env/venv_shopguide_backend/bin/pip install funasr modelscope python-multipart
```

### 显存不足

换用更小的模型或 CPU：

```bash
STT_MODEL=sensevoice-small STT_DEVICE=-1 bash scripts/start_stt.sh
```

### 路由不一致

如果 FunASR 服务实际暴露的路由不是 `/asr`，请修改 `backend/app/stt_adapter.py` 中的 `_transcribe_funasr` 方法里的 URL。
