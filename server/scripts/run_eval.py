from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

server_dir = Path(__file__).resolve().parent.parent
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from backend.app.eval.runner import load_scenarios, run_scenarios, write_attribution_csv
from backend.app.main import create_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenarios",
        default="../data/eval/shopguide_core_scenarios.json",
    )
    parser.add_argument("--attribution-output-dir", default=None)
    parser.add_argument("--attribution-detail-csv", default=None)
    parser.add_argument("--attribution-summary-csv", default=None)
    args = parser.parse_args()
    app = create_app(use_fake_llm=True, use_fake_retriever=False)
    report = run_scenarios(app, load_scenarios(Path(args.scenarios)))
    detail_csv = Path(args.attribution_detail_csv) if args.attribution_detail_csv else None
    summary_csv = Path(args.attribution_summary_csv) if args.attribution_summary_csv else None
    if args.attribution_output_dir:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(args.attribution_output_dir)
        detail_csv = detail_csv or output_dir / f"eval_{stamp}_attribution_detail.csv"
        summary_csv = summary_csv or output_dir / f"eval_{stamp}_attribution_summary.csv"
    if detail_csv or summary_csv:
        if not detail_csv or not summary_csv:
            raise SystemExit("Both attribution detail and summary CSV paths are required")
        write_attribution_csv(report, detail_csv, summary_csv)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
