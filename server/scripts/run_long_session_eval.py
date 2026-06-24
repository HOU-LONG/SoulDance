"""长会话评测 CLI。spec docs/superpowers/specs/2026-06-24-long-session-eval-design.md"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

server_dir = Path(__file__).resolve().parent.parent
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Long-session evaluation runner")
    p.add_argument("--stage", required=True, choices=["dryrun", "pilot", "full"])
    p.add_argument("--condition", choices=["C0", "C1", "C2", "C3", "C4"])
    p.add_argument("--reset-cache", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--report", action="store_true")
    p.add_argument("--turns", type=int, default=None, help="覆盖默认轮次（dryrun 20 / pilot 100 / full 1100）")
    p.add_argument("--judge-call-count", type=int, default=None)
    p.add_argument("--data-root", type=Path, default=None)
    return p.parse_args()


def _resolve_turns(stage: str, override: int | None) -> int:
    if override is not None:
        return override
    return {"dryrun": 20, "pilot": 100, "full": 1100}[stage]


def main() -> int:
    args = parse_args()
    # 互斥规则最先检查，不依赖其他模块
    if not args.report:
        if args.reset_cache and args.resume:
            print("ERROR: --reset-cache 与 --resume 互斥", file=sys.stderr)
            return 2
        if not args.reset_cache and not args.resume:
            print("ERROR: 必须传 --reset-cache 或 --resume 之一", file=sys.stderr)
            return 2
        if args.condition is None:
            print("ERROR: 非 report 模式必须传 --condition", file=sys.stderr)
            return 2

    # 延迟导入其他模块，这样测试可以先通过互斥检查
    import asyncio
    from backend.app.config import get_settings
    from backend.app.data_loader import load_products
    from backend.app.eval.long_session_judge import LongSessionJudge
    from backend.app.eval.long_session_report import (
        aggregate_csvs, render_plots, write_summary_markdown,
    )
    from backend.app.eval.long_session_runner import (
        LongSessionRunner, RunnerConfig,
    )
    from backend.app.eval.long_session_templates import build_long_session_script
    from backend.app.main import create_app  # 复用 agent 工厂

    settings = get_settings()
    products = load_products(settings.dataset_path)
    data_root = args.data_root or Path(os.getenv("SHOPGUIDE_EVAL_DATA_ROOT", "data/eval/long_session_2026-06-24"))
    if args.report:
        stage_dir = data_root / args.stage
        if not stage_dir.exists() or not any(stage_dir.glob("trace_*.jsonl")):
            print("no trace files found; nothing to summarize")
            return 0
        aggregate_csvs(stage_dir)
        render_plots(stage_dir, plots_root=data_root / "plots")
        out = write_summary_markdown(stage_dir)
        print(f"summary written: {out}")
        return 0

    async def _run_condition():
        config = RunnerConfig(
            stage=args.stage,
            condition=args.condition,
            data_root=data_root,
            mode="resume" if args.resume else "fresh",
        )
        runner = LongSessionRunner(config)
        # 配置独立 cache namespace 给 agent
        os.environ["SHOPGUIDE_MEMORY_CACHE_PATH"] = str(runner.cache_namespace / "recommendation.jsonl")
        judge_call = args.judge_call_count or (3 if args.stage == "dryrun" else 1)
        judge = LongSessionJudge(settings, call_count=judge_call)

        def agent_factory():
            # 重新 build app；create_app 内会按 env 注入 Settings
            app = create_app()
            return app.state.agent

        try:
            script = build_long_session_script(products)
            await runner.run(script[: _resolve_turns(args.stage, args.turns)],
                            products, agent_factory=agent_factory, judge=judge)
        finally:
            await judge.aclose()

    asyncio.run(_run_condition())
    return 0


if __name__ == "__main__":
    sys.exit(main())
