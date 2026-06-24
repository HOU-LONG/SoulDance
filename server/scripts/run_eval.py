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
        default="../data/eval/core.json",
        help="scenario file or directory; directories merge all .json files",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=None,
        help="run only scenarios containing this tag; may be repeated",
    )
    parser.add_argument(
        "--exclude-tag",
        action="append",
        default=None,
        help="exclude scenarios containing this tag; may be repeated",
    )
    parser.add_argument(
        "--fake-llm",
        action="store_true",
        help="use FakeLLMClient instead of the real API for CI smoke tests",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=1.0,
        help="minimum pass rate [0.0, 1.0]; below this exits 1; default 1.0",
    )
    parser.add_argument("--attribution-output-dir", default=None)
    parser.add_argument("--attribution-detail-csv", default=None)
    parser.add_argument("--attribution-summary-csv", default=None)
    args = parser.parse_args()

    app = create_app(use_fake_llm=args.fake_llm, use_fake_retriever=False)
    scenarios = load_scenarios(Path(args.scenarios))
    if args.tag:
        wanted = set(args.tag)
        scenarios = [s for s in scenarios if wanted & set(s.tags)]
    if args.exclude_tag:
        excluded = set(args.exclude_tag)
        scenarios = [s for s in scenarios if not (excluded & set(s.tags))]
    report = run_scenarios(app, scenarios)

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
    if report.total == 0:
        print("no scenarios matched", file=sys.stderr)
        return 1
    pass_rate = report.passed / report.total
    if pass_rate < args.min_pass_rate:
        print(
            f"pass_rate {pass_rate:.1%} below threshold {args.min_pass_rate:.1%}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
