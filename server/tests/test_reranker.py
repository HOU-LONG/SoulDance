from __future__ import annotations

import pytest

from backend.app.models import Product
from backend.app.rag.reranker import NoOpReranker
from backend.app.rag.reranker_scenarios import RerankScenario
from backend.app.rag.types import ProductRetrievalResult


def _product(pid: str) -> Product:
    return Product(
        product_id=pid,
        title=f"product {pid}",
        brand="brand-a",
        category="shoes",
        sub_category="running",
        price=199.0,
        image_path="",
        marketing_description="",
        chunk="",
        search_text=f"product {pid}",
        brand_region="unknown",
        extracted_terms=[],
        review_rating=4.5,
    )


def _result(pid: str, score: float) -> ProductRetrievalResult:
    return ProductRetrievalResult(product=_product(pid), score=score, evidence_chunks=[])


class TestNoOpReranker:
    def test_preserves_input_order(self):
        candidates = [_result("p1", 0.9), _result("p2", 0.8), _result("p3", 0.7)]
        result = NoOpReranker().rerank("q", candidates, top_k=10)
        assert [r.product.product_id for r in result] == ["p1", "p2", "p3"]

    def test_truncates_to_top_k(self):
        candidates = [_result(f"p{i}", 1.0 - i * 0.01) for i in range(20)]
        result = NoOpReranker().rerank("q", candidates, top_k=5)
        assert len(result) == 5
        assert [r.product.product_id for r in result] == [f"p{i}" for i in range(5)]

    def test_empty_candidates_returns_empty(self):
        result = NoOpReranker().rerank("q", [], top_k=5)
        assert result == []

    def test_scenario_kwarg_is_accepted(self):
        candidates = [_result("p1", 0.9)]
        result = NoOpReranker().rerank("q", candidates, top_k=5, scenario=RerankScenario.COMPARISON)
        assert result == candidates
