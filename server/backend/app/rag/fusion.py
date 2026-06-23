"""Hybrid 检索 + 多策略融合。

融合在 product 级别完成。dense 走内存矩阵（可选 dense_index），
BM25 走 chunk 级 + group-by-product max 保留长尾召回。
四种策略由 RetrievalConfig.fusion_strategy 切换：
- weighted: α·dense_norm + (1-α)·bm25_norm
- rrf: Σ 1/(k + rank)
- dense_only: 仅 dense
- bm25_only: 仅 BM25
"""

from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from ..config import RetrievalConfig
from ..constraint_filter import hard_filter
from ..db import get_session
from ..models import Product, RetrievalPlan
from .lexical_search import lexical_search_chunks
from .vector_search import DenseIndex, vector_search_chunks


def rrf_fuse(
    lexical_results: list[tuple[str, float]],
    vector_results: list[tuple[str, float]],
    top_k: int = 30,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: 不依赖原始分数尺度，只看 rank。"""
    scores: dict[str, float] = {}
    for ranked_list in (lexical_results, vector_results):
        for rank, (product_id, _) in enumerate(ranked_list, start=1):
            scores[product_id] = scores.get(product_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]


def weighted_fuse(
    lexical_results: list[tuple[str, float]],
    vector_results: list[tuple[str, float]],
    dense_weight: float,
    top_k: int = 30,
) -> list[tuple[str, float]]:
    """加权和融合: α·dense + (1-α)·bm25。输入分数应已 0-1 归一化。"""
    bm25_weight = max(0.0, 1.0 - dense_weight)
    scores: dict[str, float] = {}
    for product_id, score in lexical_results:
        scores[product_id] = scores.get(product_id, 0.0) + bm25_weight * score
    for product_id, score in vector_results:
        scores[product_id] = scores.get(product_id, 0.0) + dense_weight * score
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]


class HybridRetriever:
    """词法 + 向量混合检索器。

    设计：
    - dense 走传入的 DenseIndex（推荐路径，O(N·d) numpy 矩阵点积）。
    - BM25 走 chunk 级 + group-by-product max（保留 FAQ/review 级长尾召回）。
    - 融合策略由 RetrievalConfig 决定，所有超参可配置。
    - 硬约束在 product 级别二次过滤（基础检索内部已按 category 粗筛）。
    """

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
        if not self.product_map:
            return []
        query = plan.retrieval_query or ""
        recall_k = max(top_k * 4, self.config.top_k_recall)

        lexical_results: list[tuple[str, float]] = []
        vector_results: list[tuple[str, float]] = []
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
        results: list[tuple[Product, float]] = []
        for product_id, score in fused:
            product = self.product_map.get(product_id)
            if product is None:
                continue
            if not hard_filter(product, plan.hard_constraints):
                continue
            results.append((product, score))
            if len(results) >= top_k:
                break
        return results

    def _fuse(
        self,
        lexical_results: list[tuple[str, float]],
        vector_results: list[tuple[str, float]],
        top_k: int,
    ) -> list[tuple[str, float]]:
        strategy = self.config.fusion_strategy
        if strategy == "dense_only":
            return vector_results[:top_k]
        if strategy == "bm25_only":
            return lexical_results[:top_k]
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
    ) -> list[tuple[str, float]]:
        query_vector = self._encode_query(query)
        if query_vector is None:
            return []
        return vector_search_chunks(
            session,
            query_vector,
            plan.hard_constraints,
            top_k=top_k,
            dense_index=self.dense_index,
        )

    def _encode_query(self, query: str) -> np.ndarray | None:
        model = getattr(self.base_retriever, "model", None)
        if model is None:
            return None
        vector = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        return np.asarray(vector, dtype=float)
