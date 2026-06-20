from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from ..db.models import ProductChunk
from ..models import HardConstraints


def vector_search_chunks(
    session: Session,
    query_vector: np.ndarray,
    constraints: HardConstraints,
    top_k: int = 30,
) -> list[tuple[str, float]]:
    rows = _load_active_embeddings(session, constraints)
    if not rows:
        return []
    query_vec = np.asarray(query_vector, dtype=float)
    raw_scores: list[tuple[str, float]] = []
    for product_id, embedding in rows:
        vector = np.asarray(embedding, dtype=float)
        if vector.shape != query_vec.shape:
            continue
        raw_scores.append((product_id, float(np.dot(vector, query_vec))))
    if not raw_scores:
        return []
    scores = _normalize(np.asarray([score for _, score in raw_scores], dtype=float))
    best_by_product: dict[str, float] = {}
    for (product_id, _), score in zip(raw_scores, scores):
        best_by_product[product_id] = max(best_by_product.get(product_id, 0.0), float(score))
    return sorted(best_by_product.items(), key=lambda item: item[1], reverse=True)[:top_k]


def _load_active_embeddings(
    session: Session,
    constraints: HardConstraints,
) -> list[tuple[str, list[float]]]:
    query = session.query(ProductChunk.product_id, ProductChunk.embedding).filter(
        ProductChunk.is_active.is_(True),
        ProductChunk.embedding.is_not(None),
    )
    if constraints.category:
        query = query.filter(ProductChunk.category_id == constraints.category)
    if constraints.sub_category:
        query = query.filter(ProductChunk.sub_category == constraints.sub_category)
    return [
        (product_id, embedding)
        for product_id, embedding in query.all()
        if isinstance(embedding, list) and embedding
    ]


def _normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    min_score = float(scores.min())
    max_score = float(scores.max())
    if max_score == min_score:
        return np.zeros_like(scores)
    return (scores - min_score) / (max_score - min_score)
