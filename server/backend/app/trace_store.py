"""线程安全的请求 Trace 存储，内存环形缓冲区 + JSONL 文件持久化。

用法：
  from .trace_store import get_trace_store
  store = get_trace_store()
  store.append(TraceRecord(...))
  recent = store.recent(n=50)
  stats = store.stats()
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from threading import Lock

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 路径工具
# ---------------------------------------------------------------------------

def _project_root() -> str:
    """SoulDance 项目根目录绝对路径。"""
    # __file__ -> server/backend/app/trace_store.py → 上溯 4 级到项目根
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )


def _data_dir() -> str:
    return os.path.join(_project_root(), "data")


def _ensure_data_dir() -> None:
    os.makedirs(_data_dir(), exist_ok=True)


# ---------------------------------------------------------------------------
# TraceRecord
# ---------------------------------------------------------------------------

class TraceRecord(BaseModel):
    """单次请求的端到端 Trace 快照。"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    user_message: str = ""
    tool: str = ""
    tool_confidence: float = 0.0
    plan_tool_ms: float = 0.0
    response_ms: float = 0.0
    total_ms: float = 0.0
    plan_tokens: int = 0
    response_tokens: int = 0
    first_byte_ms: float = 0.0
    response_text: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# TraceStore
# ---------------------------------------------------------------------------

_TRACES_JSONL = "traces.jsonl"


class TraceStore:
    """线程安全环形缓冲区 + JSONL 追加持久化。

    - 内存环形缓冲区：最大 200 条。
    - 磁盘 JSONL：``data/traces.jsonl``（每行一个 JSON 对象，追加写）。
    - 零额外依赖（仅 stdlib + pydantic）。
    """

    def __init__(self, max_traces: int = 200) -> None:
        self._lock: Lock = Lock()
        self._max: int = max_traces
        self._records: list[TraceRecord] = []

    # ----- 内部 ---------------------------------------------------------------

    def _jsonl_path(self) -> str:
        return os.path.join(_data_dir(), _TRACES_JSONL)

    # ----- 公开 API -----------------------------------------------------------

    def append(self, record: TraceRecord) -> None:
        """追加一条记录到内存环和 JSONL 文件。超出容量时淘汰最旧记录。"""
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._max:
                self._records = self._records[-self._max :]

            _ensure_data_dir()
            with open(self._jsonl_path(), "a", encoding="utf-8") as fh:
                fh.write(record.model_dump_json() + "\n")

    def recent(self, n: int = 50) -> list[TraceRecord]:
        """返回最近 n 条记录（从新到旧排列）。"""
        n = max(0, min(n, self._max))
        with self._lock:
            return list(reversed(self._records[-n:]))

    def stats(self) -> dict:
        """返回当前环形缓冲区的聚合统计。"""
        with self._lock:
            records = self._records
            if not records:
                return {
                    "total_records": 0,
                    "avg_total_ms": 0.0,
                    "avg_plan_tool_ms": 0.0,
                    "avg_response_ms": 0.0,
                    "avg_first_byte_ms": 0.0,
                    "avg_plan_tokens": 0.0,
                    "avg_response_tokens": 0.0,
                    "avg_tool_confidence": 0.0,
                    "error_count": 0,
                    "tool_counts": {},
                }

            total = len(records)

            def _avg(attr: str) -> float:
                return sum(getattr(r, attr, 0.0) for r in records) / total

            error_count = sum(1 for r in records if r.error)

            tool_counts: dict[str, int] = {}
            for r in records:
                tool = r.tool or "__unknown__"
                tool_counts[tool] = tool_counts.get(tool, 0) + 1

            total_plan_tokens = sum(r.plan_tokens for r in records)
            total_response_tokens = sum(r.response_tokens for r in records)

            return {
                "total_records": total,
                "avg_total_ms": round(_avg("total_ms"), 1),
                "avg_plan_tool_ms": round(_avg("plan_tool_ms"), 1),
                "avg_response_ms": round(_avg("response_ms"), 1),
                "avg_first_byte_ms": round(_avg("first_byte_ms"), 1),
                "avg_plan_tokens": round(_avg("plan_tokens"), 1),
                "avg_response_tokens": round(_avg("response_tokens"), 1),
                "cumulative_plan_tokens": total_plan_tokens,
                "cumulative_response_tokens": total_response_tokens,
                "cumulative_total_tokens": total_plan_tokens + total_response_tokens,
                "avg_tool_confidence": round(_avg("tool_confidence"), 4),
                "error_count": error_count,
                "tool_counts": tool_counts,
            }


# ---------------------------------------------------------------------------
# 全局单例（双重检查锁定）
# ---------------------------------------------------------------------------

_store: TraceStore | None = None
_store_lock: Lock = Lock()


def get_trace_store() -> TraceStore:
    """返回进程级单例 TraceStore（惰性初始化，线程安全）。"""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = TraceStore()
    return _store
