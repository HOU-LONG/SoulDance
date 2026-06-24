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
