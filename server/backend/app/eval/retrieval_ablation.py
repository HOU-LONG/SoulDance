from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from ..constraint_filter import hard_filter
from ..data_loader import load_products
from ..db import get_session, init_db
from ..db.seed import seed_products
from ..embedding_retriever import EmbeddingRetriever
from ..models import HardConstraints, Product
from ..rag.fusion import rrf_fuse
from ..rag.lexical_search import lexical_search_chunks
from ..rag.vector_search import vector_search_chunks
from .models import EvalScenario


@dataclass(frozen=True)
class RetrievalAblationScenario:
    id: str
    query: str
    hard_constraints: HardConstraints = field(default_factory=HardConstraints)
    gold_product_ids: list[str] = field(default_factory=list)
    gold_primary_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievalAblationDetailRow:
    config: str
    scenario: str
    hit: bool
    recall_at_5: float
    ndcg_at_5: float
    primary_hit_at_1: float
    gold_ids: list[str]
    gold_primary_ids: list[str]
    predicted_top: str
    predicted_top5: list[str]
    miss_reason: str


@dataclass(frozen=True)
class RetrievalAblationSummaryRow:
    config: str
    pass_rate: float
    avg_recall_at_5: float
    avg_ndcg_at_5: float
    primary_hit_at_1: float
    ir_n: int


@dataclass(frozen=True)
class RetrievalAblationReport:
    detail: list[RetrievalAblationDetailRow]
    summary: dict[str, RetrievalAblationSummaryRow]


Ranker = Callable[[str, RetrievalAblationScenario, int], list[str]]


def load_retrieval_ablation_scenarios(path: str | Path) -> list[RetrievalAblationScenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [retrieval_ablation_scenario_from_mapping(item) for item in data]


def retrieval_ablation_scenario_from_mapping(raw: dict) -> RetrievalAblationScenario:
    hard = raw.get("hard_constraints") or {}
    return RetrievalAblationScenario(
        id=str(raw["id"]),
        query=str(raw["query"]),
        hard_constraints=HardConstraints.model_validate(hard),
        gold_product_ids=[str(item) for item in raw.get("gold_product_ids", [])],
        gold_primary_ids=[str(item) for item in raw.get("gold_primary_ids", [])],
    )


def retrieval_ablation_scenario_from_eval(scenario: EvalScenario) -> RetrievalAblationScenario:
    if not scenario.expect.gold_product_ids and not scenario.expect.expected_product_ids:
        raise ValueError(f"scenario {scenario.id} has no gold product ids")
    return RetrievalAblationScenario(
        id=scenario.id,
        query=scenario.message,
        hard_constraints=HardConstraints(
            price_max=scenario.expect.price_max,
            exclude_terms=list(scenario.expect.forbid_terms),
        ),
        gold_product_ids=list(scenario.expect.gold_product_ids or scenario.expect.expected_product_ids),
        gold_primary_ids=list(scenario.expect.gold_primary_ids or scenario.expect.gold_product_ids or scenario.expect.expected_product_ids),
    )


def run_retrieval_ablation(
    scenarios: list[RetrievalAblationScenario],
    *,
    products_by_id: dict[str, object],
    ranker: Ranker,
    configs: list[str],
    top_k: int = 5,
) -> RetrievalAblationReport:
    detail: list[RetrievalAblationDetailRow] = []
    for config in configs:
        for scenario in scenarios:
            predicted = _dedupe([str(item) for item in ranker(config, scenario, top_k)])[:top_k]
            detail.append(_score_detail_row(config, scenario, predicted, products_by_id, top_k))
    return RetrievalAblationReport(detail=detail, summary=_summarize_detail(detail, configs))


def write_retrieval_ablation_csv(
    report: RetrievalAblationReport,
    detail_path: str | Path,
    summary_path: str | Path,
) -> None:
    detail_path = Path(detail_path)
    summary_path = Path(summary_path)
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    detail_fields = [
        "config",
        "scenario",
        "hit",
        "recall_at_5",
        "ndcg_at_5",
        "primary_hit_at_1",
        "gold_ids",
        "gold_primary_ids",
        "predicted_top",
        "predicted_top5",
        "miss_reason",
    ]
    with detail_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields)
        writer.writeheader()
        for row in report.detail:
            writer.writerow(
                {
                    "config": row.config,
                    "scenario": row.scenario,
                    "hit": row.hit,
                    "recall_at_5": row.recall_at_5,
                    "ndcg_at_5": row.ndcg_at_5,
                    "primary_hit_at_1": row.primary_hit_at_1,
                    "gold_ids": "|".join(row.gold_ids),
                    "gold_primary_ids": "|".join(row.gold_primary_ids),
                    "predicted_top": row.predicted_top,
                    "predicted_top5": "|".join(row.predicted_top5),
                    "miss_reason": row.miss_reason,
                }
            )
    summary_fields = ["config", "pass_rate", "avg_recall_at_5", "avg_ndcg_at_5", "primary_hit_at_1", "ir_n"]
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        for config, row in report.summary.items():
            writer.writerow(
                {
                    "config": config,
                    "pass_rate": row.pass_rate,
                    "avg_recall_at_5": row.avg_recall_at_5,
                    "avg_ndcg_at_5": row.avg_ndcg_at_5,
                    "primary_hit_at_1": row.primary_hit_at_1,
                    "ir_n": row.ir_n,
                }
            )


