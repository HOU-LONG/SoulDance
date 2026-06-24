"""Dense vector retrieval.

Uses a process-wide product DenseIndex when available, and falls back to DB chunk embeddings while preserving evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from ..db.models import ProductChunk
from ..models import HardConstraints, Product
from .types import ChunkSearchResult, chunk_relevance_weight, chunk_result_from_orm


@dataclass
class DenseIndex:
    """Product-level dense index."""

    product_ids: list[str]
    matrix: np.ndarray
    product_meta: dict[str, tuple[str, str]]

    @property
    def is_empty(self) -> bool:
        return self.matrix.size == 0

    def search(
        self,
        query_vector: np.ndarray,
        constraints: HardConstraints,
        top_k: int = 30,
    ) -> list[tuple[str, float]]:
        if self.is_empty:
            return []
        query_vec = np.asarray(query_vector, dtype=float)
        if query_vec.shape[-1] != self.matrix.shape[1]:
            return []
        scores = self.matrix @ query_vec
        normalized = _normalize(scores)
        allowed = self._allowed_indices(constraints)
        if not allowed:
            return []
        ranked = [(self.product_ids[i], float(normalized[i])) for i in allowed]
        return sorted(ranked, key=lambda item: item[1], reverse=True)[:top_k]

    def _allowed_indices(self, constraints: HardConstraints) -> list[int]:
        allowed: list[int] = []
        for idx, product_id in enumerate(self.product_ids):
            category, sub_category = self.product_meta.get(product_id, ("", ""))
            if constraints.category and category != constraints.category:
                continue
            if constraints.sub_category and sub_category != constraints.sub_category:
                continue
            allowed.append(idx)
        return allowed


def build_dense_index(
    products: list[Product],
    embeddings: np.ndarray | None,
) -> DenseIndex:
    """Build a DenseIndex from product embeddings."""
    if embeddings is None or embeddings.size == 0 or len(products) == 0:
        return DenseIndex(product_ids=[], matrix=np.zeros((0, 0)), product_meta={})
    if embeddings.shape[0] != len(products):
        return DenseIndex(product_ids=[], matrix=np.zeros((0, 0)), product_meta={})
    product_ids = [product.product_id for product in products]
    meta = {
        product.product_id: (product.category or "", product.sub_category or "")
        for product in products
    }
    return DenseIndex(
        product_ids=product_ids,
        matrix=np.asarray(embeddings, dtype=float),
        product_meta=meta,
    )


def load_dense_index_from_db(
    session: Session,
    products: list[Product],
    expected_dim: int,
) -> DenseIndex | None:
    """Rebuild a DenseIndex from cached ProductChunk embeddings."""
    if not products or expected_dim <= 0:
        return None
    chunk_rows = (
        session.query(
            ProductChunk.product_id,
            ProductChunk.embedding,
            ProductChunk.chunk_type,
            ProductChunk.document_version,
        )
        .filter(
            ProductChunk.is_active.is_(True),
            ProductChunk.embedding.is_not(None),
        )
        .all()
    )
    best: dict[str, list[float]] = {}
    best_version: dict[str, int] = {}
    for product_id, embedding, chunk_type, version in chunk_rows:
        if not isinstance(embedding, list) or len(embedding) != expected_dim:
            continue
        if chunk_type and chunk_type != "description":
            continue
        if version >= best_version.get(product_id, -1):
            best[product_id] = embedding
            best_version[product_id] = version
    if len(best) != len(products):
        return None
    matrix = np.asarray([best[product.product_id] for product in products], dtype=float)
    return build_dense_index(products, matrix)


def vector_search_chunks(
    session: Session,
    query_vector: np.ndarray,
    constraints: HardConstraints,
    top_k: int = 30,
    query: str = "",
    *,
    dense_index: DenseIndex | None = None,
) -> list[ChunkSearchResult] | list[tuple[str, float]]:
    """Dense retrieval entry point.

    Prefer the supplied product-level DenseIndex; otherwise use DB chunk embeddings and return ChunkSearchResult evidence.
    """
    if dense_index is not None:
        return dense_index.search(query_vector, constraints, top_k=top_k)
    rows = _load_active_embeddings(session, constraints)
    if not rows:
        return []
    query_vec = np.asarray(query_vector, dtype=float)
    raw_scores: list[tuple[ProductChunk, float]] = []
    for chunk in rows:
        vector = np.asarray(chunk.embedding, dtype=float)
        if vector.shape != query_vec.shape:
            continue
        raw_scores.append((chunk, float(np.dot(vector, query_vec))))
    if not raw_scores:
        return []
    scores = _normalize(np.asarray([score for _, score in raw_scores], dtype=float))
    results: list[ChunkSearchResult] = []
    for (chunk, _), score in zip(raw_scores, scores):
        weighted = float(score) * chunk_relevance_weight(
            query,
            chunk.chunk_type,
            chunk.source_type,
            chunk.trust_level,
        )
        results.append(chunk_result_from_orm(chunk, weighted))
    return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]


def _load_active_embeddings(
    session: Session,
    constraints: HardConstraints,
) -> list[ProductChunk]:
    query = session.query(ProductChunk).filter(
        ProductChunk.is_active.is_(True),
        ProductChunk.embedding.is_not(None),
    )
    if constraints.category:
        query = query.filter(ProductChunk.category_id == constraints.category)
    if constraints.sub_category:
        query = query.filter(ProductChunk.sub_category == constraints.sub_category)
    return [
        chunk
        for chunk in query.all()
        if isinstance(chunk.embedding, list) and chunk.embedding
    ]


def _normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    min_score = float(scores.min())
    max_score = float(scores.max())
    if max_score == min_score:
        if max_score == 0:
            return np.zeros_like(scores)
        return np.ones_like(scores)
    return (scores - min_score) / (max_score - min_score)
