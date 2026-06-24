from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SERVER_ROOT.parent

# Keep the existing remote root .env working after moving backend code under server/.
# A server-local .env can override it for cleaner future deployments.
load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_SERVER_ROOT / ".env", override=True)


class Settings(BaseModel):
    server_root: Path = Field(default_factory=lambda: _SERVER_ROOT)
    project_root: Path = Field(default_factory=lambda: _REPO_ROOT)
    dataset_dir: str = "ecommerce_agent_dataset"

    # LLM provider: "doubao" | "deepseek" | "custom"
    llm_provider: str = "doubao"
    llm_api_key: str | None = None
    llm_base_url: str = ""
    llm_model: str = ""
    llm_fast_model: str = ""
    llm_reasoning_effort: str = ""

    # Legacy Doubao-compatible settings.
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
    server_base_url: str = ""
    feedback_path: str = ""
    user_profile_dir: str = ""

    # Operational limits
    max_llm_calls: int = 10
    max_connections: int = 50

    # Database
    database_url: str = ""
    embedding_dimension: int = 384

    # Retrieval. dense 路径走内存矩阵；BM25 保留 chunk 级 + group-by-product max；
    # 融合策略和权重在 product 级别完成，全部可配置，便于 ablation。
    retrieval_fusion_strategy: Literal["weighted", "rrf", "dense_only", "bm25_only"] = "weighted"
    retrieval_dense_weight: float = 0.65
    retrieval_rrf_k: int = 60
    retrieval_top_k_recall: int = 30
    retrieval_top_k_final: int = 10

    # TTS. openai_audio posts to /v1/audio/speech; mimo posts to /chat/completions.
    # doubao_chunked_v3 posts to Volcengine HTTP Chunked V3.
    tts_enabled: bool = True
    tts_provider: str = "openai_audio"
    tts_base_url: str = "http://127.0.0.1:18880"
    tts_api_key: str = "EMPTY"
    tts_model: str = "qwen3-tts"
    tts_response_format: str = "wav"
    tts_task_type: str = "VoiceDesign"
    tts_default_voice: str = "calm_female"
    tts_default_instructions: str = "A calm, clear female narrator voice."
    tts_timeout_seconds: float = 30.0
    tts_stream: bool = False
    tts_max_text_length: int = 500
    tts_chunk_duration_ms: int = 200
    doubao_voice_api_key: str | None = None
    doubao_tts_url: str = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    doubao_tts_api_key: str | None = None
    doubao_tts_resource_id: str = "seed-tts-2.0"
    doubao_tts_model: str = "seed-tts-2.0-standard"
    doubao_tts_speaker: str = "zh_female_wenroushunv_uranus_bigtts"
    doubao_tts_format: str = "pcm"
    doubao_tts_sample_rate: int = 24000
    doubao_tts_speech_rate: int = 0
    doubao_tts_loudness_rate: int = 0

    # STT.
    stt_enabled: bool = True
    stt_provider: str = "funasr"
    stt_base_url: str = "http://127.0.0.1:18090"
    stt_api_key: str = ""
    stt_model: str = "paraformer-zh"
    stt_audio_format: str = "wav"
    stt_sample_rate: int = 16000
    stt_timeout_seconds: float = 30.0
    stt_max_audio_size_mb: int = 10
    doubao_asr_ws_url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    doubao_asr_api_key: str | None = None
    doubao_asr_app_key: str = ""
    doubao_asr_access_key: str = ""
    doubao_asr_resource_id: str = "volc.seedasr.sauc.duration"
    doubao_asr_uid: str = "souldance-android"
    doubao_asr_audio_format: str = "pcm"
    doubao_asr_language: str = "zh-CN"
    doubao_asr_chunk_ms: int = 200
    doubao_asr_inter_chunk_delay_ms: int = 0
    doubao_asr_enable_itn: bool = True
    doubao_asr_enable_punc: bool = True
    doubao_asr_result_type: str = "full"

    @property
    def voice_preset(self) -> dict[str, str]:
        return {
            "calm_female": "A calm, clear female narrator voice.",
            "energetic_male": "An energetic, friendly male voice.",
            "gentle_female": "A gentle and warm female voice.",
        }

    @property
    def effective_api_key(self) -> str | None:
        if self.llm_api_key:
            return self.llm_api_key
        if self.llm_provider == "deepseek":
            return self.ark_api_key
        return self.ark_api_key

    @property
    def effective_base_url(self) -> str:
        if self.llm_base_url:
            return self.llm_base_url
        if self.llm_provider == "deepseek":
            return "https://api.deepseek.com"
        return self.ark_base_url

    @property
    def effective_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == "deepseek":
            return "deepseek-chat"
        return self.ark_model

    @property
    def effective_fast_model(self) -> str:
        return self.llm_fast_model or self.effective_model

    @property
    def reasoning_params(self) -> dict:
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

    @property
    def retrieval_config(self) -> "RetrievalConfig":
        return RetrievalConfig(
            fusion_strategy=self.retrieval_fusion_strategy,
            dense_weight=self.retrieval_dense_weight,
            rrf_k=self.retrieval_rrf_k,
            top_k_recall=self.retrieval_top_k_recall,
            top_k_final=self.retrieval_top_k_final,
        )


