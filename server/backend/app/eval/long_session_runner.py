"""长会话评测 runner：fresh/resume 互斥 + retry + schema 校验 + flush+fsync。"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import math
import os
import random
import shutil
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel

from ..models import Product, ChatRequest
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


def _dcg(rel: list[int]) -> float:
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rel))


def _ndcg_at_k(retrieved: list[str], ideal: list[str], k: int = 5) -> float:
    if not ideal:
        return 0.0
    rel = [1 if pid in ideal else 0 for pid in retrieved[:k]]
    ideal_rel = [1] * min(len(ideal), k)
    idcg = _dcg(ideal_rel) or 1.0
    return _dcg(rel) / idcg


def _recall_at_k(retrieved: list[str], ideal: list[str], k: int = 5) -> float:
    if not ideal:
        return 0.0
    hits = sum(1 for pid in retrieved[:k] if pid in ideal)
    return hits / len(ideal)


def _precision_at_k(retrieved: list[str], ideal: list[str], k: int = 5) -> float:
    if not retrieved[:k]:
        return 0.0
    hits = sum(1 for pid in retrieved[:k] if pid in ideal)
    return hits / k


def _compute_rule_score(
    turn: ScriptTurn,
    *,
    answer_text: str,
    retrieved_top_k: list[str],
    product_map: dict[str, Product],
) -> dict[str, Any]:
    score: dict[str, Any] = {}
    ttype = turn.turn_type
    ideal = turn.expected.get("ideal_top") or []
    forbidden = turn.expected.get("forbidden") or []
    if ttype in {"retrieval", "comparison", "long_range_reference"} and ideal:
        score["ndcg5"] = _ndcg_at_k(retrieved_top_k[:5], ideal)
        score["recall5"] = _recall_at_k(retrieved_top_k[:5], ideal)
        score["precision5"] = _precision_at_k(retrieved_top_k[:5], ideal)
    if forbidden:
        score["forbidden_hit"] = any(pid in retrieved_top_k for pid in forbidden) or any(
            pid in answer_text for pid in forbidden
        )
    if ttype == "followup_factual":
        sid = turn.expected.get("subject_product_id")
        product = product_map.get(sid or "")
        if product:
            score["fact_match"] = (
                str(int(product.price)) in answer_text
                or product.brand in answer_text
                or product.title in answer_text
            )
    if ttype == "cart_action":
        score["cart_consistent"] = True
    return score


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
    async def run(
        self,
        script: list[ScriptTurn],
        products: list[Product],
        *,
        agent_factory,
        judge = None,
        judge_sample_rates: dict[str, float] | None = None,
    ) -> None:
        """完整入口；具体的 agent.chat() 调用 + trace 字段填充由 Task 10 接入。"""
        self._script = script
        self._products = products
        self._setup_trace_file_for_test()
        product_map = {p.product_id: p for p in products}
        start_idx = self._should_resume_from() if self.config.mode == "resume" else 0
        script_hash, product_hash, condition_hash = self._hashes_or_static()
        session_id = f"eval_{self.config.stage}_{self.config.condition.lower()}_2026-06-24"

        # 保存当前环境变量以便恢复
        saved_env = {
            "SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION": os.environ.get("SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION"),
            "SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT": os.environ.get("SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT"),
            "SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY": os.environ.get("SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY"),
            "SHOPGUIDE_EVAL_DISABLE_RANK_CACHE": os.environ.get("SHOPGUIDE_EVAL_DISABLE_RANK_CACHE"),
            "SHOPGUIDE_MEMORY_CACHE_PATH": os.environ.get("SHOPGUIDE_MEMORY_CACHE_PATH"),
        }

        try:
            # 注入 condition 对应的开关到环境变量
            cfg = CONDITION_CONFIGS[self.config.condition]
            os.environ["SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION"] = "1" if cfg["disable_window"] else "0"
            os.environ["SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT"] = "1" if cfg["disable_snapshot"] else "0"
            os.environ["SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY"] = "1" if cfg["disable_recommendation"] else "0"
            os.environ["SHOPGUIDE_EVAL_DISABLE_RANK_CACHE"] = "1" if cfg["disable_rank"] else "0"
            os.environ["SHOPGUIDE_MEMORY_CACHE_PATH"] = str(self.cache_namespace / "recommendation.jsonl")

            agent = agent_factory()
            sample_rates = judge_sample_rates or {
                "comparison": 0.30, "long_range_reference": 0.30,
                "adversarial_reference": 0.50, "adversarial_constraint": 0.50,
            }
            rng = random.Random(20260624)

            for turn_index in range(start_idx, len(script)):
                turn = script[turn_index]
                t0 = dt.datetime.now()
                try:
                    agent_result = await self._retry_with_backoff(
                        self._invoke_agent, agent, turn, session_id, max_retries=3,
                    )
                    degradation = agent_result.get("degradation")
                except Exception as exc:
                    agent_result = {"answer_text": "", "retrieved_top_k": [], "pipeline": [], "tool_calls": [],
                                    "branch_flags": {}, "prompt_tokens": 0, "completion_tokens": 0,
                                    "first_chunk_ms": 0, "context_payload_bytes": 0, "context_payload_tokens": 0,
                                    "context_events_count": 0, "focus_history_len": 0,
                                    "focus_product_id": None, "hard_constraints": {},
                                    "would_hit_b1": False, "effective_hit_b1": False,
                                    "would_hit_b2": False, "effective_hit_b2": False,
                                    "cache_stats_at_turn": {}}
                    degradation = f"ark_failure_skip:{exc.__class__.__name__}"
                total_ms = int((dt.datetime.now() - t0).total_seconds() * 1000)

                rule_score = _compute_rule_score(
                    turn,
                    answer_text=agent_result["answer_text"],
                    retrieved_top_k=agent_result["retrieved_top_k"],
                    product_map=product_map,
                )

                judge_score = None
                sample_rate = sample_rates.get(turn.turn_type, 0.0)
                if judge is not None and sample_rate > 0 and rng.random() < sample_rate:
                    jr = await self._retry_with_backoff(
                        judge.judge, turn, agent_result["answer_text"],
                        agent_result["retrieved_top_k"], product_map, max_retries=3,
                    )
                    judge_score = jr.model_dump() if jr else None

                trace_dict = {
                    "condition": self.config.condition,
                    "session_id": session_id,
                    "turn_index": turn_index,
                    "phase": turn.phase,
                    "turn_type": turn.turn_type,
                    "adversarial_subtype": turn.adversarial_subtype,
                    "query": turn.query,
                    "expected": turn.expected,
                    "pipeline": agent_result["pipeline"],
                    "tool_calls": agent_result["tool_calls"],
                    "branch_flags": agent_result["branch_flags"],
                    "prompt_tokens": agent_result["prompt_tokens"],
                    "completion_tokens": agent_result["completion_tokens"],
                    "first_chunk_ms": agent_result["first_chunk_ms"],
                    "total_ms": total_ms,
                    "context_payload_bytes": agent_result["context_payload_bytes"],
                    "context_payload_tokens": agent_result["context_payload_tokens"],
                    "context_events_count": agent_result["context_events_count"],
                    "focus_history_len": agent_result["focus_history_len"],
                    "focus_product_id": agent_result["focus_product_id"],
                    "hard_constraints": agent_result["hard_constraints"],
                    "state_drift": None,
                    "degradation": degradation,
                    "would_hit_b1": agent_result["would_hit_b1"],
                    "effective_hit_b1": agent_result["effective_hit_b1"],
                    "would_hit_b2": agent_result["would_hit_b2"],
                    "effective_hit_b2": agent_result["effective_hit_b2"],
                    "cache_stats_at_turn": agent_result["cache_stats_at_turn"],
                    "rule_score": rule_score,
                    "judge_score": judge_score,
                    "answer_text": agent_result["answer_text"][:2000],
                    "retrieved_top_k": agent_result["retrieved_top_k"][:10],
                    "script_version_hash": script_hash,
                    "product_list_hash": product_hash,
                    "condition_config_hash": condition_hash,
                }
                self._write_turn(trace_dict)
        finally:
            # 恢复环境变量
            for key, value in saved_env.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)

    async def _invoke_agent(self, agent, turn: ScriptTurn, session_id: str) -> dict:
        """调 agent.handle_message() 并解析事件流以收集 trace 字段。"""
        request = ChatRequest(type="user_message", session_id=session_id, message=turn.query)
        events = await agent.handle_message(request)

        # 解析事件流
        answer_text_parts = []
        retrieved_top_k = []
        pipeline = []
        tool_calls = []
        branch_flags = {}

        for event in events:
            event_type = event.get("type")
            if event_type == "text_delta":
                answer_text_parts.append(event.get("text", ""))
            elif event_type == "product_item":
                product = event.get("product", {})
                if isinstance(product, dict):
                    product_id = product.get("product_id")
                    if product_id:
                        retrieved_top_k.append(product_id)
            elif event_type == "assistant_state":
                intent = event.get("intent")
                if intent:
                    pipeline.append(intent)
                if event.get("memory_mode"):
                    branch_flags["memory_mode"] = event.get("memory_mode")

        # 从 agent 读取缓存探针信息
        probe = getattr(agent, "_last_cache_probe", {}) or {}
        degradation = getattr(agent, "_last_degradation", None)

        return {
            "answer_text": "".join(answer_text_parts),
            "retrieved_top_k": retrieved_top_k,
            "pipeline": pipeline,
            "tool_calls": tool_calls,
            "branch_flags": branch_flags,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "first_chunk_ms": 0,
            "context_payload_bytes": 0,
            "context_payload_tokens": 0,
            "context_events_count": 0,
            "focus_history_len": 0,
            "focus_product_id": None,
            "hard_constraints": {},
            "would_hit_b1": probe.get("would_hit_b1", False),
            "effective_hit_b1": probe.get("effective_hit_b1", False),
            "would_hit_b2": probe.get("would_hit_b2", False),
            "effective_hit_b2": probe.get("effective_hit_b2", False),
            "cache_stats_at_turn": probe.get("cache_stats_b2", {}) or probe.get("cache_stats", {}),
            "degradation": degradation,
        }
