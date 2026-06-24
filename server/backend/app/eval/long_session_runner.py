"""长会话评测 runner：fresh/resume 互斥 + retry + schema 校验 + flush+fsync。"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel

from ..models import Product
from .long_session_models import TraceMeta, TraceSchemaError, validate_trace_line
from .long_session_templates import ScriptTurn

SPEC_VERSION = "2026-06-24-v1"


class HashMismatchError(RuntimeError):
    pass


class MetaMissingError(FileNotFoundError):
    pass


class RunnerConfig(BaseModel):
    stage: Literal["dryrun", "pilot", "full"]
    condition: Literal["C0", "C1", "C2", "C3", "C4"]
    data_root: Path
    mode: Literal["fresh", "resume"]


CONDITION_CONFIGS = {
    "C0": {"disable_window": True, "disable_snapshot": True, "disable_recommendation": True, "disable_rank": True},
    "C1": {"disable_window": False, "disable_snapshot": True, "disable_recommendation": True, "disable_rank": True},
    "C2": {"disable_window": False, "disable_snapshot": False, "disable_recommendation": True, "disable_rank": True},
    "C3": {"disable_window": False, "disable_snapshot": False, "disable_recommendation": False, "disable_rank": True},
    "C4": {"disable_window": False, "disable_snapshot": False, "disable_recommendation": False, "disable_rank": False},
}


class LongSessionRunner:
    def __init__(self, config: RunnerConfig):
        self.config = config
        self.stage_root = config.data_root / config.stage
        self.cache_namespace = self.stage_root / f"cache_{config.condition.lower()}"
        self.trace_path = self.stage_root / f"trace_{config.condition}.jsonl"
        self._script: list[ScriptTurn] = []
        self._products: list[Product] = []
        self._hashes: tuple[str, str, str] | None = None  # script, product, condition_config

    # ----- hashing -----
    @staticmethod
    def _sha256(data: bytes) -> str:
        return "sha256:" + hashlib.sha256(data).hexdigest()

    def _compute_hashes(self) -> tuple[str, str, str]:
        if self._hashes is not None:
            return self._hashes
        script_payload = json.dumps([t.model_dump() for t in self._script], ensure_ascii=False, sort_keys=True)
        product_payload = json.dumps([p.product_id for p in self._products], sort_keys=True)
        condition_payload = json.dumps(CONDITION_CONFIGS[self.config.condition], sort_keys=True)
        self._hashes = (
            self._sha256(script_payload.encode("utf-8")),
            self._sha256(product_payload.encode("utf-8")),
            self._sha256(condition_payload.encode("utf-8")),
        )
        return self._hashes

    # Test-only helper：允许测试用 lambda 覆盖
    _compute_hashes_static: Callable[[], tuple[str, str, str]] | None = None

    def _hashes_or_static(self) -> tuple[str, str, str]:
        if self._compute_hashes_static is not None:
            return self._compute_hashes_static()
        return self._compute_hashes()

    # ----- fresh/resume setup -----
    def _setup_trace_file_for_test(self) -> None:
        """供单测调用；正式入口为 run()，会在内部调用此方法。"""
        self.stage_root.mkdir(parents=True, exist_ok=True)
        self.cache_namespace.mkdir(parents=True, exist_ok=True)
        script_hash, product_hash, condition_hash = self._hashes_or_static()
        meta = TraceMeta(
            condition=self.config.condition,
            script_version_hash=script_hash,
            product_list_hash=product_hash,
            condition_config_hash=condition_hash,
            cache_namespace=str(self.cache_namespace),
            started_at=dt.datetime.now().isoformat(),
            ark_model=os.getenv("ARK_MODEL", ""),
            spec_version=SPEC_VERSION,
        )
        if self.config.mode == "fresh":
            if self.trace_path.exists():
                ts = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
                bak = self.trace_path.with_suffix(f".jsonl.{ts}.bak")
                shutil.move(str(self.trace_path), str(bak))
            with self.trace_path.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps({"_meta": True, **meta.model_dump()}, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        elif self.config.mode == "resume":
            if not self.trace_path.exists():
                raise MetaMissingError(f"trace.jsonl 不存在：{self.trace_path}；resume 必须基于已有 trace")
            with self.trace_path.open(encoding="utf-8") as fh:
                first = fh.readline().strip()
            if not first:
                raise MetaMissingError(f"trace.jsonl 为空：{self.trace_path}")
            existing = json.loads(first)
            if not existing.get("_meta"):
                raise MetaMissingError(f"trace.jsonl 首行不是 _meta：{self.trace_path}")
            for key in ("script_version_hash", "product_list_hash", "condition_config_hash"):
                if existing.get(key) != getattr(meta, key):
                    raise HashMismatchError(
                        f"{key} 不匹配；trace={existing.get(key)} runtime={getattr(meta, key)}；"
                        f"模板/商品/condition 已变更，拒绝续跑"
                    )

    def _should_resume_from(self) -> int:
        if not self.trace_path.exists():
            return 0
        last_idx = -1
        with self.trace_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("_meta"):
                    continue
                last_idx = max(last_idx, int(row.get("turn_index", -1)))
        return last_idx + 1

    # ----- per-turn write -----
    def _write_turn(self, trace_dict: dict) -> None:
        validate_trace_line(trace_dict)
        with self.trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(trace_dict, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    # ----- ARK retry -----
    async def _retry_with_backoff(self, fn, *args, max_retries: int = 3, **kwargs):
        delay = 2
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt == max_retries - 1:
                    break
                await asyncio.sleep(delay)
                delay *= 2
        raise last_exc  # type: ignore

    # ----- full entry -----
    async def run(self, script: list[ScriptTurn], products: list[Product], *, agent_factory) -> None:
        """完整入口；具体的 agent.chat() 调用 + trace 字段填充由 Task 10 接入。"""
        self._script = script
        self._products = products
        self._setup_trace_file_for_test()
        start_idx = self._should_resume_from() if self.config.mode == "resume" else 0
        # ... 此处为 Task 10 的 scoring hook：将 agent.chat() 的结果组装成 TurnTrace 落盘
        raise NotImplementedError("Task 10 will fill in the per-turn execution loop")
