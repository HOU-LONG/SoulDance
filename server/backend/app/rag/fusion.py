from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from ..constraint_filter import hard_filter
from ..db import get_session
from ..models import Product, RetrievalPlan
from .lexical_search import lexical_search_chunks
from .vector_search import vector_search_chunks


def rrf_fuse(
    lexical_results: list[tuple[str, float]],
    vector_results: list[tuple[str, float]],
    top_k: int = 30,
    k: int = 60,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranked_list in (lexical_results, vector_results):
        for rank, (product_id, _) in enumerate(ranked_list, start=1):
            scores[product_id] = scores.get(product_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]


class HybridRetriever:
    def __init__(self, base_retriever, session_factory=get_session):
        self.base_retriever = base_retriever
        self.session_factory = session_factory
        self.products: list[Product] = list(getattr(base_retriever, "products", []) or [])
        self.product_map = {product.product_id: product for product in self.products}

    def search(self, plan: RetrievalPlan, top_k: int = 30) -> list[tuple[Product, float]]:
        if not self.product_map:
            return []
        query = plan.retrieval_query or ""
        with self.session_factory() as session:
            lexical_results = lexical_search_chunks(
                session,
                query,
                plan.hard_constraints,
                top_k=max(top_k * 4, 30),
            )
            vector_results = self._vector_results(session, query, plan, top_k=max(top_k * 4, 30))
        fused = rrf_fuse(lexical_results, vector_results, top_k=max(top_k * 2, top_k))
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
        return vector_search_chunks(session, query_vector, plan.hard_constraints, top_k=top_k)

    def _encode_query(self, query: str) -> np.ndarray | None:
        model = getattr(self.base_retriever, "model", None)
        if model is None:
            return None
        vector = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        return np.asarray(vector, dtype=float)
