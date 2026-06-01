from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .constraint_filter import hard_filter
from .models import Product, RankedProduct, RetrievalPlan


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

    def get(self, plan: RetrievalPlan, product_map: dict[str, Product]) -> list[RankedProduct] | None:
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


def _sort_lists(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sort_lists(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return sorted(_sort_lists(item) for item in value)
    return value


def _normalize_query(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return re.sub(r"[，。！？、,.!?]", " ", text)