def default_ablation_configs() -> list[str]:
    return [
        "bm25_only",
        "dense_only",
        "weighted(alpha=0.30)",
        "weighted(alpha=0.50)",
        "weighted(alpha=0.65)",
        "weighted(alpha=0.80)",
        "rrf(k=30)",
        "rrf(k=60)",
        "rrf(k=100)",
    ]


def run_default_retrieval_ablation(
    *,
    scenario_path: str | Path,
    dataset_path: str | Path,
    embedding_model_dir: str | Path,
    embedding_device: str,
    use_embedding: bool,
    configs: list[str] | None = None,
    top_k: int = 5,
    reset_index: bool = False,
) -> RetrievalAblationReport:
    scenarios = load_retrieval_ablation_scenarios(scenario_path)
    products = load_products(dataset_path)
    retriever = EmbeddingRetriever(products, embedding_model_dir, embedding_device, use_embedding=use_embedding)
    _ensure_dense_model_available(retriever, use_embedding)
    init_db()
    with get_session() as session:
        seed_products(products, session, retriever, reset=reset_index)
    products_by_id = {product.product_id: product for product in products}
    ranker = ChunkAblationRanker(products, retriever)
    return run_retrieval_ablation(
        scenarios,
        products_by_id=products_by_id,
        ranker=ranker.rank,
        configs=configs or default_ablation_configs(),
        top_k=top_k,
    )


def _ensure_dense_model_available(retriever: EmbeddingRetriever, use_embedding: bool) -> None:
    if not use_embedding:
        return
    if getattr(retriever, "model", None) is None or getattr(retriever, "embeddings", None) is None:
        raise RuntimeError(
            "Embedding model unavailable for retrieval ablation; "
            "set EMBEDDING_MODEL_DIR to an existing model path or run with USE_EMBEDDING=0."
        )


class ChunkAblationRanker:
    def __init__(self, products: list[Product], retriever: EmbeddingRetriever):
        self.products = products
        self.product_map = {product.product_id: product for product in products}
        self.retriever = retriever

    def rank(self, config: str, scenario: RetrievalAblationScenario, top_k: int) -> list[str]:
        fetch_k = max(top_k * 6, 30)
        if config == "bm25_only":
            return self._bm25_rank(scenario, fetch_k)[:top_k]
        if config == "dense_only":
            return self._dense_rank(scenario, fetch_k)[:top_k]
        if config.startswith("weighted"):
            alpha = _parse_float_between(config, "alpha=", default=0.65)
            return self._weighted_rank(scenario, fetch_k, alpha)[:top_k]
        if config.startswith("rrf"):
            k = int(_parse_float_between(config, "k=", default=60))
            return self._rrf_rank(scenario, fetch_k, k)[:top_k]
        raise ValueError(f"unknown ablation config: {config}")

    def _bm25_rank(self, scenario: RetrievalAblationScenario, top_k: int) -> list[str]:
        with get_session() as session:
            results = lexical_search_chunks(session, scenario.query, scenario.hard_constraints, top_k=top_k)
        return _dedupe([result.product_id for result in results if self._passes_constraints(result.product_id, scenario)])

    def _dense_rank(self, scenario: RetrievalAblationScenario, top_k: int) -> list[str]:
        query_vector = self._query_vector(scenario.query)
        if query_vector is None:
            return []
        with get_session() as session:
            results = vector_search_chunks(session, query_vector, scenario.hard_constraints, top_k=top_k, query=scenario.query)
        return _dedupe([result.product_id for result in results if self._passes_constraints(result.product_id, scenario)])

    def _weighted_rank(self, scenario: RetrievalAblationScenario, top_k: int, alpha: float) -> list[str]:
        bm25 = self._scored_bm25(scenario, top_k)
        dense = self._scored_dense(scenario, top_k)
        scores: dict[str, float] = {}
        for product_id in set(bm25) | set(dense):
            scores[product_id] = (1 - alpha) * bm25.get(product_id, 0.0) + alpha * dense.get(product_id, 0.0)
        return self._sort_scores(scores)

    def _rrf_rank(self, scenario: RetrievalAblationScenario, top_k: int, k: int) -> list[str]:
        bm25 = list(self._scored_bm25(scenario, top_k).items())
        dense = list(self._scored_dense(scenario, top_k).items())
        return [product_id for product_id, _ in rrf_fuse(bm25, dense, top_k=top_k, k=k)]

    def _scored_bm25(self, scenario: RetrievalAblationScenario, top_k: int) -> dict[str, float]:
        with get_session() as session:
            rows = lexical_search_chunks(session, scenario.query, scenario.hard_constraints, top_k=top_k)
        return self._best_score_by_product(rows, scenario)

    def _scored_dense(self, scenario: RetrievalAblationScenario, top_k: int) -> dict[str, float]:
        query_vector = self._query_vector(scenario.query)
        if query_vector is None:
            return {}
        with get_session() as session:
            rows = vector_search_chunks(session, query_vector, scenario.hard_constraints, top_k=top_k, query=scenario.query)
        return self._best_score_by_product(rows, scenario)

    def _best_score_by_product(self, rows, scenario: RetrievalAblationScenario) -> dict[str, float]:
        scores: dict[str, float] = {}
        for row in rows:
            if not self._passes_constraints(row.product_id, scenario):
                continue
            scores[row.product_id] = max(scores.get(row.product_id, 0.0), float(row.score))
        return scores

    def _sort_scores(self, scores: dict[str, float]) -> list[str]:
        return [product_id for product_id, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]

    def _query_vector(self, query: str) -> np.ndarray | None:
        model = getattr(self.retriever, "model", None)
        if model is None:
            return None
        vector = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        return np.asarray(vector, dtype=float)

    def _passes_constraints(self, product_id: str, scenario: RetrievalAblationScenario) -> bool:
        product = self.product_map.get(product_id)
        return product is not None and hard_filter(product, scenario.hard_constraints)


