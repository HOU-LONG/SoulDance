from __future__ import annotations

import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from ..db.models import ProductChunk
from ..models import HardConstraints
from .types import ChunkSearchResult, chunk_relevance_weight, chunk_result_from_orm


def lexical_search_chunks(
    session: Session,
    query: str,
    constraints: HardConstraints,
    top_k: int = 30,
) -> list[ChunkSearchResult]:
    """Chunk-level BM25 search that preserves evidence for product-level fusion."""
    rows = _load_active_chunks(session, constraints)
    if not rows:
        return []
    tokenized = [_tokenize(chunk.content or "") for chunk in rows]
    if not any(tokenized):
        return []
    scores = BM25Okapi(tokenized).get_scores(_tokenize(query))
    scores = _normalize(np.asarray(scores, dtype=float))
    results: list[ChunkSearchResult] = []
    for chunk, score in zip(rows, scores):
        weighted = float(score) * chunk_relevance_weight(
            query,
            chunk.chunk_type,
            chunk.source_type,
            chunk.trust_level,
        )
        results.append(chunk_result_from_orm(chunk, weighted))
    return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]


def _load_active_chunks(
    session: Session,
    constraints: HardConstraints,
) -> list[ProductChunk]:
    query = session.query(ProductChunk).filter(ProductChunk.is_active.is_(True))
    if constraints.category:
        query = query.filter(ProductChunk.category_id == constraints.category)
    if constraints.sub_category:
        query = query.filter(ProductChunk.sub_category == constraints.sub_category)
    return list(query.all())


def _tokenize(text: str) -> list[str]:
    return [token.strip().lower() for token in jieba.lcut(text or "") if token.strip()]


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
