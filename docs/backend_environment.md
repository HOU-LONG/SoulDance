# ShopGuide Backend Environment

本项目现在明确拆分两个运行环境，避免后端 RAG 依赖污染 Qwen3-TTS / vLLM-Omni。

## 环境分工

```text
env/venv_shopguide_backend  后端 API、RAG、测试、smoke demo
env/venv_vllm_cu128         Qwen3-TTS / vLLM-Omni 服务
env/conda_gcc12             vLLM-Omni 运行时 libstdc++ / libgcc
```

后端通过 HTTP 调用 TTS 服务，不和 vLLM-Omni 共用 Python site-packages。

## 创建后端环境

```bash
cd /home/huadabioa/houlong/SoulDance
bash scripts/setup_backend_env.sh
```

默认会使用：

```text
SEED_PYTHON=env/venv_vllm_cu128/bin/python
BACKEND_VENV=env/venv_shopguide_backend
```

可以按需覆盖：

```bash
SEED_PYTHON=/path/to/python3.12 BACKEND_VENV=env/venv_shopguide_backend bash scripts/setup_backend_env.sh
```

## 后端命令

测试：

```bash
env/venv_shopguide_backend/bin/python -m pytest tests/test_agent_core.py tests/test_api.py -v
```

检查 embedding：

```bash
env/venv_shopguide_backend/bin/python scripts/check_embedding.py
```

启动后端：

```bash
export ARK_API_KEY="your-runtime-key"
bash scripts/start_backend.sh
```

如果只想快速验证 API，不加载 dense embedding：

```bash
USE_EMBEDDING=0 ARK_API_KEY="$ARK_API_KEY" bash scripts/start_backend.sh
```

## TTS 服务

TTS 仍使用：

```bash
GPU=2 PORT=18880 nohup ./start_qwen.sh > logs/qwen3_tts_vllm_omni.log 2>&1 &
```

更多内容见：

```text
docs/qwen3_tts_usage.md
```

