"""
配置中心 — SoulDance 后端所有运行时参数的单一来源。

===== 领域概念扫盲 =====

"Settings"（Pydantic BaseModel）：
一个类型安全的配置容器。所有配置项都有明确的类型注解（str/int/bool/Path），
Pydantic 自动校验类型——如果不小心把数字赋给了字符串字段，启动时就会报错而非
运行时才出 bug。这是现代 Python 项目替代 os.getenv 散落四处的标准做法。

"lru_cache + get_settings()"：
单例模式的一种实现。整个进程内 get_settings() 只会执行一次，
后续调用直接返回缓存的结果。好处：(1) 性能（不需要反复读环境变量）；
(2) 一致性（所有模块看到的是同一份配置快照）。

"env 优先级"：
repository根 .env 先加载（load_dotenv），server 子目录 .env 再覆盖（override=True）。
这使得 server/.env 可以做局部定制，不影响仓库根的公共默认值。

"PATH 解析"：
_SERVER_ROOT = config.py 的上两级目录（即 server/）
_REPO_ROOT = _SERVER_ROOT 的父级（即仓库根，SoulDance/）
所有相对路径（dataset、embedding model 等）都基于 _REPO_ROOT 解析为绝对路径，
确保无论从哪个工作目录启动都能找到正确的文件——这就是"可移植性"的基础。

===== 配置分组概览 =====

- LLM 配置：provider（doubao/deepseek/custom）、API key、base URL、model
- Reranker 配置：CrossEncoder 模型路径、LLM 重排开关、置信度阈值、top_k
- Retrieval 配置：融合策略（weighted/rrf/dense_only/bm25_only）、权重、RRF k
- TTS/STT 配置：语音合成与转写的 provider、模型、codec 参数
- 持久化配置：database URL、session/cart/feedback 路径
- 评测开关：A1（窗口截断）、A2（结构化快照）、C4（推荐记忆）等

===== 与其它模块协作 =====

- main.py：create_app 入口处调用 get_settings()，注入各组件
- db/engine.py：get_engine 从 settings 取 database_url
- llm_client.py：DoubaoLLMClient 从 settings 取 API key/model/超时
- rag/reranker.py：build_reranker 从 settings 取 rerank 相关参数
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# ── 仓库路径解析 ─────────────────────────────────────────────
# _SERVER_ROOT: server/ 目录（config.py 在 server/backend/app/ 内，parents[2] 即 server/）
# _REPO_ROOT: 仓库根 SoulDance/（server/ 的父级）
# 所有相对路径均以此为基准解析，这是整个项目"跨机器可移植"的基石。

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SERVER_ROOT.parent

# env 加载顺序：先仓库根 .env（公共默认），再 server/.env（局部覆盖）。
# 这使得同一份 repo 在不同环境（本地开发 vs 远程服务器）都能正确配置。
load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_SERVER_ROOT / ".env", override=True)


class Settings(BaseModel):
    """ShopGuide 后端的全局配置中心。

    每个字段都有默认值（定义在 Field default 和 get_settings() 的 os.getenv 调用中），
    使得在没有 .env 文件的情况下也能以最小可用模式运行。
    """
    # 服务器路径
    server_root: Path = Field(default_factory=lambda: _SERVER_ROOT)
    project_root: Path = Field(default_factory=lambda: _REPO_ROOT)
    dataset_dir: str = "ecommerce_agent_dataset"

    # ── LLM 提供商配置 ─────────────────────────────────────
    # provider 决定走哪个 LLM 后端：doubao（豆包/火山引擎）、deepseek、custom（OpenAI 兼容）
    llm_provider: str = "doubao"
    llm_api_key: str | None = None
    llm_base_url: str = ""
    llm_model: str = ""
    llm_fast_model: str = ""
    llm_reasoning_effort: str = ""

    # ── 豆包（火山引擎 ARK）专用配置 ────────────────────────
    # 这些是 provider=doubao 时的实际 API 参数。ark_model 是火山引擎的接入点（endpoint）ID。
    ark_api_key: str | None = None
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3/"
    ark_model: str = "ep-20260514111645-lmgt2"

    # ── Embedding（向量嵌入）模型配置 ───────────────────────
    # embedding 模型用于把商品文本转成向量，支撑语义搜索。
    # embedding_model_id 是 HuggingFace/ModelScope 的模型标识符，用于自动下载。
    # embedding_device cuda:0 用于 GPU 推理；开发机无 GPU 时可设为 "cpu"。
    embedding_model_dir: str = "model/bge-small-zh-v1.5"
    embedding_model_id: str = "AI-ModelScope/bge-small-zh-v1.5"
    embedding_device: str = "cuda:0"
    use_embedding: bool = True
    request_timeout_seconds: float = 45.0

    # ── 持久化路径 ──────────────────────────────────────────
    # 留空代表禁用对应功能的内存模式（不写磁盘）
    memory_cache_path: str = ""
    session_dir: str = ""
    cart_path: str = ""
    session_ttl_days: int = 7
    server_base_url: str = ""
    feedback_path: str = ""
    user_profile_dir: str = ""

    # ── 长会话评测开关（spec 2026-06-24-long-session-eval）──
    # 生产环境全部默认 False/25000，等价于 C4 全开行为（窗口截断 + 结构化快照 + 推荐记忆 + 排序缓存均启用）。
    # 评测 CLI 通过环境变量临时覆盖，不需要改 .env 或代码。
    # A1: 窗口截断（保留最近 3 轮确保上下文紧凑，防止 LLM 对历史过拟合）
    # A2: 结构化快照（替代原始对话日志，减少 token 消耗）
    # C4: 推荐记忆 + 排序缓存（加速重复/相似查询的响应）
    eval_disable_window_truncation: bool = False
    eval_disable_structured_snapshot: bool = False
    eval_disable_recommendation_memory: bool = False
    eval_disable_rank_cache: bool = False
    eval_force_trim_token_budget: int = 25000

    # ── 运行限制 ────────────────────────────────────────────
    max_llm_calls: int = 10
    max_connections: int = 50

    # ── 数据库 ──────────────────────────────────────────────
    # database_url 为空 → 自动回退到 project_root/data/shopguide.db
    database_url: str = ""
    embedding_dimension: int = 384

    # ── 重排器（Reranker）配置 ──────────────────────────────
    # CrossEncoder 模型默认 BGE-Reranker-v2-m3（BAAI 开源的跨编码器重排模型）。
    # 工作原理：对候选商品列表逐一打分（query, product_text）→ 按分排序 → 截断到 output_top_k。
    # LLM 重排开关 rerank_llm_enabled：True 时在强场景（comparison/refinement/low-confidence）
    #   触发 LLM 兜底重排；失败时静默降级回原序，不影响可用性。
    rerank_enabled: bool = True
    rerank_model_dir: str = "model/bge-reranker-v2-m3"
    rerank_model_id: str = "BAAI/bge-reranker-v2-m3"
    rerank_device: str = "cuda:0"
    rerank_input_top_k: int = 30    # 送入重排的候选商品数
    rerank_output_top_k: int = 15   # 重排后输出给 LLM 的商品数
    rerank_llm_enabled: bool = True
    rerank_llm_top_n: int = 8      # LLM 重排输入数（筛选 top_n 送 LLM）
    rerank_low_confidence_threshold: float = 0.05  # CrossEncoder 分数差距 < 此值 → 触发 LLM 重排

    # ── LLM 上下文窗口上限 ─────────────────────────────────
    # 用于 SessionContext 的 token 预算管理，超出时触发窗口截断。
    llm_context_limit: int = 128000

    # ── 检索策略配置 ────────────────────────────────────────
    # fusion_strategy: weighted（加权融合）/ rrf（倒数排名融合）/ dense_only / bm25_only
    # dense_weight=0.65 意味着向量语义检索占 65% 权重，BM25 关键词匹配占 35%
    # rrf_k=60 是 RRF 算法的平滑参数，标准值为 60
    # top_k_recall=30：融合后取前 30 个候选 → 送入重排
    # top_k_final=10：重排后保留前 10 个 → 最终返回给调用方
    retrieval_fusion_strategy: Literal["weighted", "rrf", "dense_only", "bm25_only"] = "weighted"
    retrieval_dense_weight: float = 0.65
    retrieval_rrf_k: int = 60
    retrieval_top_k_recall: int = 30
    retrieval_top_k_final: int = 10

    # ── TTS（文字转语音）配置 ───────────────────────────────
    # openai_audio → POST /v1/audio/speech; mimo → POST /chat/completions;
    # doubao_chunked_v3 → 火山引擎 HTTP Chunked V3（流式语音合成）
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
    # 豆包语音引擎专用配置
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

    # ── STT（语音转文字）配置 ───────────────────────────────
    # funasr 是 FunASR 引擎（阿里达摩院开源）；doubao_ws 是豆包 WebSocket 流式识别
    stt_enabled: bool = True
    stt_provider: str = "funasr"
    stt_base_url: str = "http://127.0.0.1:18090"
    stt_api_key: str = ""
    stt_model: str = "paraformer-zh"
    stt_audio_format: str = "wav"
    stt_sample_rate: int = 16000
    stt_timeout_seconds: float = 30.0
    stt_max_audio_size_mb: int = 10
    # 豆包 ASR 流式识别专用配置
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

    # ── 计算属性 ────────────────────────────────────────────
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

    # --- Evaluation switches (spec 2026-06-24-long-session-eval) ---
    # 生产默认全部 False/25000，等价于当前 C4 全开行为；评测 CLI 通过环境变量临时覆盖。
    eval_disable_window_truncation: bool = False
    eval_disable_structured_snapshot: bool = False
    eval_disable_recommendation_memory: bool = False
    eval_disable_rank_cache: bool = False
    eval_force_trim_token_budget: int = 25000

    user_profile_dir: str = ""

    # Operational limits
    max_llm_calls: int = 10
    max_connections: int = 50

    # Database
    database_url: str = ""
    embedding_dimension: int = 384

    # Reranker
    rerank_enabled: bool = True
    rerank_model_dir: str = "model/bge-reranker-v2-m3"
    rerank_model_id: str = "BAAI/bge-reranker-v2-m3"
    rerank_device: str = "cuda:0"
    rerank_input_top_k: int = 30
    rerank_output_top_k: int = 15
    rerank_llm_enabled: bool = True
    rerank_llm_top_n: int = 8
    rerank_low_confidence_threshold: float = 0.05

    # Session context compression. Single runtime value for the LLM context
    # window — when model-name → limit mapping is added later, it must resolve
    # into this field before the watermark policy is consulted.
    llm_context_limit: int = 128000

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
    """检索层超参集合——融合策略与 top_k 的不可变快照。

    从 Settings 的 retrieval_* 字段聚合而来，通过 settings.retrieval_config 属性暴露。
    设计为独立类的原因是：(1) 便于在测试中注入不同的检索参数；
    (2) 避免把 Settings 的几十个无关字段传给检索模块，保持接口干净。
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
    """将可能为相对路径的字符串转为基于 _REPO_ROOT 的绝对路径。

    例如 "data/sessions" → "/home/huadabioa/.../SoulDance/data/sessions"
    如果已是绝对路径则原样返回。空字符串也直接返回空（表示"禁用此功能"）。
    """
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


