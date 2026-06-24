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


def _product_with(pid: str, title: str) -> Product:
    return _product(pid).model_copy(update={"title": title, "search_text": title})


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


class FakeEncoder:
    """Stub that returns scores looked up by query+passage string."""

    def __init__(self, score_map: dict[str, float] | None = None):
        self.score_map = score_map or {}
        self.calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs):
        # pairs is a list[[query, passage]] coming from CrossEncoderReranker
        self.calls.append([(q, p) for q, p in pairs])
        return [self.score_map.get(passage, 0.0) for _, passage in pairs]


class BrokenEncoder:
    def predict(self, pairs):
        raise RuntimeError("encoder boom")


class StubMetrics:
    def __init__(self):
        self.counters: dict[str, int] = {}

    def increment(self, name: str, value: int = 1):
        self.counters[name] = self.counters.get(name, 0) + value


class TestCrossEncoderReranker:
    def _result_with_title(self, pid: str, title: str, score: float) -> ProductRetrievalResult:
        return ProductRetrievalResult(
            product=_product_with(pid, title),
            score=score,
            evidence_chunks=[],
        )

    def test_reorders_by_query_relevance(self):
        from backend.app.rag.reranker import CrossEncoderReranker

        candidates = [
            self._result_with_title("p1", "winter coat", 0.5),
            self._result_with_title("p2", "running shoes", 0.5),
            self._result_with_title("p3", "running socks", 0.5),
        ]
        encoder = FakeEncoder(score_map={
            "winter coat": 0.1,
            "running shoes": 0.95,
            "running socks": 0.8,
        })
        rer = CrossEncoderReranker(encoder, output_top_k=10)
        result = rer.rerank("running gear", candidates, top_k=10)

        assert [r.product.product_id for r in result] == ["p2", "p3", "p1"]
        assert result[0].score == pytest.approx(0.95)
        assert result[1].score == pytest.approx(0.8)
        assert result[2].score == pytest.approx(0.1)

    def test_truncates_to_top_k(self):
        from backend.app.rag.reranker import CrossEncoderReranker

        candidates = [self._result_with_title(f"p{i}", f"text-{i}", 0.0) for i in range(20)]
        encoder = FakeEncoder(score_map={f"text-{i}": 1.0 - i * 0.01 for i in range(20)})
        rer = CrossEncoderReranker(encoder, output_top_k=5)
        result = rer.rerank("q", candidates, top_k=5)
        assert len(result) == 5
        assert [r.product.product_id for r in result] == [f"p{i}" for i in range(5)]

    def test_empty_candidates_returns_empty(self):
        from backend.app.rag.reranker import CrossEncoderReranker
        encoder = FakeEncoder()
        rer = CrossEncoderReranker(encoder)
        assert rer.rerank("q", [], top_k=5) == []

    def test_evidence_chunks_preserved_after_rerank(self):
        from backend.app.rag.reranker import CrossEncoderReranker
        from backend.app.rag.types import ChunkSearchResult

        chunk = ChunkSearchResult(
            product_id="p1", chunk_id="c1", sku_id=None,
            category_id="cat", sub_category="sub", chunk_type="specification",
            source_type="official_detail", trust_level="official",
            document_version=1, content="evidence for p1", score=0.9,
        )
        c1 = ProductRetrievalResult(
            product=_product_with("p1", "t1"),
            score=0.5,
            evidence_chunks=[chunk],
        )
        encoder = FakeEncoder(score_map={"evidence for p1": 0.99})
        result = CrossEncoderReranker(encoder).rerank("q", [c1], top_k=5)
        assert result[0].evidence_chunks == [chunk]
        # uses evidence chunk excerpt over product title
        assert encoder.calls[0][0] == ("q", "evidence for p1")

    def test_encoder_exception_falls_back_to_input_order(self):
        from backend.app.rag.reranker import CrossEncoderReranker

        c1 = self._result_with_title("p1", "a", 0.5)
        c2 = self._result_with_title("p2", "b", 0.5)
        metrics = StubMetrics()
        rer = CrossEncoderReranker(BrokenEncoder(), metrics=metrics)

        result = rer.rerank("q", [c1, c2], top_k=10)
        assert [r.product.product_id for r in result] == ["p1", "p2"]
        assert metrics.counters.get("retrieval.reranker.fallback.cross_failed", 0) == 1

    def test_records_cross_latency_metric(self):
        from backend.app.rag.reranker import CrossEncoderReranker
        encoder = FakeEncoder(score_map={"a": 0.7})
        metrics = StubMetrics()
        rer = CrossEncoderReranker(encoder, metrics=metrics)
        rer.rerank("q", [self._result_with_title("p1", "a", 0.5)], top_k=5)
        # Just confirm latency counter was touched at least once
        assert any(name.startswith("retrieval.reranker.cross.calls") for name in metrics.counters)


