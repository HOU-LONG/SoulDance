from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

server_dir = Path(__file__).resolve().parent.parent
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from backend.app.eval.runner import load_scenarios, run_scenarios
from backend.app.main import create_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenarios",
        default="../data/eval/core.json",
        help="scenario 文件或目录（目录会合并所有 .json）",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=None,
        help="仅跑包含此 tag 的场景（可多次），不传则跑全部",
    )
    parser.add_argument(
        "--exclude-tag",
        action="append",
        default=None,
        help="排除包含此 tag 的场景（可多次）",
    )
    parser.add_argument(
        "--fake-llm",
        action="store_true",
        help="使用 FakeLLMClient 而非真实 API（CI 烟囱测试用，能力受限）",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=1.0,
        help="通过率门槛 [0.0, 1.0]。低于此值返回 exit 1。默认 1.0 (全部通过)。",
    )
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
