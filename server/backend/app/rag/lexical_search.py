from __future__ import annotations

import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from ..db.models import ProductChunk
from ..models import HardConstraints


def lexical_search_chunks(
    session: Session,
    query: str,
    constraints: HardConstraints,
    top_k: int = 30,
) -> list[tuple[str, float]]:
    """Chunk 级 BM25 + group-by-product 取 max。

    保留 chunk 级粒度是为了让 FAQ / review 这类长尾文本也能命中召回，
    最终在 product 级别归并取最高分。
    """
    rows = _load_active_chunks(session, constraints)
    if not rows:
        return []
    tokenized = [_tokenize(content) for _, content in rows]
    if not any(tokenized):
        return []
    scores = BM25Okapi(tokenized).get_scores(_tokenize(query))
    scores = _normalize(np.asarray(scores, dtype=float))
    best_by_product: dict[str, float] = {}
    for (product_id, _), score in zip(rows, scores):
        best_by_product[product_id] = max(best_by_product.get(product_id, 0.0), float(score))
    return sorted(best_by_product.items(), key=lambda item: item[1], reverse=True)[:top_k]


def _load_active_chunks(
    session: Session,
    constraints: HardConstraints,
) -> list[tuple[str, str]]:
    query = session.query(ProductChunk.product_id, ProductChunk.content).filter(
        ProductChunk.is_active.is_(True)
    )
    if constraints.category:
        query = query.filter(ProductChunk.category_id == constraints.category)
    if constraints.sub_category:
        query = query.filter(ProductChunk.sub_category == constraints.sub_category)
    return [(product_id, content or "") for product_id, content in query.all()]


def _tokenize(text: str) -> list[str]:
    return [token.strip().lower() for token in jieba.lcut(text or "") if token.strip()]


def _normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    min_score = float(scores.min())
    max_score = float(scores.max())
    if max_score == min_score:
        return np.zeros_like(scores)
    return (scores - min_score) / (max_score - min_score)
