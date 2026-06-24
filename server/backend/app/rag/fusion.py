"""Hybrid retrieval and product-level fusion.

Dense retrieval can use a process-wide DenseIndex. Lexical retrieval keeps chunk evidence.
Fusion strategy is controlled by RetrievalConfig.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from ..config import RetrievalConfig
from ..constraint_filter import hard_filter
from ..db import get_session
from ..models import Product, RetrievalPlan
from .lexical_search import lexical_search_chunks
from .types import ChunkSearchResult, ProductRetrievalResult
from .vector_search import DenseIndex, vector_search_chunks

SearchResult = tuple[str, float] | ChunkSearchResult


def rrf_fuse(
    lexical_results: list[SearchResult],
    vector_results: list[SearchResult],
    top_k: int = 30,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion based on rank order, with optional evidence bonuses."""
    scores: dict[str, float] = {}
    for ranked_list in (lexical_results, vector_results):
        for rank, item in enumerate(ranked_list, start=1):
            product_id = _result_product_id(item)
            score_bonus = _result_score_bonus(item)
            scores[product_id] = scores.get(product_id, 0.0) + 1.0 / (k + rank) + score_bonus
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]


def weighted_fuse(
    lexical_results: list[SearchResult],
    vector_results: list[SearchResult],
    dense_weight: float,
    top_k: int = 30,
) -> list[tuple[str, float]]:
    """Weighted dense/BM25 fusion. Inputs are expected to be normalized."""
    bm25_weight = max(0.0, 1.0 - dense_weight)
    scores: dict[str, float] = {}
    for item in lexical_results:
        product_id = _result_product_id(item)
        scores[product_id] = scores.get(product_id, 0.0) + bm25_weight * _result_score(item)
    for item in vector_results:
        product_id = _result_product_id(item)
        scores[product_id] = scores.get(product_id, 0.0) + dense_weight * _result_score(item)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]


class HybridRetriever:
    """Hybrid lexical and vector retriever."""

    def __init__(
        self,
        base_retriever,
        session_factory=get_session,
        *,
        config: RetrievalConfig | None = None,
        dense_index: DenseIndex | None = None,
    ):
        self.base_retriever = base_retriever
        self.session_factory = session_factory
        self.config = config or RetrievalConfig()
        self.dense_index = dense_index
        self.products: list[Product] = list(getattr(base_retriever, "products", []) or [])
        self.product_map = {product.product_id: product for product in self.products}

    def search(self, plan: RetrievalPlan, top_k: int = 30) -> list[tuple[Product, float]]:
        return [(item.product, item.score) for item in self.search_with_evidence(plan, top_k=top_k)]

    def search_with_evidence(self, plan: RetrievalPlan, top_k: int = 30) -> list[ProductRetrievalResult]:
        if not self.product_map:
            return []
        query = plan.retrieval_query or ""
        recall_k = max(top_k * 4, self.config.top_k_recall)

        lexical_results: list[SearchResult] = []
        vector_results: list[SearchResult] = []
        strategy = self.config.fusion_strategy

        with self.session_factory() as session:
            if strategy != "dense_only":
                lexical_results = lexical_search_chunks(
                    session,
                    query,
                    plan.hard_constraints,
                    top_k=recall_k,
                )
            if strategy != "bm25_only":
                vector_results = self._vector_results(session, query, plan, top_k=recall_k)

        fused = self._fuse(lexical_results, vector_results, top_k=max(top_k * 2, top_k))
        evidence_by_product = _group_evidence([*lexical_results, *vector_results])
        results: list[ProductRetrievalResult] = []
        for product_id, score in fused:
            product = self.product_map.get(product_id)
            if product is None:
                continue
            if not hard_filter(product, plan.hard_constraints):
                continue
            results.append(
                ProductRetrievalResult(
                    product=product,
                    score=score,
                    evidence_chunks=evidence_by_product.get(product_id, [])[:5],
                )
            )
            if len(results) >= top_k:
                break
        return results

    def _fuse(
        self,
        lexical_results: list[SearchResult],
        vector_results: list[SearchResult],
        top_k: int,
    ) -> list[tuple[str, float]]:
        strategy = self.config.fusion_strategy
        if strategy == "dense_only":
            return [(_result_product_id(item), _result_score(item)) for item in vector_results[:top_k]]
        if strategy == "bm25_only":
            return [(_result_product_id(item), _result_score(item)) for item in lexical_results[:top_k]]
        if strategy == "rrf":
            return rrf_fuse(lexical_results, vector_results, top_k=top_k, k=self.config.rrf_k)
        return weighted_fuse(
            lexical_results,
            vector_results,
            dense_weight=self.config.dense_weight,
            top_k=top_k,
        )

    def _vector_results(
        self,
        session: Session,
        query: str,
        plan: RetrievalPlan,
        top_k: int,
    ) -> list[SearchResult]:
        query_vector = self._encode_query(query)
        if query_vector is None:
            return []
        return vector_search_chunks(
            session,
            query_vector,
            plan.hard_constraints,
            top_k=top_k,
            query=query,
            dense_index=self.dense_index,
        )

    def _encode_query(self, query: str) -> np.ndarray | None:
        model = getattr(self.base_retriever, "model", None)
        if model is None:
            return None
        vector = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        return np.asarray(vector, dtype=float)


def _group_evidence(results: list[SearchResult]) -> dict[str, list[ChunkSearchResult]]:
    grouped: dict[str, dict[str, ChunkSearchResult]] = {}
    chunks = [result for result in results if isinstance(result, ChunkSearchResult)]
    for result in sorted(chunks, key=lambda item: item.score, reverse=True):
        product_chunks = grouped.setdefault(result.product_id, {})
        if result.chunk_id not in product_chunks:
            product_chunks[result.chunk_id] = result
    return {product_id: list(chunks.values()) for product_id, chunks in grouped.items()}


def _result_product_id(item: SearchResult) -> str:
    if isinstance(item, ChunkSearchResult):
        return item.product_id
    return item[0]


def _result_score(item: SearchResult) -> float:
    if isinstance(item, ChunkSearchResult):
        return float(item.score)
    return float(item[1])


def _result_score_bonus(item: SearchResult) -> float:
    if isinstance(item, ChunkSearchResult):
        return item.score * 0.01
    return 0.0
