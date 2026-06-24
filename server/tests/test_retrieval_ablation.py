from pathlib import Path

from backend.app.eval.retrieval_ablation import (
    RetrievalAblationScenario,
    run_retrieval_ablation,
    write_retrieval_ablation_csv,
)
from backend.app.models import HardConstraints


class TinyRetriever:
    def __init__(self):
        self.products = []


def test_retrieval_ablation_outputs_summary_detail_and_miss_reason(tmp_path: Path):
    scenarios = [
        RetrievalAblationScenario(
            id="case_hit",
            query="sunscreen",
            hard_constraints=HardConstraints(category="beauty"),
            gold_product_ids=["p1"],
        )
    ]
    rankings = {
        "bm25_only": {"case_hit": ["p1", "p2"]},
        "dense_only": {"case_hit": ["p2"]},
    }

    report = run_retrieval_ablation(
        scenarios,
        products_by_id={"p1": object(), "p2": object()},
        ranker=lambda config, scenario, top_k: rankings[config][scenario.id][:top_k],
        configs=["bm25_only", "dense_only"],
    )

    assert report.summary["bm25_only"].pass_rate == 1.0
    assert report.summary["dense_only"].avg_recall_at_5 == 0.0
    assert report.detail[0].miss_reason == "hit"
    assert report.detail[1].miss_reason == "retrieval_miss"

    detail_path = tmp_path / "detail.csv"
    summary_path = tmp_path / "summary.csv"
    write_retrieval_ablation_csv(report, detail_path, summary_path)

    detail = detail_path.read_text(encoding="utf-8")
    summary = summary_path.read_text(encoding="utf-8")
    assert "config,scenario,hit,recall_at_5,ndcg_at_5,primary_hit_at_1,gold_ids,gold_primary_ids,predicted_top,predicted_top5,miss_reason" in detail
    assert "config,pass_rate,avg_recall_at_5,avg_ndcg_at_5,primary_hit_at_1,ir_n" in summary


def test_retrieval_ablation_primary_hit_uses_primary_gold_ids():
    scenario = RetrievalAblationScenario(
        id="case_primary",
        query="sunscreen",
        gold_product_ids=["p1", "p2"],
        gold_primary_ids=["p1"],
    )

    report = run_retrieval_ablation(
        [scenario],
        products_by_id={"p1": object(), "p2": object()},
        ranker=lambda config, scenario, top_k: ["p2", "p1"],
        configs=["bm25_only"],
    )

    row = report.detail[0]
    assert row.recall_at_5 == 1.0
    assert row.primary_hit_at_1 == 0.0


def test_retrieval_ablation_requires_dense_model_when_embedding_enabled():
    import pytest

    from backend.app.eval.retrieval_ablation import _ensure_dense_model_available

    retriever = type("Retriever", (), {"model": None, "embeddings": None})()

    with pytest.raises(RuntimeError, match="Embedding model unavailable"):
        _ensure_dense_model_available(retriever, use_embedding=True)


def test_retrieval_ablation_allows_missing_dense_model_when_embedding_disabled():
    from backend.app.eval.retrieval_ablation import _ensure_dense_model_available

    retriever = type("Retriever", (), {"model": None, "embeddings": None})()

    _ensure_dense_model_available(retriever, use_embedding=False)
