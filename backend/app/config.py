from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 自动加载项目根目录的 .env 文件。
# 已存在的环境变量不会被覆盖（env vars > .env）。
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)


class Settings(BaseModel):
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])
    dataset_dir: str = "ecommerce_agent_dataset"

    # LLM provider: "doubao" (default) | "deepseek" | "custom"
    llm_provider: str = "doubao"
    llm_api_key: str | None = None
    llm_base_url: str = ""
    llm_model: str = ""

    # 可选：JSON 任务（意图解析、选品）专用快速模型，为空则共用 llm_model
    llm_fast_model: str = ""

    # 反馈闭环
    feedback_path: str = ""          # 反馈事件持久化文件路径
    user_profile_dir: str = ""       # 用户偏好画像持久化目录

    # DeepSeek reasoning 参数（仅文本生成/闲聊时传递）
    llm_reasoning_effort: str = ""       # "high" | "medium" | "low"，为空时不传该参数

    # 兼容旧配置（provider=doubao 时生效）
    ark_api_key: str | None = None
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3/"
    ark_model: str = "ep-20260514111645-lmgt2"
    embedding_model_dir: str = "model/bge-small-zh-v1.5"
    embedding_model_id: str = "AI-ModelScope/bge-small-zh-v1.5"
    embedding_device: str = "cuda:0"
    use_embedding: bool = True
    request_timeout_seconds: float = 45.0
    memory_cache_path: str = ""
    session_dir: str = ""
    cart_path: str = ""
    session_ttl_days: int = 7
    server_base_url: str = ""  # e.g. "http://192.168.1.100:8000" for Android LAN access

    # TTS
    tts_enabled: bool = True
    tts_base_url: str = "http://127.0.0.1:18880"
    tts_api_key: str = "EMPTY"
    tts_model: str = "qwen3-tts"
    tts_response_format: str = "wav"       # wav | pcm
    tts_task_type: str = "VoiceDesign"
    tts_default_voice: str = "calm_female"
    tts_default_instructions: str = "A calm, clear female narrator voice."
    tts_timeout_seconds: float = 30.0
    tts_stream: bool = False
    tts_max_text_length: int = 500
    tts_chunk_duration_ms: int = 200

    # STT
    stt_enabled: bool = True
    stt_provider: str = "funasr"
    stt_base_url: str = "http://127.0.0.1:18090"
    stt_api_key: str = ""
    stt_model: str = "paraformer-zh"
    stt_audio_format: str = "wav"
    stt_sample_rate: int = 16000
    stt_timeout_seconds: float = 30.0
    stt_max_audio_size_mb: int = 10

    @property
    def voice_preset(self) -> dict[str, str]:
        return {
            "calm_female": "A calm, clear female narrator voice.",
            "energetic_male": "An energetic, friendly male voice.",
            "gentle_female": "A gentle and warm female voice.",
        }

    @property
    def effective_api_key(self) -> str | None:
        """根据 provider 解析最终 API Key。"""
        if self.llm_api_key:
            return self.llm_api_key
        if self.llm_provider == "deepseek":
            return self.ark_api_key  # 兼容：也可以复用 ARK_API_KEY
        return self.ark_api_key

    @property
    def effective_base_url(self) -> str:
        """根据 provider 解析最终 base_url。"""
        if self.llm_base_url:
            return self.llm_base_url
        if self.llm_provider == "deepseek":
            return "https://api.deepseek.com"
        # doubao (default)
        return self.ark_base_url

    @property
    def effective_model(self) -> str:
        """主模型，用于文本生成/闲聊。"""
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == "deepseek":
            return "deepseek-chat"
        return self.ark_model

    @property
    def effective_fast_model(self) -> str:
        """JSON 任务专用快速模型，为空时回退到 effective_model。"""
        return self.llm_fast_model or self.effective_model

    @property
    def reasoning_params(self) -> dict:
        """构建 DeepSeek reasoning 参数。设 reasoning_effort 时自动启用 thinking。"""
        params: dict = {}
        if self.llm_reasoning_effort:
            params["reasoning_effort"] = self.llm_reasoning_effort
            params["extra_body"] = {"thinking": {"type": "enabled"}}
        return params

    @property
    def dataset_path(self) -> Path:
        path = Path(self.dataset_dir)
        if path.is_absolute():
            return path
        return self.project_root / path

    @property
    def embedding_path(self) -> Path:
        path = Path(self.embedding_model_dir)
        if path.is_absolute():
            return path
        return self.project_root / path


