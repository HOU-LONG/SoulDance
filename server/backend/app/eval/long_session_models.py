from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


TRACE_SCHEMA_VERSION = "1"


class TraceSchemaError(ValueError):
    """Trace JSON schema 验证失败时抛出。"""
    pass


class JudgeScore(BaseModel):
    """LLM 评测打分结果（spec §6.1.1）。"""
    raw: list[dict[str, Any]]
    mean: float
    disagreement: float
    call_count: int


class TurnTrace(BaseModel):
    """单轮 trace 记录（spec §7 + §9.1）。"""
    condition: Literal["C0", "C1", "C2", "C3", "C4"]
    session_id: str
    turn_index: int = Field(ge=0)
    phase: Literal["A", "B", "C", "D", "E"]
    turn_type: str
    adversarial_subtype: str | None = None
    query: str
    expected: dict[str, Any]
    pipeline: list[str]
    tool_calls: list[dict[str, Any]]
    branch_flags: dict[str, Any]
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    first_chunk_ms: int = Field(ge=0)
    total_ms: int = Field(ge=0)
    context_payload_bytes: int = Field(ge=0)
    context_payload_tokens: int = Field(ge=0)
    context_events_count: int = Field(ge=0)
    focus_history_len: int = Field(ge=0)
    focus_product_id: str | None = None
    hard_constraints: dict[str, Any]
    state_drift: dict[str, Any] | None = None
    degradation: dict[str, Any] | None = None
    would_hit_b1: bool
    effective_hit_b1: bool
    would_hit_b2: bool
    effective_hit_b2: bool
    cache_stats_at_turn: dict[str, Any]
    rule_score: dict[str, Any]
    judge_score: JudgeScore | None = None
    answer_text: str
    retrieved_top_k: list[str]
    script_version_hash: str
    product_list_hash: str
    condition_config_hash: str


class TraceMeta(BaseModel):
    """Trace 文件头部元数据（不含 _meta 标记，由 runner 在写入时添加）。"""
    condition: Literal["C0", "C1", "C2", "C3", "C4"]
    script_version_hash: str
    product_list_hash: str
    condition_config_hash: str
    cache_namespace: str
    started_at: str
    ark_model: str
    spec_version: str


# 模块级缓存，避免重复加载 schema
_SCHEMA_CACHE: dict[str, Any] | None = None


def _load_schema() -> dict[str, Any]:
    """加载并缓存 JSON Schema。"""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is not None:
        return _SCHEMA_CACHE

    schema_path = Path(__file__).parent / "trace_schema_v1.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        _SCHEMA_CACHE = json.load(f)
    return _SCHEMA_CACHE


def validate_trace_line(line: dict) -> None:
    """验证单轮 trace 字典是否符合 JSON Schema。"""
    import jsonschema

    schema = _load_schema()
    try:
        jsonschema.validate(instance=line, schema=schema)
    except jsonschema.ValidationError as e:
        raise TraceSchemaError(f"Trace schema 验证失败: {e}") from e
