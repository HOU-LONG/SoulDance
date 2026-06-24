from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .constraint_filter import hard_filter
from .models import Product, RankedProduct, RetrievalPlan
from .response_contract import recommendation_contract_text


class StructuredMemoryCache:
    """Small in-process cache for deterministic recommendation results."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._items: dict[str, list[dict[str, Any]]] = {}
        self._hits = 0
        self._misses = 0
        self._writes = 0
        if self.path and self.path.exists():
            self._load()

    def get(
        self,
        plan: RetrievalPlan,
        product_map: dict[str, Product],
        *,
        disable_get: bool = False,
    ) -> list[RankedProduct] | None:
        if disable_get:
            return None
        key = self.make_key(plan)
        rows = self._items.get(key)
        if not rows:
            self._misses += 1
            return None
        ranked: list[RankedProduct] = []
        for row in rows:
            product = product_map.get(str(row.get("product_id", "")))
            if not product or not hard_filter(product, plan.hard_constraints):
                continue
            ranked.append(
                RankedProduct(
                    product=product,
                    score=float(row.get("score", 0.0)),
                    tier=int(row.get("tier", 3)),
                    reason=str(row.get("reason", "")),
                    evidence=list(row.get("evidence", [])),
                )
            )
        if not ranked:
            self._misses += 1
            return None
        self._hits += 1
        return ranked

    def probe(self, plan: RetrievalPlan, product_map: dict[str, Product]) -> bool:
        """Pure: 仅判断是否能命中，不改任何 stats。"""
        key = self.make_key(plan)
        rows = self._items.get(key)
        if not rows:
            return False
        for row in rows:
            product = product_map.get(str(row.get("product_id", "")))
            if product and hard_filter(product, plan.hard_constraints):
                return True
        return False

    def put(self, plan: RetrievalPlan, ranked: list[RankedProduct]) -> None:
        key = self.make_key(plan)
        rows = [
            {
                "product_id": item.product.product_id,
                "score": item.score,
                "tier": item.tier,
                "reason": item.reason,
                "evidence": item.evidence,
            }
            for item in ranked
        ]
        self._items[key] = rows
        self._writes += 1
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"key": key, "rows": rows}, ensure_ascii=False) + "\n")

    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "writes": self._writes, "size": len(self._items)}

    def make_key(self, plan: RetrievalPlan) -> str:
        constraints = plan.hard_constraints.model_dump(mode="json")
        payload = {
            "intent": plan.intent,
            "retrieval_mode": plan.retrieval_mode,
            "category": plan.category,
            "hard_constraints": _sort_lists(constraints),
            "soft_preferences": dict(sorted(plan.soft_preferences.items())),
            "query": _normalize_query(plan.retrieval_query),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load(self) -> None:
        if not self.path:
            return
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = str(data.get("key", ""))
                rows = data.get("rows", [])
                if key and isinstance(rows, list):
                    self._items[key] = rows


class RecommendationMemoryHit:
    def __init__(self, mode: str, ranked: list[RankedProduct], summary: str):
        self.mode = mode
        self.ranked = ranked
        self.summary = summary


class RecommendationMemoryCache:
    """Structured product-decision memory above retrieval/rank cache."""

    SEMANTIC_SCAN_LIMIT = 100
    SEMANTIC_MIN_SCORE = 0.25

    def __init__(self, path: str | Path | None = None, catalog_fingerprint: str = "demo_catalog_v1"):
        self.path = Path(path) if path else None
        self.catalog_fingerprint = catalog_fingerprint
        self._items: dict[str, dict[str, Any]] = {}
        self._exact_hits = 0
        self._semantic_hits = 0
        self._misses = 0
        self._writes = 0
        self._invalidations = 0
        if self.path and self.path.exists():
            self._load()

    def get(
        self,
        plan: RetrievalPlan,
        message: str,
        product_map: dict[str, Product],
        *,
        disable_get: bool = False,
    ) -> RecommendationMemoryHit | None:
        if disable_get:
            return None
        exact_key = self.make_exact_key(plan, message)
        row = self._items.get(exact_key)
        if row:
            hit = self._validated_hit(row, plan, product_map, "exact_hit")
            if hit:
                self._exact_hits += 1
                return hit
            self._invalidations += 1
        semantic_row = self._find_semantic_row(plan, message)
        if semantic_row:
            hit = self._validated_hit(semantic_row, plan, product_map, "semantic_hit")
            if hit:
                self._semantic_hits += 1
                return hit
            self._invalidations += 1
        self._misses += 1
        return None

    def probe(
        self,
        plan: RetrievalPlan,
        message: str,
        product_map: dict[str, Product],
    ) -> bool:
        """Pure: 仅判断 exact 或 semantic 是否能命中，不改任何 stats / _invalidations。"""
        exact_key = self.make_exact_key(plan, message)
        row = self._items.get(exact_key)
        if row and self._validated_hit_dry(row, plan, product_map):
            return True
        semantic_row = self._find_semantic_row(plan, message)
        if semantic_row and self._validated_hit_dry(semantic_row, plan, product_map):
            return True
        return False

    def _validated_hit_dry(
        self,
        row: dict[str, Any],
        plan: RetrievalPlan,
        product_map: dict[str, Product],
    ) -> bool:
        """与 _validated_hit 同逻辑但不构造 RankedProduct，仅返回 True/False。"""
        for item in row.get("selected_products", []):
            product = product_map.get(str(item.get("product_id", "")))
            if not product or not hard_filter(product, plan.hard_constraints):
                return False
            taxonomy = row.get("taxonomy", {})
            expected_sub = taxonomy.get("sub_category")
            expected_cat = taxonomy.get("category")
            if expected_sub and product.sub_category != expected_sub:
                return False
            if expected_cat and product.category != expected_cat:
                return False
        return bool(row.get("selected_products"))

    def put(self, plan: RetrievalPlan, message: str, selected: list[RankedProduct]) -> None:
        if not selected:
            return
        key = self.make_exact_key(plan, message)
        entry = {
            "key": key,
            "normalized_query": _normalize_query(message or plan.retrieval_query),
            "retrieval_query": _normalize_query(plan.retrieval_query),
            "taxonomy": {
                "category": plan.hard_constraints.category,
                "sub_category": plan.hard_constraints.sub_category,
                "plan_category": plan.category,
            },
            "hard_constraints": _sort_lists(plan.hard_constraints.model_dump(mode="json")),
            "soft_preferences": dict(sorted(plan.soft_preferences.items())),
            "selected_products": [
                {
                    "product_id": item.product.product_id,
                    "role": "primary" if index == 0 else "alternative",
                    "score": item.score,
                    "tier": item.tier,
                    "reason": item.reason,
                    "evidence": item.evidence,
                }
                for index, item in enumerate(selected[:4])
            ],
            "short_response_summary": _short_response_summary(plan, selected),
            "source": "llm_selection_v1",
            "catalog_fingerprint": self.catalog_fingerprint,
            "prompt_version": "semantic_v2/selection_v1/response_v2",
        }
        self._items[key] = entry
        self._writes += 1
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def stats(self) -> dict[str, int]:
        return {
            "exact_hits": self._exact_hits,
            "semantic_hits": self._semantic_hits,
            "misses": self._misses,
            "writes": self._writes,
            "invalidations": self._invalidations,
            "size": len(self._items),
        }

    def make_exact_key(self, plan: RetrievalPlan, message: str) -> str:
        payload = {
            "intent": plan.intent,
            "retrieval_mode": plan.retrieval_mode,
            "normalized_query": _normalize_query(message or plan.retrieval_query),
            "taxonomy": {
                "category": plan.hard_constraints.category,
                "sub_category": plan.hard_constraints.sub_category,
                "plan_category": plan.category,
            },
            "hard_constraints": _sort_lists(plan.hard_constraints.model_dump(mode="json")),
            "catalog_fingerprint": self.catalog_fingerprint,
            "prompt_version": "semantic_v2/selection_v1/response_v2",
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _find_semantic_row(self, plan: RetrievalPlan, message: str) -> dict[str, Any] | None:
        current_taxonomy = {
            "category": plan.hard_constraints.category,
            "sub_category": plan.hard_constraints.sub_category,
            "plan_category": plan.category,
        }
        current_constraints = _sort_lists(plan.hard_constraints.model_dump(mode="json"))
        current_preferences = dict(sorted(plan.soft_preferences.items()))
        current_tokens = _memory_tokens(message or plan.retrieval_query)
        best_row = None
        best_score = 0.0
        rows = list(self._items.values())[-self.SEMANTIC_SCAN_LIMIT :]
        for row in rows:
            if row.get("catalog_fingerprint") != self.catalog_fingerprint:
                continue
            if row.get("taxonomy") != current_taxonomy:
                continue
            if row.get("hard_constraints") != current_constraints:
                continue
            if row.get("soft_preferences", {}) != current_preferences:
                continue
            score = _token_similarity(current_tokens, _memory_tokens(str(row.get("normalized_query", ""))))
            if score > best_score:
                best_score = score
                best_row = row
        if best_row and best_score >= self.SEMANTIC_MIN_SCORE:
            return best_row
        return None

    def _validated_hit(
        self,
        row: dict[str, Any],
        plan: RetrievalPlan,
        product_map: dict[str, Product],
        mode: str,
    ) -> RecommendationMemoryHit | None:
        ranked: list[RankedProduct] = []
        for item in row.get("selected_products", []):
            product = product_map.get(str(item.get("product_id", "")))
            if not product or not hard_filter(product, plan.hard_constraints):
                return None
            taxonomy = row.get("taxonomy", {})
            expected_sub = taxonomy.get("sub_category")
            expected_cat = taxonomy.get("category")
            if expected_sub and product.sub_category != expected_sub:
                return None
            if expected_cat and product.category != expected_cat:
                return None
            ranked.append(
                RankedProduct(
                    product=product,
                    score=float(item.get("score", 0.0)),
                    tier=int(item.get("tier", 1)),
                    reason=str(item.get("reason", "")),
                    evidence=list(item.get("evidence", [])),
                )
            )
        if not ranked:
            return None
        return RecommendationMemoryHit(mode, ranked, str(row.get("short_response_summary", "")))

    def _load(self) -> None:
        if not self.path:
            return
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = str(row.get("key", ""))
                if key and isinstance(row.get("selected_products"), list):
                    self._items[key] = row


def _sort_lists(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sort_lists(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return sorted(_sort_lists(item) for item in value)
    return value


def _normalize_query(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return re.sub(r"[，。！？、,.!?]", " ", text)



def _memory_tokens(text: str) -> set[str]:
    normalized = _normalize_query(text)
    stop_words = {"推荐", "想买", "一款", "一个", "一下", "帮我", "给我", "买", "找", "的", "个"}
    tokens = {part for part in re.split(r"\s+", normalized) if part and part not in stop_words}
    for word in ["防晒霜", "防晒", "精华液", "精华", "手机", "电脑", "笔记本", "清爽"]:
        if word in normalized:
            tokens.add(word)
    return tokens


def _token_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _short_response_summary(plan: RetrievalPlan, selected: list[RankedProduct]) -> str:
    primary = selected[0]
    constraints: list[str] = []
    if plan.hard_constraints.price_min is not None:
        constraints.append(f"预算 {plan.hard_constraints.price_min:.0f} 元以上")
    if plan.hard_constraints.price_max is not None:
        constraints.append(f"预算 {plan.hard_constraints.price_max:.0f} 元以内")
    if plan.hard_constraints.include_brands:
        constraints.append("指定品牌" + "、".join(plan.hard_constraints.include_brands))
    if plan.hard_constraints.exclude_terms:
        constraints.append("排除" + "、".join(plan.hard_constraints.exclude_terms))
    handled = "，".join(constraints) if constraints else "你的核心需求"
    alternatives = selected[1:4]
    alternatives_text = None
    if alternatives:
        alternatives_text = "备选差异：" + "；".join(f"{item.product.title}：{item.reason}" for item in alternatives) + "。"
    return recommendation_contract_text(
        understanding=f"我按「{handled}」理解你的需求，并复用了已验证的推荐结果。",
        conclusion=f"优先看「{primary.product.title}」，它仍然是这组条件下的主推。",
        primary_reason=f"{primary.reason}。",
        alternatives=alternatives_text,
        next_step="如果你想调整预算、避开某个品牌，或者看同类备选，我可以继续筛。",
    )