def _parse_bool_env(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    """构建并缓存 Settings 单例。

    配置来源优先级（从低到高）：
    1. Pydantic Field 默认值（代码中的硬编码 fallback）
    2. .env 文件（仓库根 + server 子目录，后者覆盖前者）
    3. 操作系统环境变量（最高优先级，load_dotenv 不会覆盖已存在的 env var）

    lru_cache 确保整个进程内只构建一次，所有模块共享同一份配置快照。
    如果需要在运行时修改配置，应修改 Settings 实例的属性而不是重新调用此函数。
    """
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
        llm_context_limit=int(os.getenv("LLM_CONTEXT_LIMIT", "128000")),
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
        rerank_enabled=os.getenv("RERANK_ENABLED", "true").lower() not in {"0", "false"},
        rerank_model_dir=os.getenv("RERANK_MODEL_DIR", "model/bge-reranker-v2-m3"),
        rerank_model_id=os.getenv("RERANK_MODEL_ID", "BAAI/bge-reranker-v2-m3"),
        rerank_device=os.getenv("RERANK_DEVICE", "cuda:0"),
        rerank_input_top_k=int(os.getenv("RERANK_INPUT_TOP_K", "30")),
        rerank_output_top_k=int(os.getenv("RERANK_OUTPUT_TOP_K", "15")),
        rerank_llm_enabled=os.getenv("RERANK_LLM_ENABLED", "true").lower() not in {"0", "false"},
        rerank_llm_top_n=int(os.getenv("RERANK_LLM_TOP_N", "8")),
        rerank_low_confidence_threshold=float(os.getenv("RERANK_LOW_CONFIDENCE_THRESHOLD", "0.05")),
        eval_disable_window_truncation=_parse_bool_env("SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION"),
        eval_disable_structured_snapshot=_parse_bool_env("SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT"),
        eval_disable_recommendation_memory=_parse_bool_env("SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY"),
        eval_disable_rank_cache=_parse_bool_env("SHOPGUIDE_EVAL_DISABLE_RANK_CACHE"),
        eval_force_trim_token_budget=int(os.getenv("SHOPGUIDE_EVAL_FORCE_TRIM_TOKEN_BUDGET", "25000")),
    )
