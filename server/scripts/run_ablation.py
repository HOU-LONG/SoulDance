"""消融实验脚本：跑配置矩阵 + 输出 CSV。

设计：
- 每个配置（fusion_strategy × dense_weight × rrf_k）独立构造一个 app
- 对带 golden_id 的 scenario 计算 Recall@K / NDCG@K
- 不带 golden_id 的 scenario 只统计通过率
- 输出 CSV：每行一个 (config, scenario)，包含通过率和 IR 指标

用法：
  python scripts/run_ablation.py --scenarios ../data/eval/recommend.json --output ../data/eval/
  python scripts/run_ablation.py --tag recommend --output ../data/eval/

环境变量驱动：每轮 run 前重置 lru_cache 让 get_settings 重新读取。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

server_dir = Path(__file__).resolve().parent.parent
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))


@dataclass
class AblationConfig:
    """一组检索超参，对应一行评测。"""

    strategy: str
    dense_weight: float
    rrf_k: int

    @property
    def label(self) -> str:
        if self.strategy in {"dense_only", "bm25_only"}:
            return self.strategy
        if self.strategy == "weighted":
            return f"weighted(α={self.dense_weight:.2f})"
        return f"rrf(k={self.rrf_k})"


def build_config_matrix(
    dense_weights: list[float],
    rrf_ks: list[int],
) -> list[AblationConfig]:
    matrix: list[AblationConfig] = []
    matrix.append(AblationConfig("bm25_only", 0.0, 60))
    matrix.append(AblationConfig("dense_only", 1.0, 60))
    for w in dense_weights:
        matrix.append(AblationConfig("weighted", w, 60))
    for k in rrf_ks:
        matrix.append(AblationConfig("rrf", 0.65, k))
    return matrix


def apply_config_to_env(config: AblationConfig) -> None:
    """把配置写入环境变量，供下一次 get_settings() 读取。"""
    os.environ["RETRIEVAL_FUSION_STRATEGY"] = config.strategy
    os.environ["RETRIEVAL_DENSE_WEIGHT"] = f"{config.dense_weight:.4f}"
    os.environ["RETRIEVAL_RRF_K"] = str(config.rrf_k)


def reset_settings_cache() -> None:
    """清掉 get_settings 的 lru_cache，确保新一轮读到新的环境变量。"""
    from backend.app.config import get_settings

    get_settings.cache_clear()


def load_golden() -> dict[str, dict]:
    path = Path(__file__).resolve().parents[2] / "data" / "eval" / "golden_products.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def run_one_config(
    config: AblationConfig,
    scenarios,
    golden: dict[str, dict],
    *,
    per_scenario_timeout: int,
) -> list[dict]:
    """单一配置下跑全部 scenario，返回每个 scenario 的指标 dict。"""
    apply_config_to_env(config)
    reset_settings_cache()

    # 必须在 env 设置后再 import / create_app
    from backend.app.eval.metrics import compute_ranking_metrics
    from backend.app.eval.runner import _run_scenario
    from backend.app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(use_fake_llm=False, use_fake_retriever=False)
    client = TestClient(app)

    class _TimeoutError(Exception):
        pass

    def _handler(_signum, _frame):
        raise _TimeoutError("scenario exceeded timeout")

    rows: list[dict] = []
    for scenario in scenarios:
        signal.signal(signal.SIGALRM, _handler)
        signal.alarm(per_scenario_timeout)
        t1 = time.time()
        try:
            result = _run_scenario(app, client, scenario)
            passed = result.passed
            product_ids = result.product_ids
        except _TimeoutError:
            passed, product_ids = False, []
        except Exception:
            passed, product_ids = False, []
        finally:
            signal.alarm(0)
        dt = time.time() - t1

        # IR 指标：只对带 golden_id 的 scenario 计算
        ir_metrics: dict[str, float] = {}
        golden_id = scenario.golden_id
        if golden_id and golden_id in golden:
            ideal_top = golden[golden_id].get("ideal_top", [])
            ir_metrics = compute_ranking_metrics(product_ids, ideal_top, k_values=(5, 10))

        rows.append(
            {
                "config": config.label,
                "strategy": config.strategy,
                "dense_weight": config.dense_weight,
                "rrf_k": config.rrf_k,
                "scenario": scenario.id,
                "golden_id": golden_id or "",
                "passed": int(passed),
                "elapsed_s": round(dt, 2),
                "predicted_top": ",".join(product_ids[:5]),
                "recall@5": ir_metrics.get("recall@5", ""),
                "ndcg@5": ir_metrics.get("ndcg@5", ""),
                "recall@10": ir_metrics.get("recall@10", ""),
                "ndcg@10": ir_metrics.get("ndcg@10", ""),
            }
        )
        print(f"    [{'PASS' if passed else 'FAIL'} {dt:5.1f}s] {scenario.id}", flush=True)
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    """按 config 聚合：通过率、平均 Recall@5、平均 NDCG@5。"""
    by_config: dict[str, list[dict]] = {}
    for row in rows:
        by_config.setdefault(row["config"], []).append(row)
    summary = []
    for config_label, group in by_config.items():
        total = len(group)
        passed = sum(r["passed"] for r in group)
        ir_rows = [r for r in group if r["recall@5"] != ""]
        if ir_rows:
            avg_recall5 = sum(float(r["recall@5"]) for r in ir_rows) / len(ir_rows)
            avg_ndcg5 = sum(float(r["ndcg@5"]) for r in ir_rows) / len(ir_rows)
        else:
            avg_recall5 = avg_ndcg5 = float("nan")
        summary.append(
            {
                "config": config_label,
                "scenarios": total,
                "pass_rate": round(passed / total, 3) if total else 0,
                "avg_recall@5": round(avg_recall5, 3) if avg_recall5 == avg_recall5 else "",
                "avg_ndcg@5": round(avg_ndcg5, 3) if avg_ndcg5 == avg_ndcg5 else "",
                "ir_n": len(ir_rows),
            }
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenarios",
        default="../data/eval/recommend.json",
        help="scenario 文件或目录。默认只跑 recommend（带 golden_id 的子集）",
    )
    parser.add_argument(
        "--tag",
        action="append",
        help="按 tag 过滤 scenario",
    )
    parser.add_argument(
        "--output",
        default="../data/eval/",
        help="CSV 输出目录",
    )
    parser.add_argument(
        "--dense-weights",
        type=lambda s: [float(x) for x in s.split(",")],
        default=[0.3, 0.5, 0.65, 0.8],
        help="weighted 策略的 α 值列表，逗号分隔",
    )
    parser.add_argument(
        "--rrf-ks",
        type=lambda s: [int(x) for x in s.split(",")],
        default=[30, 60, 100],
        help="rrf 策略的 k 值列表，逗号分隔",
    )
    parser.add_argument(
        "--per-scenario-timeout",
        type=int,
        default=60,
        help="单 scenario 超时秒数",
    )
    args = parser.parse_args()

    # 延迟 import 以便先解析 args（这里没用，但保持习惯）
    from backend.app.eval.runner import load_scenarios

    scenarios = load_scenarios(Path(args.scenarios))
    if args.tag:
        wanted = set(args.tag)
        scenarios = [s for s in scenarios if wanted & set(s.tags)]
    if not scenarios:
        print("no scenarios matched", file=sys.stderr)
        return 1

    golden = load_golden()
    matrix = build_config_matrix(args.dense_weights, args.rrf_ks)
    print(f"=== ablation: {len(matrix)} configs × {len(scenarios)} scenarios ===")

    all_rows: list[dict] = []
    total_t0 = time.time()
    for config in matrix:
        print(f"\n--- {config.label} ---", flush=True)
        # 清掉 carts.json，避免跨 config 累积
        carts_path = Path(__file__).resolve().parents[2] / "data" / "carts.json"
        if carts_path.exists():
            carts_path.unlink()
        rows = run_one_config(
            config, scenarios, golden, per_scenario_timeout=args.per_scenario_timeout
        )
        all_rows.extend(rows)

    print(f"\n=== ablation finished in {time.time() - total_t0:.0f}s ===")

    # 写 CSV
    timestamp = "ablation_" + time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_path = output_dir / f"{timestamp}_detail.csv"
    summary_path = output_dir / f"{timestamp}_summary.csv"

    with detail_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    summary = summarize(all_rows)
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)

    print(f"\ndetail:  {detail_path}")
    print(f"summary: {summary_path}")
    print("\n=== Summary ===")
    print(f"{'config':<22} {'pass':>6} {'recall@5':>10} {'ndcg@5':>8} {'ir_n':>5}")
    for row in summary:
        print(
            f"  {row['config']:<20} "
            f"{row['pass_rate']:>6.1%} "
            f"{row['avg_recall@5']!s:>10} "
            f"{row['avg_ndcg@5']!s:>8} "
            f"{row['ir_n']:>5}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