class FakeLLMClient:
    """Stub LLM client. `responses` queue feeds chat_json_sync return values."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def chat_json_sync(self, messages, **kwargs):
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("no fake response queued")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class TestLLMReranker:
    def _result(self, pid: str) -> ProductRetrievalResult:
        return ProductRetrievalResult(product=_product(pid), score=0.5, evidence_chunks=[])

    def test_reorders_using_llm_output(self):
        from backend.app.rag.reranker import LLMReranker

        c1, c2, c3 = self._result("p1"), self._result("p2"), self._result("p3")
        llm = FakeLLMClient(responses=[
            [
                {"product_id": "p3", "rank": 1},
                {"product_id": "p1", "rank": 2},
                {"product_id": "p2", "rank": 3},
            ]
        ])
        rer = LLMReranker(llm, top_n=8)
        result = rer.rerank("query", [c1, c2, c3], top_k=8)
        assert [r.product.product_id for r in result] == ["p3", "p1", "p2"]

    def test_invalid_product_id_falls_back_to_input_order(self):
        from backend.app.rag.reranker import LLMReranker

        c1, c2 = self._result("p1"), self._result("p2")
        llm = FakeLLMClient(responses=[
            [{"product_id": "p99", "rank": 1}, {"product_id": "p100", "rank": 2}]
        ])
        metrics = StubMetrics()
        rer = LLMReranker(llm, metrics=metrics, top_n=8)
        result = rer.rerank("q", [c1, c2], top_k=8)
        assert [r.product.product_id for r in result] == ["p1", "p2"]
        assert metrics.counters.get("retrieval.reranker.fallback.llm_failed", 0) == 1

    def test_parse_error_falls_back(self):
        from backend.app.rag.reranker import LLMReranker

        c1 = self._result("p1")
        llm = FakeLLMClient(responses=[{"unexpected": "shape"}])
        metrics = StubMetrics()
        rer = LLMReranker(llm, metrics=metrics, top_n=8)
        result = rer.rerank("q", [c1], top_k=8)
        assert [r.product.product_id for r in result] == ["p1"]
        assert metrics.counters.get("retrieval.reranker.fallback.llm_failed", 0) == 1

    def test_llm_exception_falls_back(self):
        from backend.app.rag.reranker import LLMReranker

        c1 = self._result("p1")
        llm = FakeLLMClient(responses=[RuntimeError("boom")])
        metrics = StubMetrics()
        rer = LLMReranker(llm, metrics=metrics, top_n=8)
        result = rer.rerank("q", [c1], top_k=8)
        assert [r.product.product_id for r in result] == ["p1"]
        assert metrics.counters.get("retrieval.reranker.fallback.llm_failed", 0) == 1

    def test_partial_coverage_appends_remaining_in_input_order(self):
        from backend.app.rag.reranker import LLMReranker

        c1, c2, c3 = self._result("p1"), self._result("p2"), self._result("p3")
        llm = FakeLLMClient(responses=[
            [{"product_id": "p3", "rank": 1}]  # only p3 ranked
        ])
        rer = LLMReranker(llm, top_n=8)
        result = rer.rerank("q", [c1, c2, c3], top_k=8)
        assert [r.product.product_id for r in result] == ["p3", "p1", "p2"]
