from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from ..db.models import ProductChunk
from ..models import HardConstraints
from .types import ChunkSearchResult, chunk_relevance_weight, chunk_result_from_orm


def vector_search_chunks(
    session: Session,
    query_vector: np.ndarray,
    constraints: HardConstraints,
    top_k: int = 30,
    query: str = "",
) -> list[ChunkSearchResult]:
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
