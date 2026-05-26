# Qwen3-TTS 服务使用指南

本项目在 `mix_A100` 上用 vLLM-Omni 提供 Qwen3-TTS 服务。

## 目录

- 项目目录: `/home/huadabioa/houlong/SoulDance`
- Python 运行环境: `/home/huadabioa/houlong/SoulDance/env/venv_vllm_cu128`
- GCC/libstdc++ 运行环境: `/home/huadabioa/houlong/SoulDance/env/conda_gcc12`
- 模型目录: `/home/huadabioa/houlong/SoulDance/model/qwen3_tts`
- 部署配置: `/home/huadabioa/houlong/SoulDance/qwen3_tts_local.yaml`
- 启动脚本: `/home/huadabioa/houlong/SoulDance/start_qwen.sh`
- 常用日志: `/home/huadabioa/houlong/SoulDance/logs/qwen3_tts_vllm_omni.log`

根目录下还有两个兼容软链：

- `/home/huadabioa/houlong/SoulDance/venv_vllm_cu128 -> env/venv_vllm_cu128`
- `/home/huadabioa/houlong/SoulDance/conda_gcc12 -> env/conda_gcc12`

这两个不是环境副本，几乎不占空间。保留它们可以兼容旧脚本、旧 shebang、以及第三方包生成的绝对路径缓存。

## 启动

默认使用 GPU 2 和端口 18880：

```bash
cd /home/huadabioa/houlong/SoulDance
GPU=2 PORT=18880 nohup ./start_qwen.sh > logs/qwen3_tts_vllm_omni.log 2>&1 &
```

如果需要换端口：

```bash
cd /home/huadabioa/houlong/SoulDance
GPU=2 PORT=8000 nohup ./start_qwen.sh > logs/qwen3_tts_vllm_omni_8000.log 2>&1 &
```

`start_qwen.sh` 会先检查目标端口是否已经被占用，避免重复启动同一个端口的服务。

## 检查状态

```bash
curl -fsS http://127.0.0.1:18880/health
curl -fsS http://127.0.0.1:18880/v1/models
```

检查进程和 GPU 占用：

```bash
pgrep -af "vllm_omni.entrypoints.cli.main serve|StageEngineCoreProc"
nvidia-smi
```

如果服务在另一台机器调用，把 `127.0.0.1` 换成服务器可访问的 IP 或域名。

## 调用 TTS

```bash
cd /home/huadabioa/houlong/SoulDance

curl -sS -X POST http://127.0.0.1:18880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EMPTY" \
  -d '{
    "model": "qwen3-tts",
    "input": "Hello, this is a Qwen3 TTS test.",
    "task_type": "VoiceDesign",
    "instructions": "A calm, clear female narrator voice.",
    "response_format": "wav",
    "stream": false
  }' \
  --output logs/qwen3_tts_test.wav

file logs/qwen3_tts_test.wav
```

正常结果应该是 `RIFF ... WAVE audio ... 24000 Hz` 之类的 wav 文件信息。

## 停止

先看服务主进程：

```bash
pgrep -af "vllm_omni.entrypoints.cli.main serve"
```

停止某一个服务：

```bash
kill <PID>
```

停止当前用户下所有 Qwen3-TTS vLLM-Omni 服务：

```bash
pkill -f "vllm_omni.entrypoints.cli.main serve .*qwen3_tts"
```

## 不要删除

这些路径是运行必需的：

```text
/home/huadabioa/houlong/SoulDance/env/venv_vllm_cu128
/home/huadabioa/houlong/SoulDance/env/conda_gcc12
/home/huadabioa/houlong/SoulDance/vllm-omni-main
/home/huadabioa/houlong/SoulDance/model/qwen3_tts
/home/huadabioa/houlong/SoulDance/qwen3_tts_local.yaml
/home/huadabioa/houlong/SoulDance/start_qwen.sh
```

也建议保留这两个兼容软链：

```text
/home/huadabioa/houlong/SoulDance/venv_vllm_cu128
/home/huadabioa/houlong/SoulDance/conda_gcc12
```

`env/conda_gcc12` 运行时仍然需要，因为编译好的 vLLM 扩展会加载里面的 `libstdc++.so.6` 和 `libgcc_s.so.1`。

## 常见问题

### 端口已经占用

如果看到：

```text
Port 18880 is already in use. The Qwen3-TTS service may already be running.
```

先检查：

```bash
curl -fsS http://127.0.0.1:18880/health
ss -ltnp | grep 18880
```

如果 `/health` 正常，说明服务已经在跑，不需要再启动。

### FlashInfer JIT 缓存引用旧环境路径

如果启动时报错类似：

```text
ninja: error: '/home/huadabioa/houlong/SoulDance/venv_vllm_cu128/.../flashinfer/data/csrc/sampling.cu', missing
RuntimeError: Ninja build failed
```

这通常是移动环境后，`.cache/flashinfer` 里的 JIT 编译缓存还记着旧绝对路径。处理方法：

```bash
cd /home/huadabioa/houlong/SoulDance
mv .cache/flashinfer .cache/flashinfer.bak.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
ln -sfn env/venv_vllm_cu128 venv_vllm_cu128
ln -sfn env/conda_gcc12 conda_gcc12
GPU=2 PORT=18880 nohup ./start_qwen.sh > logs/qwen3_tts_vllm_omni.log 2>&1 &
```

也可以先单独验证 FlashInfer 采样模块能否编译加载：

```bash
cd /home/huadabioa/houlong/SoulDance
env PATH="$PWD/env/venv_vllm_cu128/bin:$PATH" \
  CUDA_VISIBLE_DEVICES=2 \
  CUDA_DEVICE_ORDER=PCI_BUS_ID \
  FLASHINFER_WORKSPACE_BASE="$PWD" \
  LD_LIBRARY_PATH="$PWD/env/conda_gcc12/lib:/usr/local/cuda-12.8/lib64:$PWD/env/venv_vllm_cu128/lib/python3.12/site-packages/torch/lib:$LD_LIBRARY_PATH" \
  env/venv_vllm_cu128/bin/python - <<'PY'
import flashinfer.sampling as sampling
print("sampling_module_ok", sampling.get_sampling_module())
PY
```

### Shell 提示符出现双括号

`((venv_vllm_cu128) ) (base)` 一般是因为同时激活了 Python venv 和 conda `base`，或者重复 source 了 venv 的 `activate`。这只是提示符显示问题，不一定影响服务。

清理当前 shell：

```bash
deactivate 2>/dev/null || true
conda deactivate 2>/dev/null || true
```

重新开一个干净终端再启动服务也可以。
