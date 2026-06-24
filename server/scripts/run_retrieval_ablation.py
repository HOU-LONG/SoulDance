from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

server_dir = Path(__file__).resolve().parent.parent
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from backend.app.config import get_settings
from backend.app.eval.retrieval_ablation import (
    default_ablation_configs,
    run_default_retrieval_ablation,
    write_retrieval_ablation_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default="../data/eval/retrieval_ablation_scenarios.json")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--detail-csv", default=None)
    parser.add_argument("--summary-csv", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--reset-index", action="store_true")
    args = parser.parse_args()

    detail_csv = Path(args.detail_csv) if args.detail_csv else None
    summary_csv = Path(args.summary_csv) if args.summary_csv else None
    if args.output_dir:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(args.output_dir)
        detail_csv = detail_csv or output_dir / f"ablation_{stamp}_detail.csv"
        summary_csv = summary_csv or output_dir / f"ablation_{stamp}_summary.csv"
    if not detail_csv or not summary_csv:
        raise SystemExit("Either --output-dir or both --detail-csv and --summary-csv are required")

    settings = get_settings()
    report = run_default_retrieval_ablation(
        scenario_path=Path(args.scenarios),
        dataset_path=settings.dataset_path,
        embedding_model_dir=settings.embedding_path,
        embedding_device=settings.embedding_device,
        use_embedding=settings.use_embedding,
        configs=default_ablation_configs(),
        top_k=args.top_k,
        reset_index=args.reset_index,
    )
    write_retrieval_ablation_csv(report, detail_csv, summary_csv)
    print(f"detail_csv={detail_csv}")
    print(f"summary_csv={summary_csv}")
    for config, row in report.summary.items():
        print(
            f"{config}: pass_rate={row.pass_rate:.3f} "
            f"recall@5={row.avg_recall_at_5:.3f} "
            f"ndcg@5={row.avg_ndcg_at_5:.3f} "
            f"primary@1={row.primary_hit_at_1:.3f} n={row.ir_n}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
