"""Reranker layer between HybridRetriever and rank_products.

Cross-encoder is the default, LLM is the fallback for strong scenarios.
All failure paths degrade silently — the caller never sees an exception.
"""

from __future__ import annotations

import logging
from typing import Protocol, Sequence, runtime_checkable

from .reranker_scenarios import RerankScenario
from .types import ProductRetrievalResult

_LOG = logging.getLogger(__name__)


@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 15,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]: ...


class NoOpReranker:
    """Returns input order, truncated to top_k. Used when rerank is disabled."""

    def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 15,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]:
        return list(candidates[:top_k])


class CrossEncoderReranker:
    """Local cross-encoder reranker. Wraps a sentence-transformers CrossEncoder model.

    `model` must expose `predict(pairs: list[[str, str]]) -> Sequence[float]`.
    Any exception silently falls back to input order; metric counter is bumped.
    """

    def __init__(
        self,
        model,
        *,
        metrics=None,
        output_top_k: int = 15,
    ):
        self.model = model
        self.metrics = metrics
        self.output_top_k = output_top_k

    def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 15,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]:
        if not candidates:
            return []
        cap = min(top_k, self.output_top_k)
        pairs = [[query, self._passage_text(c)] for c in candidates]
        try:
            scores = list(self.model.predict(pairs))
        except Exception:
            _LOG.warning("CrossEncoderReranker.predict failed", exc_info=True)
            if self.metrics is not None:
                self.metrics.increment("retrieval.reranker.fallback.cross_failed")
            return list(candidates[:cap])

        if self.metrics is not None:
            self.metrics.increment("retrieval.reranker.cross.calls")

        scored = list(zip(candidates, scores))
        scored.sort(key=lambda item: float(item[1]), reverse=True)
        reranked: list[ProductRetrievalResult] = []
        for candidate, score in scored[:cap]:
            reranked.append(
                ProductRetrievalResult(
                    product=candidate.product,
                    score=float(score),
                    evidence_chunks=candidate.evidence_chunks,
                )
            )
        return reranked

    @staticmethod
    def _passage_text(candidate: ProductRetrievalResult) -> str:
        if candidate.evidence_chunks:
            text = candidate.evidence_chunks[0].excerpt.strip()
            if text:
                return text
        product = candidate.product
        title = product.title or ""
        marketing = getattr(product, "marketing_description", "") or ""
        joined = (title + " " + marketing).strip()
        return joined[:256]


class LLMReranker:
    """List-wise LLM reranker.

    Expects llm_client.chat_json_sync(messages) to return a JSON list of
    {product_id, rank}. Any parse error or invalid product_id falls back
    to the input order silently.
    """

    SYSTEM_PROMPT = (
        "你是电商导购的重排器。根据用户查询，对候选商品按相关性从高到低排序。"
        "必须只输出 JSON 数组，格式为 [{\"product_id\": \"...\", \"rank\": 1}]."
        "不要输出任何解释。"
    )

    def __init__(self, llm_client, *, metrics=None, top_n: int = 8):
        self.llm_client = llm_client
        self.metrics = metrics
        self.top_n = top_n

    def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 8,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]:
        if not candidates:
            return []
        cap = min(top_k, self.top_n)
        input_window = list(candidates[:cap])

        try:
            ranked_ids = self._invoke_llm(query, input_window)
        except Exception:
            _LOG.warning("LLMReranker.invoke failed", exc_info=True)
            self._record_fallback()
            return input_window

        if ranked_ids is None:
            self._record_fallback()
            return input_window

        return self._reorder(ranked_ids, input_window)

    def _invoke_llm(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
    ) -> list[str] | None:
        payload = [
            {
                "product_id": c.product.product_id,
                "title": c.product.title,
                "brand": c.product.brand,
                "price": c.product.price,
                "evidence": [
                    chunk.excerpt for chunk in c.evidence_chunks[:3]
                ],
            }
            for c in candidates
        ]
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"用户查询：{query}\n候选商品：{payload}\n"
                    "请输出排序后的 JSON。"
                ),
            },
        ]
        response = self.llm_client.chat_json_sync(messages)
        if self.metrics is not None:
            self.metrics.increment("retrieval.reranker.llm.invoked")
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response) -> list[str] | None:
        if not isinstance(response, list):
            return None
        seen: list[str] = []
        for item in response:
            if not isinstance(item, dict):
                return None
            pid = item.get("product_id")
            if not isinstance(pid, str):
                return None
            seen.append(pid)
        return seen if seen else None

    def _reorder(
        self,
        ranked_ids: list[str],
        candidates: list[ProductRetrievalResult],
    ) -> list[ProductRetrievalResult]:
        by_id = {c.product.product_id: c for c in candidates}
        valid_ranked = [by_id[pid] for pid in ranked_ids if pid in by_id]
        # If nothing valid came back, treat as failure.
        if not valid_ranked:
            self._record_fallback()
            return candidates
        used = {c.product.product_id for c in valid_ranked}
        tail = [c for c in candidates if c.product.product_id not in used]
        return valid_ranked + tail

    def _record_fallback(self) -> None:
        if self.metrics is not None:
            self.metrics.increment("retrieval.reranker.fallback.llm_failed")