@lru_cache
def get_settings() -> Settings:
    return Settings(
        dataset_dir=os.getenv("DATASET_DIR", "ecommerce_agent_dataset"),
        # 新配置（优先）
        llm_provider=os.getenv("LLM_PROVIDER", "doubao"),
        llm_api_key=os.getenv("LLM_API_KEY"),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_fast_model=os.getenv("LLM_FAST_MODEL", ""),
        llm_reasoning_effort=os.getenv("LLM_REASONING_EFFORT", ""),
        # 旧配置（兼容 doubao）
        ark_api_key=os.getenv("ARK_API_KEY"),
        ark_base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/"),
        ark_model=os.getenv("ARK_MODEL", "ep-20260514111645-lmgt2"),
        embedding_model_dir=os.getenv("EMBEDDING_MODEL_DIR", "model/bge-small-zh-v1.5"),
        embedding_model_id=os.getenv("EMBEDDING_MODEL_ID", "AI-ModelScope/bge-small-zh-v1.5"),
        embedding_device=os.getenv("EMBEDDING_DEVICE", "cuda:0"),
        use_embedding=os.getenv("USE_EMBEDDING", "1") not in {"0", "false", "False"},
        request_timeout_seconds=float(os.getenv("ARK_TIMEOUT_SECONDS", "45")),
        memory_cache_path=os.getenv("SHOPGUIDE_MEMORY_CACHE_PATH", ""),
        session_dir=os.getenv("SHOPGUIDE_SESSION_DIR", ""),
        cart_path=os.getenv("SHOPGUIDE_CART_PATH", ""),
        session_ttl_days=int(os.getenv("SHOPGUIDE_SESSION_TTL_DAYS", "7")),
        server_base_url=os.getenv("SERVER_BASE_URL", ""),
        feedback_path=os.getenv("SHOPGUIDE_FEEDBACK_PATH", ""),
        user_profile_dir=os.getenv("SHOPGUIDE_USER_PROFILE_DIR", ""),
        # TTS
        tts_enabled=os.getenv("TTS_ENABLED", "true").lower() not in {"0", "false"},
        tts_base_url=os.getenv("TTS_BASE_URL", "http://127.0.0.1:18880"),
        tts_api_key=os.getenv("TTS_API_KEY", "EMPTY"),
        tts_model=os.getenv("TTS_MODEL", "qwen3-tts"),
        tts_response_format=os.getenv("TTS_RESPONSE_FORMAT", "wav"),
        tts_task_type=os.getenv("TTS_TASK_TYPE", "VoiceDesign"),
        tts_default_voice=os.getenv("TTS_DEFAULT_VOICE", "calm_female"),
        tts_default_instructions=os.getenv("TTS_DEFAULT_INSTRUCTIONS", "A calm, clear female narrator voice."),
        tts_timeout_seconds=float(os.getenv("TTS_TIMEOUT_SECONDS", "30")),
        tts_stream=os.getenv("TTS_STREAM", "false").lower() == "true",
        tts_max_text_length=int(os.getenv("TTS_MAX_TEXT_LENGTH", "500")),
        tts_chunk_duration_ms=int(os.getenv("TTS_CHUNK_DURATION_MS", "200")),
        # STT
        stt_enabled=os.getenv("STT_ENABLED", "true").lower() not in {"0", "false"},
        stt_provider=os.getenv("STT_PROVIDER", "funasr"),
        stt_base_url=os.getenv("STT_BASE_URL", "http://127.0.0.1:18090"),
        stt_api_key=os.getenv("STT_API_KEY", ""),
        stt_model=os.getenv("STT_MODEL", "paraformer-zh"),
        stt_audio_format=os.getenv("STT_AUDIO_FORMAT", "wav"),
        stt_sample_rate=int(os.getenv("STT_SAMPLE_RATE", "16000")),
        stt_timeout_seconds=float(os.getenv("STT_TIMEOUT_SECONDS", "30")),
        stt_max_audio_size_mb=int(os.getenv("STT_MAX_AUDIO_SIZE_MB", "10")),
    )
