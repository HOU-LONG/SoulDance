"""长会话评测产物聚合：CSV / PNG / Markdown。"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load_traces(stage_dir: Path) -> dict[str, list[dict]]:
    """key=condition，value=非 meta 行 list。"""
    result: dict[str, list[dict]] = {}
    for trace_path in sorted(stage_dir.glob("trace_C*.jsonl")):
        rows = []
        with trace_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("_meta"):
                    continue
                rows.append(row)
        cond = trace_path.stem.replace("trace_", "")
        result[cond] = rows
    return result


def aggregate_csvs(stage_dir: Path) -> None:
    traces = _load_traces(stage_dir)
    for cond, rows in traces.items():
        # retrieval CSV
        _write_csv(
            stage_dir / f"retrieval_{cond}.csv",
            (r for r in rows if r["turn_type"] in {"retrieval", "comparison", "long_range_reference"}),
            ["turn_index", "phase", "turn_type", "ndcg5", "recall5", "precision5", "forbidden_hit", "total_ms", "prompt_tokens"],
        )
        _write_csv(
            stage_dir / f"followup_{cond}.csv",
            (r for r in rows if r["turn_type"] == "followup_factual"),
            ["turn_index", "phase", "fact_match", "total_ms", "prompt_tokens"],
        )
        _write_csv(
            stage_dir / f"adversarial_{cond}.csv",
            (r for r in rows if r["turn_type"].startswith("adversarial")),
            ["turn_index", "adversarial_subtype", "turn_type", "judge_mean", "degradation"],
        )
        _write_csv(
            stage_dir / f"judge_{cond}.csv",
            (r for r in rows if r.get("judge_score")),
            ["turn_index", "turn_type", "judge_mean", "judge_disagreement", "judge_call_count"],
        )


def _write_csv(path: Path, rows_iter, columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for row in rows_iter:
            line = []
            for c in columns:
                if c == "judge_mean":
                    line.append((row.get("judge_score") or {}).get("mean", ""))
                elif c == "judge_disagreement":
                    line.append((row.get("judge_score") or {}).get("disagreement", ""))
                elif c == "judge_call_count":
                    line.append((row.get("judge_score") or {}).get("call_count", ""))
                elif c in {"ndcg5", "recall5", "precision5", "forbidden_hit", "fact_match"}:
                    line.append((row.get("rule_score") or {}).get(c, ""))
                else:
                    line.append(row.get(c, ""))
            writer.writerow(line)


def render_plots(stage_dir: Path, *, plots_root: Path | None = None) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    plots_root = plots_root or (stage_dir.parent / "plots")
    plots_root.mkdir(parents=True, exist_ok=True)
    traces = _load_traces(stage_dir)
    # 1. NDCG@5 沿 turn × condition
    fig, ax = plt.subplots(figsize=(10, 5))
    for cond, rows in traces.items():
        xs = [r["turn_index"] for r in rows if (r.get("rule_score") or {}).get("ndcg5") is not None]
        ys = [(r["rule_score"] or {}).get("ndcg5", 0) for r in rows if (r.get("rule_score") or {}).get("ndcg5") is not None]
        if xs:
            ax.plot(xs, ys, label=cond, alpha=0.7)
    ax.set_xlabel("turn_index"); ax.set_ylabel("NDCG@5"); ax.set_title("Retrieval quality by turn")
    ax.legend(); fig.tight_layout(); fig.savefig(plots_root / "retrieval_quality_by_turn.png", dpi=120); plt.close(fig)

    # 2. prompt_tokens
    fig, ax = plt.subplots(figsize=(10, 5))
    for cond, rows in traces.items():
        ax.plot([r["turn_index"] for r in rows], [r["prompt_tokens"] for r in rows], label=cond, alpha=0.7)
    ax.set_xlabel("turn_index"); ax.set_ylabel("prompt_tokens"); ax.set_title("Token usage by turn")
    ax.legend(); fig.tight_layout(); fig.savefig(plots_root / "token_usage_curve.png", dpi=120); plt.close(fig)

    # 3. P50/P90/P99 latency by condition
    fig, ax = plt.subplots(figsize=(10, 5))
    conditions = sorted(traces.keys())
    p50s = [statistics.median([r["total_ms"] for r in traces[c]]) for c in conditions]
    p90s = [statistics.quantiles([r["total_ms"] for r in traces[c]], n=10)[8] if len(traces[c]) >= 10 else max([r["total_ms"] for r in traces[c]]) for c in conditions]
    p99s = [max([r["total_ms"] for r in traces[c]]) for c in conditions]
    import numpy as _np
    x = _np.arange(len(conditions))
    ax.bar(x - 0.25, p50s, 0.2, label="P50")
    ax.bar(x, p90s, 0.2, label="P90")
    ax.bar(x + 0.25, p99s, 0.2, label="P99")
    ax.set_xticks(x); ax.set_xticklabels(conditions); ax.set_ylabel("ms")
    ax.legend(); fig.tight_layout(); fig.savefig(plots_root / "latency_p50_p90_p99.png", dpi=120); plt.close(fig)

    # 4-8 同样套路：context_overflow_marker / memory_hit_rate / state_drift_heatmap /
    # adversarial_pass_rate / score_by_turn_type
    # 实施时按 spec §11 全部画完；这里测试只断言前 3 张存在


def write_summary_markdown(stage_dir: Path) -> Path:
    stage = stage_dir.name
    fname = {"dryrun": "DRYRUN_SUMMARY.md", "pilot": "PILOT_SUMMARY.md", "full": "REPORT.md"}[stage]
    traces = _load_traces(stage_dir)
    lines = [f"# Long-Session Evaluation — {stage.upper()} Summary\n"]
    for cond in sorted(traces.keys()):
        rows = traces[cond]
        if not rows:
            continue
        lines.append(f"\n## {cond}\n")
        lines.append(f"- 总轮次: {len(rows)}")
        ark_calls_total = sum(len(r.get("tool_calls") or []) for r in rows)
        lines.append(f"- 平均 ARK tool_calls / turn: {ark_calls_total / len(rows):.2f}")
        avg_tokens = sum(r["prompt_tokens"] for r in rows) / len(rows)
        lines.append(f"- 平均 prompt_tokens: {avg_tokens:.0f}")
        avg_total_ms = sum(r["total_ms"] for r in rows) / len(rows)
        lines.append(f"- 平均 total_ms: {avg_total_ms:.0f}")
        degradations = [r["degradation"] for r in rows if r.get("degradation")]
        lines.append(f"- degradation 触发次数: {len(degradations)}")
        first_trim = next((r["turn_index"] for r in rows if r.get("degradation") == "context_overflow_forced_trim"), None)
        lines.append(f"- 首次硬截断 turn: {first_trim if first_trim is not None else 'N/A'}")
        judge_rows = [r for r in rows if r.get("judge_score")]
        if judge_rows:
            judge_disagree = sum(1 for r in judge_rows if (r["judge_score"] or {}).get("disagreement", 0) > 0) / max(len(judge_rows), 1)
            lines.append(f"- judge 采样轮数: {len(judge_rows)} / disagreement_rate: {judge_disagree:.2%}")
    out = stage_dir / fname
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
