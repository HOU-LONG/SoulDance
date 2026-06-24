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