class RetrievalConfig(BaseModel):
    """检索层超参集合。

    所有融合权重、RRF k、top_k 默认值的唯一来源，便于 ablation 实验
    无需改代码即可切换策略。
    """

    fusion_strategy: Literal["weighted", "rrf", "dense_only", "bm25_only"] = "weighted"
    dense_weight: float = 0.65
    rrf_k: int = 60
    top_k_recall: int = 30
    top_k_final: int = 10

    @property
    def bm25_weight(self) -> float:
        return max(0.0, 1.0 - self.dense_weight)


def _repo_relative_path(value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(_REPO_ROOT / path)


def _retrieval_strategy(value: str) -> str:
    value = (value or "").strip().lower()
    if value not in {"weighted", "rrf", "dense_only", "bm25_only"}:
        return "weighted"
    return value


@lru_cache
def get_settings() -> Settings:
    return Settings(
        dataset_dir=os.getenv("DATASET_DIR", "ecommerce_agent_dataset"),
        llm_provider=os.getenv("LLM_PROVIDER", "doubao"),
        llm_api_key=os.getenv("LLM_API_KEY"),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_fast_model=os.getenv("LLM_FAST_MODEL", ""),
        llm_reasoning_effort=os.getenv("LLM_REASONING_EFFORT", ""),
        ark_api_key=os.getenv("ARK_API_KEY"),
        ark_base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/"),
        ark_model=os.getenv("ARK_MODEL", "ep-20260514111645-lmgt2"),
        database_url=os.getenv("SHOPGUIDE_DATABASE_URL", ""),
        embedding_dimension=int(os.getenv("SHOPGUIDE_EMBEDDING_DIMENSION", "384")),
        retrieval_fusion_strategy=_retrieval_strategy(os.getenv("RETRIEVAL_FUSION_STRATEGY", "weighted")),
        retrieval_dense_weight=float(os.getenv("RETRIEVAL_DENSE_WEIGHT", "0.65")),
        retrieval_rrf_k=int(os.getenv("RETRIEVAL_RRF_K", "60")),
        retrieval_top_k_recall=int(os.getenv("RETRIEVAL_TOP_K_RECALL", "30")),
        retrieval_top_k_final=int(os.getenv("RETRIEVAL_TOP_K_FINAL", "10")),
        embedding_model_dir=os.getenv("EMBEDDING_MODEL_DIR", "model/bge-small-zh-v1.5"),
        embedding_model_id=os.getenv("EMBEDDING_MODEL_ID", "AI-ModelScope/bge-small-zh-v1.5"),
        embedding_device=os.getenv("EMBEDDING_DEVICE", "cuda:0"),
        use_embedding=os.getenv("USE_EMBEDDING", "1") not in {"0", "false", "False"},
        request_timeout_seconds=float(os.getenv("ARK_TIMEOUT_SECONDS", "45")),
        memory_cache_path=_repo_relative_path(os.getenv("SHOPGUIDE_MEMORY_CACHE_PATH", "")),
        session_dir=_repo_relative_path(os.getenv("SHOPGUIDE_SESSION_DIR", "")),
        cart_path=_repo_relative_path(os.getenv("SHOPGUIDE_CART_PATH", "")),
        session_ttl_days=int(os.getenv("SHOPGUIDE_SESSION_TTL_DAYS", "7")),
        server_base_url=os.getenv("SERVER_BASE_URL", ""),
        feedback_path=_repo_relative_path(os.getenv("SHOPGUIDE_FEEDBACK_PATH", "")),
        user_profile_dir=_repo_relative_path(os.getenv("SHOPGUIDE_USER_PROFILE_DIR", "")),
        max_llm_calls=int(os.getenv("SHOPGUIDE_MAX_LLM_CALLS", "10")),
        max_connections=int(os.getenv("SHOPGUIDE_MAX_CONNECTIONS", "50")),
        tts_enabled=os.getenv("TTS_ENABLED", "true").lower() not in {"0", "false"},
        tts_provider=os.getenv("TTS_PROVIDER", "openai_audio"),
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
        doubao_voice_api_key=os.getenv("DOUBAO_VOICE_API_KEY"),
        doubao_tts_url=os.getenv("DOUBAO_TTS_URL", "https://openspeech.bytedance.com/api/v3/tts/unidirectional"),
        doubao_tts_api_key=os.getenv("DOUBAO_TTS_API_KEY") or os.getenv("DOUBAO_VOICE_API_KEY"),
        doubao_tts_resource_id=os.getenv("DOUBAO_TTS_RESOURCE_ID", "seed-tts-2.0"),
        doubao_tts_model=os.getenv("DOUBAO_TTS_MODEL", "seed-tts-2.0-standard"),
        doubao_tts_speaker=os.getenv("DOUBAO_TTS_SPEAKER", "zh_female_wenroushunv_uranus_bigtts"),
        doubao_tts_format=os.getenv("DOUBAO_TTS_FORMAT", "pcm"),
        doubao_tts_sample_rate=int(os.getenv("DOUBAO_TTS_SAMPLE_RATE", "24000")),
        doubao_tts_speech_rate=int(os.getenv("DOUBAO_TTS_SPEECH_RATE", "0")),
        doubao_tts_loudness_rate=int(os.getenv("DOUBAO_TTS_LOUDNESS_RATE", "0")),
        stt_enabled=os.getenv("STT_ENABLED", "true").lower() not in {"0", "false"},
        stt_provider=os.getenv("STT_PROVIDER", "funasr"),
        stt_base_url=os.getenv("STT_BASE_URL", "http://127.0.0.1:18090"),
        stt_api_key=os.getenv("STT_API_KEY", ""),
        stt_model=os.getenv("STT_MODEL", "paraformer-zh"),
        stt_audio_format=os.getenv("STT_AUDIO_FORMAT", "wav"),
        stt_sample_rate=int(os.getenv("STT_SAMPLE_RATE", "16000")),
        stt_timeout_seconds=float(os.getenv("STT_TIMEOUT_SECONDS", "30")),
        stt_max_audio_size_mb=int(os.getenv("STT_MAX_AUDIO_SIZE_MB", "10")),
        doubao_asr_ws_url=os.getenv("DOUBAO_ASR_WS_URL", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"),
        doubao_asr_api_key=os.getenv("DOUBAO_ASR_API_KEY") or os.getenv("DOUBAO_VOICE_API_KEY"),
        doubao_asr_app_key=os.getenv("DOUBAO_ASR_APP_KEY", ""),
        doubao_asr_access_key=os.getenv("DOUBAO_ASR_ACCESS_KEY", ""),
        doubao_asr_resource_id=os.getenv("DOUBAO_ASR_RESOURCE_ID", "volc.seedasr.sauc.duration"),
        doubao_asr_uid=os.getenv("DOUBAO_ASR_UID", "souldance-android"),
        doubao_asr_audio_format=os.getenv("DOUBAO_ASR_AUDIO_FORMAT", "pcm"),
        doubao_asr_language=os.getenv("DOUBAO_ASR_LANGUAGE", "zh-CN"),
        doubao_asr_chunk_ms=int(os.getenv("DOUBAO_ASR_CHUNK_MS", "200")),
        doubao_asr_inter_chunk_delay_ms=int(os.getenv("DOUBAO_ASR_INTER_CHUNK_DELAY_MS", "0")),
        doubao_asr_enable_itn=os.getenv("DOUBAO_ASR_ENABLE_ITN", "true").lower() not in {"0", "false"},
        doubao_asr_enable_punc=os.getenv("DOUBAO_ASR_ENABLE_PUNC", "true").lower() not in {"0", "false"},
        doubao_asr_result_type=os.getenv("DOUBAO_ASR_RESULT_TYPE", "full"),
    )
