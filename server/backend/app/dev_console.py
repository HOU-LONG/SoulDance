"""开发调试仪表盘 —— FastAPI APIRouter。

端点：
  GET  /dev              — 单文件 HTML 仪表盘
  GET  /dev/traces       — JSON：最近 50 条 trace
  GET  /dev/stats        — JSON：聚合统计
  GET  /dev/prompts      — 列出所有 prompt 文件
  POST /dev/prompts      — {name, content} 热更新 prompt 文件

零新依赖。Chart.js 从 CDN 引入，CSS/JS 全部内联 HTML。
数据源：trace_store 全局单例（TraceStore.append / recent / stats）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .prompt_registry import PromptRegistry
from .trace_store import get_trace_store

router = APIRouter(tags=["dev_console"])

# prompt 文件根目录：server/backend/app/prompts
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_prompt_registry = PromptRegistry(_PROMPTS_DIR)

# plan 类工具集合 —— 用于统计 plan 占比
_PLAN_TOOLS = {"recommend_product", "compare_products", "scenario_bundle", "product_followup"}


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class PromptUpdateRequest(BaseModel):
    name: str = Field(..., description="prompt 文件名（如 semantic_parser），不含 .txt 后缀")
    content: str = Field(..., description="新的 prompt 文本内容")


# ---------------------------------------------------------------------------
# HTML 仪表盘（单文件，Chart.js v4 CDN，深色主题 #1a1a2e）
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SoulDance Dev Console</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 24px; min-height: 100vh; }
h1 { font-size: 24px; font-weight: 600; margin-bottom: 4px; color: #ffffff; }
.subtitle { font-size: 13px; color: #8888aa; margin-bottom: 24px; }
/* stat cards */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: #16213e; border-radius: 12px; padding: 20px; border: 1px solid #2a2a4a; }
.card-label { font-size: 12px; color: #8888aa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.card-value { font-size: 28px; font-weight: 700; color: #e0e0ff; }
.card-unit { font-size: 13px; color: #8888aa; margin-left: 4px; }
/* charts row */
.charts { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 24px; }
.chart-box { background: #16213e; border-radius: 12px; padding: 20px; border: 1px solid #2a2a4a; }
.chart-box h2 { font-size: 15px; font-weight: 600; margin-bottom: 12px; color: #c0c0e0; }
.chart-box canvas { max-height: 300px; }
/* table */
.table-box { background: #16213e; border-radius: 12px; padding: 20px; border: 1px solid #2a2a4a; }
.table-box h2 { font-size: 15px; font-weight: 600; margin-bottom: 12px; color: #c0c0e0; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 8px 12px; border-bottom: 1px solid #2a2a4a; color: #8888aa; font-weight: 500; font-size: 12px; text-transform: uppercase; }
td { padding: 8px 12px; border-bottom: 1px solid #1e1e3a; white-space: nowrap; }
tr:hover td { background: rgba(255,255,255,0.03); }
td:nth-child(4) { max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.badge-plan { background: #2d4a7a; color: #8ab4f8; }
.badge-chat { background: #3a3a5a; color: #b0b0d0; }
.badge-cart { background: #5a3a2a; color: #f0b080; }
.badge-analysis { background: #2a5a3a; color: #80f0a0; }
.badge-followup { background: #4a2a5a; color: #c080f0; }
.badge-compare { background: #5a4a2a; color: #f0d080; }
.badge-bundle { background: #2a4a5a; color: #80d0f0; }
.badge-clarify { background: #5a2a3a; color: #f08090; }
/* error badge */
tr.error-row td { color: #f08090; }
@media (max-width: 768px) {
  .charts { grid-template-columns: 1fr; }
  .cards { grid-template-columns: repeat(2, 1fr); }
}
</style>
</head>
<body>
<h1>SoulDance Dev Console</h1>
<p class="subtitle">实时请求追踪 &middot; 每 5 秒自动刷新</p>

<div class="cards">
  <div class="card"><div class="card-label">平均延迟</div><div class="card-value" id="stat-latency">--<span class="card-unit">ms</span></div></div>
  <div class="card"><div class="card-label">平均 Token</div><div class="card-value" id="stat-tokens">--<span class="card-unit">/req</span></div></div>
  <div class="card"><div class="card-label">总请求数</div><div class="card-value" id="stat-total">--</div></div>
  <div class="card"><div class="card-label">Plan 占比</div><div class="card-value" id="stat-plan">--<span class="card-unit">%</span></div></div>
</div>

<div class="charts">
  <div class="chart-box">
    <h2>延时趋势（最近 50 条）</h2>
    <canvas id="latencyChart"></canvas>
  </div>
  <div class="chart-box">
    <h2>Tool 分布</h2>
    <canvas id="toolChart"></canvas>
  </div>
</div>

<div class="table-box">
  <h2>最近 20 条请求</h2>
  <div style="overflow-x:auto;">
    <table id="traceTable">
      <thead><tr><th>时间</th><th>延迟</th><th>Tool</th><th>用户消息</th><th>Tokens</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<script>
// ---- Tool badge mapping ----
var TOOL_CLASS = {
  recommend_product: 'badge-plan',
  product_followup: 'badge-followup',
  compare_products: 'badge-compare',
  scenario_bundle: 'badge-bundle',
  cart_operation: 'badge-cart',
  product_analysis: 'badge-analysis',
  chitchat: 'badge-chat',
  clarification: 'badge-clarify'
};

// ---- Chart.js 实例 ----
var latencyChart, toolChart;

function initCharts() {
  var ctx1 = document.getElementById('latencyChart').getContext('2d');
  latencyChart = new Chart(ctx1, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: '延迟 (ms)',
        data: [],
        borderColor: '#8ab4f8',
        backgroundColor: 'rgba(138,180,248,0.1)',
        borderWidth: 1.5,
        pointRadius: 2,
        pointHoverRadius: 4,
        tension: 0.3,
        fill: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#8888aa', maxTicksLimit: 10, font: { size: 10 } }, grid: { color: '#2a2a4a' } },
        y: { ticks: { color: '#8888aa', font: { size: 10 } }, grid: { color: '#2a2a4a' }, beginAtZero: true }
      },
      interaction: { intersect: false, mode: 'index' }
    }
  });

  var ctx2 = document.getElementById('toolChart').getContext('2d');
  toolChart = new Chart(ctx2, {
    type: 'doughnut',
    data: {
      labels: [],
      datasets: [{
        data: [],
        backgroundColor: ['#8ab4f8','#f0b080','#80f0a0','#c080f0','#f0d080','#80d0f0','#b0b0d0','#f08090'],
        borderColor: '#1a1a2e',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#c0c0e0', padding: 12, font: { size: 10 }, boxWidth: 10 } }
      }
    }
  });
}

// ---- 数据拉取与渲染 ----
async function fetchData() {
  try {
    var res1 = await fetch('/dev/stats');
    var res2 = await fetch('/dev/traces');
    var stats = await res1.json();
    var traces = await res2.json();
    renderStats(stats);
    renderLatencyChart(traces);
    renderToolChart(stats.tool_counts || {});
    renderTable(traces);
  } catch(e) { console.error('fetch error', e); }
}

function renderStats(s) {
  document.getElementById('stat-latency').innerHTML = (s.avg_latency_ms || 0).toFixed(1) + '<span class="card-unit">ms</span>';
  document.getElementById('stat-tokens').innerHTML = (s.avg_tokens_per_request || 0).toFixed(0) + '<span class="card-unit">/req</span>';
  document.getElementById('stat-total').textContent = s.total_requests || 0;
  document.getElementById('stat-plan').innerHTML = ((s.plan_ratio || 0) * 100).toFixed(1) + '<span class="card-unit">%</span>';
}

function renderLatencyChart(traces) {
  // traces 已由服务端按时间倒序返回；reverse 后得到正序用于折线图
  var recent = traces.slice(0, 50).reverse();
  var labels = recent.map(function(t) {
    var d = new Date(t.timestamp);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  });
  var data = recent.map(function(t) { return t.latency_ms || t.total_ms || 0; });
  latencyChart.data.labels = labels;
  latencyChart.data.datasets[0].data = data;
  latencyChart.update('none');
}

function renderToolChart(toolCounts) {
  var entries = Object.entries(toolCounts).sort(function(a, b) { return b[1] - a[1]; });
  toolChart.data.labels = entries.map(function(e) { return e[0]; });
  toolChart.data.datasets[0].data = entries.map(function(e) { return e[1]; });
  toolChart.update('none');
}

function renderTable(traces) {
  var tbody = document.querySelector('#traceTable tbody');
  var recent = traces.slice(0, 20);
  tbody.innerHTML = recent.map(function(t) {
    var d = new Date(t.timestamp);
    var timeStr = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    var cls = TOOL_CLASS[t.tool] || 'badge-chat';
    var msg = (t.user_message || '').substring(0, 60);
    var latency = (t.latency_ms || t.total_ms || 0).toFixed(0);
    var tokens = t.total_tokens || (t.plan_tokens || 0) + (t.response_tokens || 0);
    var errorRow = t.error ? ' class="error-row"' : '';
    return '<tr' + errorRow + '>' +
      '<td>' + timeStr + '</td>' +
      '<td>' + latency + ' ms</td>' +
      '<td><span class="badge ' + cls + '">' + (t.tool || 'unknown') + '</span></td>' +
      '<td title="' + escapeHtml(t.user_message || '') + '">' + escapeHtml(msg) + '</td>' +
      '<td>' + tokens + '</td>' +
      '</tr>';
  }).join('');
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ---- 启动 ----
initCharts();
fetchData();
setInterval(fetchData, 5000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def dev_dashboard():
    """返回单文件 HTML 仪表盘。"""
    return _DASHBOARD_HTML


@router.get("/traces")
async def dev_traces():
    """返回最近 50 条 trace 记录（JSON）。

    trace_store 原始字段的时间戳为 ISO 字符串、延迟字段为 total_ms；
    本端点统一映射为前端友好的 latency_ms / total_tokens。
    """
    store = get_trace_store()
    traces = store.recent(n=50)
    result: list[dict] = []
    for t in traces:
        d = t.model_dump(mode="json")
        d["latency_ms"] = t.total_ms
        d["total_tokens"] = (t.plan_tokens or 0) + (t.response_tokens or 0)
        result.append(d)
    return result


@router.get("/stats")
async def dev_stats():
    """返回聚合统计（JSON）。

    基于 trace_store.stats() 的原始数据，计算前端需要的 4 个指标卡：
    平均延迟、平均 token、总请求数、plan 占比。
    """
    store = get_trace_store()
    raw = store.stats()
    tool_counts: dict[str, int] = raw.get("tool_counts", {})
    plan_count = sum(v for k, v in tool_counts.items() if k in _PLAN_TOOLS)
    total = raw.get("total_records", 0)
    return {
        "avg_latency_ms": raw.get("avg_total_ms", 0.0),
        "avg_tokens_per_request": round(
            raw.get("avg_plan_tokens", 0.0) + raw.get("avg_response_tokens", 0.0), 1
        ),
        "total_requests": total,
        "plan_ratio": round(plan_count / total, 4) if total else 0.0,
        "tool_counts": tool_counts,
    }


@router.get("/prompts")
async def list_prompts():
    """列出 prompts 目录下所有可用的 prompt 文件及其大小。"""
    prompts_dir = _PROMPTS_DIR
    if not prompts_dir.exists():
        return {"prompts": [], "version": _prompt_registry.version}

    def _collect(base: Path, prefix: str = "") -> list[dict]:
        result: list[dict] = []
        for entry in sorted(base.iterdir()):
            rel = f"{prefix}/{entry.name}" if prefix else entry.name
            if entry.is_dir():
                result.extend(_collect(entry, rel))
            elif entry.suffix == ".txt":
                result.append({
                    "name": rel.replace(".txt", ""),
                    "path": str(entry.relative_to(prompts_dir)),
                    "size": entry.stat().st_size,
                })
        return result

    return {
        "prompts": _collect(prompts_dir),
        "version": _prompt_registry.version,
    }


@router.post("/prompts")
async def update_prompt(body: PromptUpdateRequest):
    """热更新指定 prompt 文件。

    写入 `${PROMPTS_DIR}/v1/${name}.txt`，并返回更新后的路径与大小。
    自动创建不存在的父目录。
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="invalid prompt name")

    target = _PROMPTS_DIR / _prompt_registry.version / f"{name}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")

    return {
        "status": "ok",
        "name": name,
        "path": str(target.relative_to(_PROMPTS_DIR.parent)),
        "size": len(body.content),
    }