def _score_detail_row(
    config: str,
    scenario: RetrievalAblationScenario,
    predicted: list[str],
    products_by_id: dict[str, object],
    top_k: int,
) -> RetrievalAblationDetailRow:
    gold_ids = list(scenario.gold_product_ids)
    primary_ids = list(scenario.gold_primary_ids or gold_ids)
    predicted_top5 = predicted[:top_k]
    hit = any(gold_id in predicted_top5 for gold_id in gold_ids)
    recall = 1.0 if hit else 0.0
    primary_hit = 1.0 if predicted_top5 and predicted_top5[0] in primary_ids else 0.0
    ndcg = _ndcg_at_k(predicted_top5, gold_ids, top_k)
    return RetrievalAblationDetailRow(
        config=config,
        scenario=scenario.id,
        hit=hit,
        recall_at_5=recall,
        ndcg_at_5=ndcg,
        primary_hit_at_1=primary_hit,
        gold_ids=gold_ids,
        gold_primary_ids=primary_ids,
        predicted_top=predicted_top5[0] if predicted_top5 else "",
        predicted_top5=predicted_top5,
        miss_reason=_classify_retrieval_miss(gold_ids, predicted_top5, products_by_id),
    )


def _classify_retrieval_miss(gold_ids: list[str], predicted: list[str], products_by_id: dict[str, object]) -> str:
    if not gold_ids:
        return "no_gold"
    if any(gold_id not in products_by_id for gold_id in gold_ids):
        return "gold_label_mismatch"
    if any(gold_id in predicted for gold_id in gold_ids):
        return "hit"
    return "retrieval_miss"


def _summarize_detail(
    detail: list[RetrievalAblationDetailRow],
    configs: Iterable[str],
) -> dict[str, RetrievalAblationSummaryRow]:
    summary: dict[str, RetrievalAblationSummaryRow] = {}
    for config in configs:
        rows = [row for row in detail if row.config == config]
        if not rows:
            summary[config] = RetrievalAblationSummaryRow(config, 0.0, 0.0, 0.0, 0.0, 0)
            continue
        summary[config] = RetrievalAblationSummaryRow(
            config=config,
            pass_rate=_mean(1.0 if row.hit else 0.0 for row in rows),
            avg_recall_at_5=_mean(row.recall_at_5 for row in rows),
            avg_ndcg_at_5=_mean(row.ndcg_at_5 for row in rows),
            primary_hit_at_1=_mean(row.primary_hit_at_1 for row in rows),
            ir_n=len(rows),
        )
    return summary


def _ndcg_at_k(predicted: list[str], gold_ids: list[str], top_k: int) -> float:
    if not gold_ids:
        return 0.0
    gold = set(gold_ids)
    dcg = 0.0
    for index, product_id in enumerate(predicted[:top_k], start=1):
        if product_id in gold:
            dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(gold), top_k)
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 0.0


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _parse_float_between(value: str, marker: str, default: float) -> float:
    if marker not in value:
        return default
    raw = value.split(marker, 1)[1].split(")", 1)[0]
    try:
        return float(raw)
    except ValueError:
        return default
