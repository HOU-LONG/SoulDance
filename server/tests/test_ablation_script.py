"""Phase 4 验证：消融实验脚本核心函数。

只测纯函数（不真跑 LLM），保证：
- build_config_matrix 包含 bm25_only / dense_only / weighted(N) / rrf(M) 共 2+N+M 个 config
- summarize 正确聚合通过率和平均 IR 指标
- apply_config_to_env 写入正确环境变量
"""

from __future__ import annotations

import sys
from pathlib import Path

scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from run_ablation import (
    AblationConfig,
    apply_config_to_env,
    build_config_matrix,
    summarize,
)


def test_build_config_matrix_default():
    matrix = build_config_matrix(dense_weights=[0.5, 0.65], rrf_ks=[60, 100])
    # 2 个固定 (bm25_only / dense_only) + 2 个 weighted + 2 个 rrf
    assert len(matrix) == 6
    strategies = [c.strategy for c in matrix]
    assert strategies.count("bm25_only") == 1
    assert strategies.count("dense_only") == 1
    assert strategies.count("weighted") == 2
    assert strategies.count("rrf") == 2


def test_ablation_config_labels():
    assert AblationConfig("bm25_only", 0.0, 60).label == "bm25_only"
    assert AblationConfig("dense_only", 1.0, 60).label == "dense_only"
    assert AblationConfig("weighted", 0.65, 60).label == "weighted(α=0.65)"
    assert AblationConfig("rrf", 0.65, 100).label == "rrf(k=100)"


def test_apply_config_to_env_writes_expected_vars(monkeypatch):
    monkeypatch.delenv("RETRIEVAL_FUSION_STRATEGY", raising=False)
    monkeypatch.delenv("RETRIEVAL_DENSE_WEIGHT", raising=False)
    monkeypatch.delenv("RETRIEVAL_RRF_K", raising=False)
    apply_config_to_env(AblationConfig("rrf", 0.5, 30))
    import os

    assert os.environ["RETRIEVAL_FUSION_STRATEGY"] == "rrf"
    assert os.environ["RETRIEVAL_DENSE_WEIGHT"] == "0.5000"
    assert os.environ["RETRIEVAL_RRF_K"] == "30"


def test_summarize_aggregates_pass_rate_and_ir_metrics():
    rows = [
        {
            "config": "bm25_only",
            "scenario": "s1",
            "passed": 1,
            "recall@5": 1.0,
            "ndcg@5": 0.9,
        },
        {
            "config": "bm25_only",
            "scenario": "s2",
            "passed": 0,
            "recall@5": 0.5,
            "ndcg@5": 0.4,
        },
        {
            "config": "bm25_only",
            "scenario": "s3",
            "passed": 1,
            "recall@5": "",
            "ndcg@5": "",
        },
        {
            "config": "weighted(α=0.65)",
            "scenario": "s1",
            "passed": 1,
            "recall@5": 1.0,
            "ndcg@5": 1.0,
        },
    ]
    summary = summarize(rows)
    assert len(summary) == 2

    by_config = {row["config"]: row for row in summary}
    bm = by_config["bm25_only"]
    assert bm["scenarios"] == 3
    assert bm["pass_rate"] == round(2 / 3, 3)
    # 只算有 IR 指标的 2 行
    assert bm["ir_n"] == 2
    assert bm["avg_recall@5"] == 0.75
    assert bm["avg_ndcg@5"] == 0.65

    weighted = by_config["weighted(α=0.65)"]
    assert weighted["scenarios"] == 1
    assert weighted["pass_rate"] == 1.0
    assert weighted["ir_n"] == 1


def test_summarize_handles_no_ir_metrics():
    """全部 scenario 都没 golden_id 时，avg_recall@5 应该是空字符串而不是 NaN。"""
    rows = [
        {"config": "bm25_only", "scenario": "s1", "passed": 1, "recall@5": "", "ndcg@5": ""},
    ]
    summary = summarize(rows)
    assert summary[0]["avg_recall@5"] == ""
    assert summary[0]["avg_ndcg@5"] == ""
    assert summary[0]["ir_n"] == 0
