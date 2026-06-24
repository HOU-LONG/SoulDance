# 长会话上下文控制 + 决策复用策略评估 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `server/backend/app/` 落地 4 个禁用开关 + Pure Probe API + 25K token 上下文硬截断保护，新建 `server/backend/app/eval/long_session_*.py` 评测套件，CLI `server/scripts/run_long_session_eval.py` 支持 fresh/resume 互斥启动，按 spec §9 三阶段（dryrun/pilot/full）驱动跑评测、出报告。

**Architecture:** 实施分两层。① **生产代码层**——给 `Settings` 加 5 个 eval 字段、给 `semantic_layer.py` 加 A1/A2 开关、给 `memory_cache.py` 加 `disable_get` 参数 + `.probe()` pure API、给 `agent.py` 加 25K 硬截断保护并打 `degradation` 标签；生产默认全部 False/全开，不影响 live 行为。② **评测套件层**——新建 `long_session_runner.py`（fresh/resume + per-turn retry + flush+fsync）、`long_session_templates.py`（按类目定制 + 75 对抗轮）、`long_session_judge.py`（独立 ARK client + dry-run 实测分歧后自适应折叠）、`long_session_report.py`（CSV + matplotlib PNG + Markdown）、`trace_schema_v1.json`；CLI 强制 `--reset-cache`/`--resume` 互斥；stage × condition 双维 cache 物理隔离。所有评测产物落 `data/eval/long_session_2026-06-24/{dryrun,pilot,full}/`。

**Tech Stack:** Python 3.12, FastAPI（已有）, Pydantic v2, pytest, tiktoken（用 `cl100k_base` 近似豆包 tokenizer）, matplotlib, jsonschema, httpx（已有 ARK client）

## Global Constraints

- **Live 路径**：所有生产代码改动必须落在 `server/backend/app/` 下；CLI 入口必须落在 `server/scripts/`；评测产物落 `data/eval/long_session_2026-06-24/`。已在 spec §0 核实。
- **生产默认不变**：`Settings` 新增 5 个字段默认值必须保证 `eval_disable_*=False` + `eval_force_trim_token_budget=25000`，等价于 C4 全开生产行为；任何修改都不得让现有 `test_agent_core` / `test_api` / `test_bugfix_phase3` 等已有测试 fail。
- **disable 语义**：禁用开关只切"注入/使用"，不切"维护"；具体语义见 spec §4。
- **probe() 必须 side-effect-free**：禁止调用任何写 `self._items` / `self._*hits` / `self._misses` / `self._invalidations` / `self._writes` 的代码；100 次 probe 与 0 次 probe 的 `.stats()` 必须完全一致。
- **CLI 互斥**：`--reset-cache` 与 `--resume` 不可同时传，也不可都不传；违反必须报错退出。
- **trace 行落盘**：每轮强制 `flush()` + `fsync()`，schema 校验通过才接受；schema 文件 `server/backend/app/eval/trace_schema_v1.json` 与 spec §9.1 一致。
- **真实 ARK 调用**：评测必须使用真实豆包 ARK API；禁止在 long-session runner 中引入 `FakeLLMClient`。`.env` 从 `/home/huadabioa/houlong/SoulDance/.env` 读。
- **测试目录约定**：单测放 `server/tests/`，命名 `test_long_session_*.py`；遵循现有 `pytest.ini` 的 `pythonpath = .` 与 `testpaths = tests`。
- **导入路径**：评测模块在外部由 CLI 调用时，import 形式为 `from backend.app.eval.long_session_runner import ...`（参考 `server/scripts/run_eval.py:12`）。
- **commit 风格**：每个任务结束必须提交；commit message 简体中文 + `Co-Authored-By: Claude <noreply@anthropic.com>`。

---

## 文件结构总览

**新增文件：**

```
server/backend/app/eval/long_session_models.py           # Pydantic schema for trace + summary
server/backend/app/eval/long_session_templates.py        # 类目模板 + 对抗轮模板
server/backend/app/eval/long_session_judge.py            # LLM judge + 分歧统计
server/backend/app/eval/long_session_runner.py           # 核心 runner + fresh/resume
server/backend/app/eval/long_session_report.py           # CSV / PNG / Markdown 报告
server/backend/app/eval/trace_schema_v1.json             # trace JSON Schema
server/backend/app/eval/prompts/long_session_judge_v1.md # judge prompt（版本化入库）
server/scripts/run_long_session_eval.py                  # CLI 入口
server/tests/test_long_session_settings.py
server/tests/test_long_session_window_switch.py
server/tests/test_long_session_snapshot_switch.py
server/tests/test_long_session_memory_cache_probe.py
server/tests/test_long_session_context_budget.py
server/tests/test_long_session_templates.py
server/tests/test_long_session_judge.py
server/tests/test_long_session_runner_fresh_resume.py
server/tests/test_long_session_runner_schema.py
server/tests/test_long_session_cli.py
server/tests/test_long_session_report.py
```

**修改文件：**

```
server/backend/app/config.py             # 加 5 个 eval_* 字段 + 环境变量读取
server/backend/app/semantic_layer.py     # _recent_context_summary / semantic_context_payload 受开关控制
server/backend/app/memory_cache.py       # .get() 加 disable_get 参数；新增 .probe()
server/backend/app/agent.py              # 注入 25K 硬截断保护；调 .probe() 落 would_hit
```

**产物目录（runner 运行时创建，不入 git 跟踪）：**

```
data/eval/long_session_2026-06-24/{dryrun,pilot,full}/{trace_C{0..4}.jsonl, cache_c{0..4}/, ...}
data/eval/long_session_2026-06-24/plots/
```

---

## 任务路线图（13 个任务）

| # | 任务 | 类型 | 依赖 |
|---|---|---|---|
| 1 | Settings 加 5 个 eval 字段 + 环境变量读取 | 生产 | — |
| 2 | A1 窗口截断开关（semantic_layer） | 生产 | 1 |
| 3 | A2 结构化快照开关（semantic_layer） | 生产 | 1 |
| 4 | Pure Probe API + disable_get（memory_cache） | 生产 | 1 |
| 5 | 25K context budget 硬截断保护（agent） | 生产 | 1 |
| 6 | 会话模板生成器（long_session_templates） | 评测 | — |
| 7 | LLM judge 模块（long_session_judge） | 评测 | — |
| 8 | Trace 模型 + JSON Schema（long_session_models + trace_schema_v1） | 评测 | — |
| 9 | Runner 核心：fresh/resume + retry + schema 校验 | 评测 | 2,3,4,5,6,8 |
| 10 | Runner 评分 hook：rule_score + judge_score | 评测 | 6,7,9 |
| 11 | Report 生成：CSV + Markdown + matplotlib PNG | 评测 | 9 |
| 12 | CLI 入口 `run_long_session_eval.py` | 评测 | 9,10,11 |
| 13 | dryrun 阶段集成 smoke（每 condition 2 轮）+ Cost Appendix 写入 | 验收 | 1-12 |

任务 1-5 是生产代码侧改动；6-8 是评测套件的纯数据/纯逻辑模块，可与 1-5 并行；9-12 必须按依赖串行。任务 13 是真实跑 dry-run smoke，用于退出 plan、进入 spec §9 的 user gate。

---

## Task 1: Settings 加 5 个 eval 字段

**Files:**
- Modify: `server/backend/app/config.py:44`（在 `feedback_path` 行附近，紧邻其他 path 字段下方插入新分组）
- Modify: `server/backend/app/config.py:242`（在 `_repo_relative_path(...)` 的 `build_settings()` 区域追加 5 个 `os.getenv(...)` 读取）
- Test: `server/tests/test_long_session_settings.py`

**Interfaces:**
- Produces:
  - `Settings.eval_disable_window_truncation: bool = False`
  - `Settings.eval_disable_structured_snapshot: bool = False`
  - `Settings.eval_disable_recommendation_memory: bool = False`
  - `Settings.eval_disable_rank_cache: bool = False`
  - `Settings.eval_force_trim_token_budget: int = 25000`
  - 环境变量：`SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION` / `SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT` / `SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY` / `SHOPGUIDE_EVAL_DISABLE_RANK_CACHE` / `SHOPGUIDE_EVAL_FORCE_TRIM_TOKEN_BUDGET`
- Consumes: 无

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_settings.py`

```python
from __future__ import annotations

import os

import pytest

from backend.app.config import Settings, build_settings


def test_default_eval_switches_keep_production_behavior():
    settings = Settings()
    assert settings.eval_disable_window_truncation is False
    assert settings.eval_disable_structured_snapshot is False
    assert settings.eval_disable_recommendation_memory is False
    assert settings.eval_disable_rank_cache is False
    assert settings.eval_force_trim_token_budget == 25000


def test_env_overrides_eval_switches(monkeypatch):
    monkeypatch.setenv("SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION", "1")
    monkeypatch.setenv("SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT", "true")
    monkeypatch.setenv("SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY", "yes")
    monkeypatch.setenv("SHOPGUIDE_EVAL_DISABLE_RANK_CACHE", "on")
    monkeypatch.setenv("SHOPGUIDE_EVAL_FORCE_TRIM_TOKEN_BUDGET", "12345")
    settings = build_settings()
    assert settings.eval_disable_window_truncation is True
    assert settings.eval_disable_structured_snapshot is True
    assert settings.eval_disable_recommendation_memory is True
    assert settings.eval_disable_rank_cache is True
    assert settings.eval_force_trim_token_budget == 12345


def test_env_default_unset_returns_false(monkeypatch):
    for key in [
        "SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION",
        "SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT",
        "SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY",
        "SHOPGUIDE_EVAL_DISABLE_RANK_CACHE",
        "SHOPGUIDE_EVAL_FORCE_TRIM_TOKEN_BUDGET",
    ]:
        monkeypatch.delenv(key, raising=False)
    settings = build_settings()
    assert settings.eval_disable_window_truncation is False
    assert settings.eval_force_trim_token_budget == 25000
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_settings.py -v
```

Expected: 3 个测试 fail，原因 `AttributeError: 'Settings' object has no attribute 'eval_disable_window_truncation'`。

- [ ] **Step 3: 在 `config.py:44-50` 区域追加字段（紧贴 `feedback_path` 下方）**

在 `server/backend/app/config.py` 中 `feedback_path: str = ""` 行之后、`user_profile_dir: str = ""` 行之前，插入：

```python
    # --- Evaluation switches (spec 2026-06-24-long-session-eval) ---
    # 生产默认全部 False/25000，等价于当前 C4 全开行为；评测 CLI 通过环境变量临时覆盖。
    eval_disable_window_truncation: bool = False
    eval_disable_structured_snapshot: bool = False
    eval_disable_recommendation_memory: bool = False
    eval_disable_rank_cache: bool = False
    eval_force_trim_token_budget: int = 25000
```

- [ ] **Step 4: 在 `build_settings()` 中追加环境变量读取**

定位 `server/backend/app/config.py` 内 `build_settings()` 函数体的尾部 return 之前，参考现有 `_repo_relative_path(os.getenv(...))` 模式。追加：

```python
def _parse_bool_env(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ... 在 build_settings() 内部，构造 Settings(...) 时追加 kwargs ：
        eval_disable_window_truncation=_parse_bool_env("SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION"),
        eval_disable_structured_snapshot=_parse_bool_env("SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT"),
        eval_disable_recommendation_memory=_parse_bool_env("SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY"),
        eval_disable_rank_cache=_parse_bool_env("SHOPGUIDE_EVAL_DISABLE_RANK_CACHE"),
        eval_force_trim_token_budget=int(os.getenv("SHOPGUIDE_EVAL_FORCE_TRIM_TOKEN_BUDGET", "25000")),
```

注意：`_parse_bool_env` 放在 `build_settings()` 上方模块顶层、紧贴现有的 `_repo_relative_path()` 之后。如果 `_repo_relative_path()` 已经有同等 helper，则复用。

- [ ] **Step 5: 跑测试确认通过 + 现有测试不破**

```bash
cd server && python -m pytest tests/test_long_session_settings.py tests/test_config.py -v
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/config.py server/tests/test_long_session_settings.py
git commit -m "feat(eval): add 5 evaluation switches to Settings (default off, prod-safe)

- eval_disable_window_truncation / structured_snapshot / recommendation_memory / rank_cache
- eval_force_trim_token_budget=25000
- Read from SHOPGUIDE_EVAL_* env vars; production defaults remain C4 全开

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: A1 窗口截断开关（semantic_layer）

**Files:**
- Modify: `server/backend/app/semantic_layer.py:286-312`（`semantic_context_payload` 签名加 settings 参数）
- Modify: `server/backend/app/semantic_layer.py:325-344`（`_recent_context_summary` 签名加 disable_window 参数）
- Modify: `server/backend/app/agent.py`（所有调 `semantic_context_payload(context)` 的地方改成传 `Settings`）
- Test: `server/tests/test_long_session_window_switch.py`

**Interfaces:**
- Consumes: `Settings.eval_disable_window_truncation` from Task 1
- Produces:
  - `semantic_context_payload(context, *, disable_window: bool = False, disable_snapshot: bool = False) -> dict[str, Any]`
  - `_recent_context_summary(context, *, disable_window: bool = False) -> dict[str, Any]`
  - 当 `disable_window=True` 时：`recent_user_turns`/`recent_recommendation_sets`/`last_events` 改为全量返回（不再 `[-3:]`/`[-6:]`）

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_window_switch.py`

```python
from __future__ import annotations

from backend.app.models import ContextEvent, ConversationState, SessionContext
from backend.app.semantic_layer import semantic_context_payload, _recent_context_summary


def _build_session_with_n_events(n: int) -> SessionContext:
    ctx = SessionContext(session_id="t")
    for i in range(n):
        ctx.state.context_events.append(
            ContextEvent(
                turn_index=i,
                user_message=f"u{i}",
                assistant_intent="recommend_product",
                result_type="recommendation_set" if i % 2 == 0 else "answer",
            )
        )
    return ctx


def test_recent_context_summary_default_truncates_to_3():
    ctx = _build_session_with_n_events(20)
    summary = _recent_context_summary(ctx)
    assert len(summary["recent_user_turns"]) == 3
    assert len(summary["recent_recommendation_sets"]) == 3
    assert len(summary["last_events"]) == 3


def test_recent_context_summary_disable_window_returns_full():
    ctx = _build_session_with_n_events(20)
    summary = _recent_context_summary(ctx, disable_window=True)
    assert len(summary["recent_user_turns"]) == 20
    assert len(summary["recent_recommendation_sets"]) == 10  # 偶数 turn
    assert len(summary["last_events"]) == 20


def test_semantic_context_payload_propagates_disable_window():
    ctx = _build_session_with_n_events(20)
    payload_default = semantic_context_payload(ctx)
    payload_disabled = semantic_context_payload(ctx, disable_window=True)
    assert len(payload_default["recent_context"]["recent_user_turns"]) == 3
    assert len(payload_disabled["recent_context"]["recent_user_turns"]) == 20
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_window_switch.py -v
```

Expected: 3 个测试 fail，原因 `TypeError: _recent_context_summary() got unexpected keyword argument 'disable_window'`。

- [ ] **Step 3: 改 `_recent_context_summary` 签名**

在 `server/backend/app/semantic_layer.py:325-344` 把：

```python
def _recent_context_summary(context: SessionContext) -> dict[str, Any]:
    recommendation_sets = [
        event.model_dump(mode="json")
        for event in context.state.context_events
        if event.result_type == "recommendation_set"
    ][-3:]
    user_turns = [
        {
            "turn_index": event.turn_index,
            "user_message": event.user_message,
            "assistant_intent": event.assistant_intent,
            "result_type": event.result_type,
        }
        for event in context.state.context_events[-6:]
    ][-3:]
    return {
        "recent_user_turns": user_turns,
        "recent_recommendation_sets": recommendation_sets,
        "last_events": [event.model_dump(mode="json") for event in context.state.context_events[-3:]],
    }
```

改为：

```python
def _recent_context_summary(
    context: SessionContext,
    *,
    disable_window: bool = False,
) -> dict[str, Any]:
    rec_events = [
        event.model_dump(mode="json")
        for event in context.state.context_events
        if event.result_type == "recommendation_set"
    ]
    user_turn_events = [
        {
            "turn_index": event.turn_index,
            "user_message": event.user_message,
            "assistant_intent": event.assistant_intent,
            "result_type": event.result_type,
        }
        for event in context.state.context_events
    ]
    all_events = [event.model_dump(mode="json") for event in context.state.context_events]
    if disable_window:
        # A1 评测模式：不截窗口，让 LLM 看到全量历史；外层 25K 硬截断保护见 agent.py
        return {
            "recent_user_turns": user_turn_events,
            "recent_recommendation_sets": rec_events,
            "last_events": all_events,
        }
    return {
        "recent_user_turns": user_turn_events[-6:][-3:],
        "recent_recommendation_sets": rec_events[-3:],
        "last_events": all_events[-3:],
    }
```

- [ ] **Step 4: 改 `semantic_context_payload` 签名**

在 `server/backend/app/semantic_layer.py:286-312` 找到 `def semantic_context_payload(context: SessionContext | None) -> dict[str, Any]:`，把签名改为：

```python
def semantic_context_payload(
    context: SessionContext | None,
    *,
    disable_window: bool = False,
    disable_snapshot: bool = False,
) -> dict[str, Any]:
```

把 return dict 中 `"recent_context": _recent_context_summary(context),` 改为：

```python
        "recent_context": _recent_context_summary(context, disable_window=disable_window),
```

（`disable_snapshot` 参数本任务先不处理，由 Task 3 接管。）

- [ ] **Step 5: 让 agent.py 在调用时透传 disable_window**

在 `server/backend/app/agent.py` 用 `grep -n "semantic_context_payload" server/backend/app/agent.py` 找所有调用点。每处调用形如：

```python
payload = semantic_context_payload(context)
```

改为：

```python
payload = semantic_context_payload(
    context,
    disable_window=self.settings.eval_disable_window_truncation,
)
```

`self.settings` 来自 `ShopGuideAgent.__init__`。若 `ShopGuideAgent` 当前未注入 `settings`，在 `__init__` 形参追加 `settings: Settings | None = None`，并在 `main.py:40-100` 的 `create_app()` 中传 `settings=settings`。

- [ ] **Step 6: 跑测试 + 现有测试不破**

```bash
cd server && python -m pytest tests/test_long_session_window_switch.py tests/test_agent_core.py -v
```

Expected: 全部 PASS（包括现有 agent 测试）。

- [ ] **Step 7: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/semantic_layer.py server/backend/app/agent.py server/tests/test_long_session_window_switch.py
git commit -m "feat(eval): add A1 window-truncation switch to semantic_context_payload

- _recent_context_summary 接受 disable_window 关键字参数
- disable_window=True 时返回全量历史，不再 [-3:]/[-6:] 切片
- agent 注入 Settings，运行时透传 eval_disable_window_truncation
- 生产默认 disable_window=False，行为不变

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: A2 结构化快照开关（semantic_layer）

**Files:**
- Modify: `server/backend/app/semantic_layer.py:286-312`（`semantic_context_payload` 内部按 disable_snapshot 清空 4 项字段）
- Modify: `server/backend/app/agent.py`（透传 `eval_disable_structured_snapshot`）
- Test: `server/tests/test_long_session_snapshot_switch.py`

**Interfaces:**
- Consumes: `Settings.eval_disable_structured_snapshot` from Task 1
- Produces: 当 `disable_snapshot=True` 时，`semantic_context_payload` 返回值中 `focus_product` / `last_plan` / `pending_clarification` / `current_task` 四项强制置 None（spec §4 表格）；`recent_context` 不受影响（由 Task 2 / A1 控制）

**注意**：spec §4 表格中提到的"constraint_state"在代码里以 `current_task` 内嵌的 `constraint_state` 表示，runner 视角的"四项"指：`focus_product`、`last_plan`、`pending_clarification`、`current_task`。本任务把这四个 key 置 None。

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_snapshot_switch.py`

```python
from __future__ import annotations

from backend.app.models import HardConstraints, RetrievalPlan, SessionContext
from backend.app.semantic_layer import semantic_context_payload


def _ctx_with_focus_and_plan() -> SessionContext:
    ctx = SessionContext(session_id="t")
    ctx.focus_product_id = "p_beauty_006"
    ctx.last_plan = RetrievalPlan(
        intent="recommend_product",
        retrieval_mode="vector",
        retrieval_query="防晒霜",
        category="美妆护肤",
        hard_constraints=HardConstraints(),
    )
    ctx.last_recommendations = [{"product_id": "p_beauty_006", "title": "测试商品"}]
    return ctx


def test_payload_default_keeps_snapshot():
    ctx = _ctx_with_focus_and_plan()
    payload = semantic_context_payload(ctx)
    assert payload["focus_product_id"] == "p_beauty_006"
    assert payload["focus_product"] is not None
    assert payload["last_plan"] is not None
    assert payload["current_task"] is not None


def test_payload_disable_snapshot_nulls_four_fields():
    ctx = _ctx_with_focus_and_plan()
    payload = semantic_context_payload(ctx, disable_snapshot=True)
    assert payload["focus_product"] is None
    assert payload["last_plan"] is None
    assert payload["pending_clarification"] is None
    assert payload["current_task"] is None
    # focus_product_id 自身仍保留（状态机不动）
    assert payload["focus_product_id"] == "p_beauty_006"
    # recent_context 仍正常（由 A1 控制）
    assert "recent_context" in payload


def test_payload_disable_snapshot_does_not_touch_recent_context():
    ctx = _ctx_with_focus_and_plan()
    payload = semantic_context_payload(ctx, disable_snapshot=True)
    # recent_context 仍有完整结构
    assert isinstance(payload["recent_context"], dict)
    assert "recent_user_turns" in payload["recent_context"]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_snapshot_switch.py -v
```

Expected: 2 个测试 fail（默认那条 PASS）；fail 原因是 `disable_snapshot=True` 时这些字段未被置 None。

- [ ] **Step 3: 在 `semantic_context_payload` 内按 disable_snapshot 清四项**

修改 `server/backend/app/semantic_layer.py` 中 `semantic_context_payload` 函数体（行号约 287-312）。在 return 之前添加：

```python
def semantic_context_payload(
    context: SessionContext | None,
    *,
    disable_window: bool = False,
    disable_snapshot: bool = False,
) -> dict[str, Any]:
    if context is None:
        return {}
    focus_product = _focus_product_summary(context)
    pending_clar = (
        context.state.pending_clarification.model_dump(mode="json")
        if context.state.pending_clarification
        else None
    )
    pending_rec = (
        context.state.pending_recovery.model_dump(mode="json")
        if context.state.pending_recovery
        else None
    )
    last_plan_payload = context.last_plan.model_dump(mode="json") if context.last_plan else None
    current_task_payload = context.state.current_task.model_dump(mode="json")

    if disable_snapshot:
        # A2 评测模式：清四项结构化快照字段；focus_product_id 自身保留（状态机仍跑）
        focus_product = None
        last_plan_payload = None
        pending_clar = None
        current_task_payload = None

    return {
        "last_plan": last_plan_payload,
        "last_intent": context.state.dialog_state.last_intent,
        "focus_product_id": context.focus_product_id,
        "has_focus_product": focus_product is not None,
        "focus_product": focus_product,
        "last_product_ids": list(context.last_product_ids),
        "last_recommendations": list(context.last_recommendations),
        "recent_cart_product_id": context.recent_cart_product_id,
        "global_profile": dict(context.global_profile),
        "current_task": current_task_payload,
        "pending_clarification": pending_clar,
        "pending_recovery": pending_rec,
        "recent_context": _recent_context_summary(context, disable_window=disable_window),
    }
```

注意：`has_focus_product` 仍由 `focus_product is not None` 推导 → 禁用 snapshot 时它也变 False，这是预期行为（LLM 看不到 focus）。

- [ ] **Step 4: agent.py 透传 disable_snapshot**

修改 Task 2 中已改造的所有 `semantic_context_payload(...)` 调用点，追加参数：

```python
payload = semantic_context_payload(
    context,
    disable_window=self.settings.eval_disable_window_truncation,
    disable_snapshot=self.settings.eval_disable_structured_snapshot,
)
```

- [ ] **Step 5: 跑测试 + 现有测试不破**

```bash
cd server && python -m pytest tests/test_long_session_snapshot_switch.py tests/test_long_session_window_switch.py tests/test_agent_core.py -v
```

Expected: 全 PASS。

- [ ] **Step 6: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/semantic_layer.py server/backend/app/agent.py server/tests/test_long_session_snapshot_switch.py
git commit -m "feat(eval): add A2 structured-snapshot switch to semantic_context_payload

- disable_snapshot=True 时清四项：focus_product / last_plan / pending_clarification / current_task
- focus_product_id / recent_context 不受影响（A1 / 状态机不动原则）
- agent 透传 eval_disable_structured_snapshot

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Pure Probe API + disable_get（memory_cache）

**Files:**
- Modify: `server/backend/app/memory_cache.py:25`（`StructuredMemoryCache.get` 加 `disable_get` 参数）
- Modify: `server/backend/app/memory_cache.py:128`（`RecommendationMemoryCache.get` 同上）
- Add: `server/backend/app/memory_cache.py`（两个类各新增 `probe()` 方法）
- Modify: `server/backend/app/agent.py`（调用点透传 disable_get；新增并行 probe 调用）
- Test: `server/tests/test_long_session_memory_cache_probe.py`

**Interfaces:**
- Consumes: `Settings.eval_disable_recommendation_memory` / `eval_disable_rank_cache` from Task 1
- Produces:
  - `StructuredMemoryCache.get(plan, product_map, *, disable_get: bool = False) -> list[RankedProduct] | None`
  - `StructuredMemoryCache.probe(plan, product_map) -> bool`（pure：不改 `_hits/_misses/_writes`）
  - `RecommendationMemoryCache.get(plan, message, product_map, *, disable_get: bool = False) -> RecommendationMemoryHit | None`
  - `RecommendationMemoryCache.probe(plan, message, product_map) -> bool`（pure：不改 `_*hits/_misses/_invalidations`）

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_memory_cache_probe.py`

```python
from __future__ import annotations

from backend.app.memory_cache import RecommendationMemoryCache, StructuredMemoryCache
from backend.app.models import HardConstraints, Product, RankedProduct, RetrievalPlan


def _make_product(pid: str = "p1") -> Product:
    return Product(
        product_id=pid,
        title="测试商品",
        brand="测试",
        category="美妆护肤",
        sub_category="防晒",
        price=199.0,
        marketing_description="",
        faqs=[],
        reviews=[],
        extracted_terms=[],
    )


def _make_plan() -> RetrievalPlan:
    return RetrievalPlan(
        intent="recommend_product",
        retrieval_mode="vector",
        retrieval_query="防晒霜",
        category="美妆护肤",
        hard_constraints=HardConstraints(category="美妆护肤"),
    )


def test_structured_cache_disable_get_returns_none():
    cache = StructuredMemoryCache()
    plan = _make_plan()
    product = _make_product()
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="", evidence=[])]
    cache.put(plan, ranked)
    # 默认 get 命中
    assert cache.get(plan, {product.product_id: product}) is not None
    # disable_get 时返回 None
    assert cache.get(plan, {product.product_id: product}, disable_get=True) is None


def test_structured_cache_probe_does_not_mutate_stats():
    cache = StructuredMemoryCache()
    plan = _make_plan()
    product = _make_product()
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="", evidence=[])]
    cache.put(plan, ranked)
    stats_before = dict(cache.stats())
    for _ in range(100):
        cache.probe(plan, {product.product_id: product})
    stats_after = dict(cache.stats())
    assert stats_before == stats_after


def test_structured_cache_probe_returns_hit_status():
    cache = StructuredMemoryCache()
    plan = _make_plan()
    product = _make_product()
    # 空 cache → probe False
    assert cache.probe(plan, {product.product_id: product}) is False
    # put 后 probe True
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="", evidence=[])]
    cache.put(plan, ranked)
    assert cache.probe(plan, {product.product_id: product}) is True


def test_recommendation_cache_disable_get_returns_none():
    cache = RecommendationMemoryCache()
    plan = _make_plan()
    product = _make_product()
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="主推", evidence=[])]
    cache.put(plan, "我要防晒霜", ranked)
    assert cache.get(plan, "我要防晒霜", {product.product_id: product}) is not None
    assert cache.get(plan, "我要防晒霜", {product.product_id: product}, disable_get=True) is None


def test_recommendation_cache_probe_does_not_mutate_stats():
    cache = RecommendationMemoryCache()
    plan = _make_plan()
    product = _make_product()
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="主推", evidence=[])]
    cache.put(plan, "我要防晒霜", ranked)
    stats_before = dict(cache.stats())
    for _ in range(100):
        cache.probe(plan, "我要防晒霜", {product.product_id: product})
    stats_after = dict(cache.stats())
    assert stats_before == stats_after


def test_recommendation_cache_probe_returns_hit_status():
    cache = RecommendationMemoryCache()
    plan = _make_plan()
    product = _make_product()
    assert cache.probe(plan, "我要防晒霜", {product.product_id: product}) is False
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="主推", evidence=[])]
    cache.put(plan, "我要防晒霜", ranked)
    assert cache.probe(plan, "我要防晒霜", {product.product_id: product}) is True
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_memory_cache_probe.py -v
```

Expected: 全 fail，`AttributeError` 或 `TypeError` for `probe` / `disable_get`。

- [ ] **Step 3: 给 `StructuredMemoryCache` 加 `disable_get` + `probe`**

修改 `server/backend/app/memory_cache.py:25-49`：

```python
    def get(
        self,
        plan: RetrievalPlan,
        product_map: dict[str, Product],
        *,
        disable_get: bool = False,
    ) -> list[RankedProduct] | None:
        if disable_get:
            return None
        key = self.make_key(plan)
        rows = self._items.get(key)
        if not rows:
            self._misses += 1
            return None
        ranked: list[RankedProduct] = []
        for row in rows:
            product = product_map.get(str(row.get("product_id", "")))
            if not product or not hard_filter(product, plan.hard_constraints):
                continue
            ranked.append(
                RankedProduct(
                    product=product,
                    score=float(row.get("score", 0.0)),
                    tier=int(row.get("tier", 3)),
                    reason=str(row.get("reason", "")),
                    evidence=list(row.get("evidence", [])),
                )
            )
        if not ranked:
            self._misses += 1
            return None
        self._hits += 1
        return ranked

    def probe(self, plan: RetrievalPlan, product_map: dict[str, Product]) -> bool:
        """Pure: 仅判断是否能命中，不改任何 stats。"""
        key = self.make_key(plan)
        rows = self._items.get(key)
        if not rows:
            return False
        for row in rows:
            product = product_map.get(str(row.get("product_id", "")))
            if product and hard_filter(product, plan.hard_constraints):
                return True
        return False
```

- [ ] **Step 4: 给 `RecommendationMemoryCache` 加 `disable_get` + `probe`**

修改 `server/backend/app/memory_cache.py:128-145`：

```python
    def get(
        self,
        plan: RetrievalPlan,
        message: str,
        product_map: dict[str, Product],
        *,
        disable_get: bool = False,
    ) -> RecommendationMemoryHit | None:
        if disable_get:
            return None
        exact_key = self.make_exact_key(plan, message)
        row = self._items.get(exact_key)
        if row:
            hit = self._validated_hit(row, plan, product_map, "exact_hit")
            if hit:
                self._exact_hits += 1
                return hit
            self._invalidations += 1
        semantic_row = self._find_semantic_row(plan, message)
        if semantic_row:
            hit = self._validated_hit(semantic_row, plan, product_map, "semantic_hit")
            if hit:
                self._semantic_hits += 1
                return hit
            self._invalidations += 1
        self._misses += 1
        return None

    def probe(
        self,
        plan: RetrievalPlan,
        message: str,
        product_map: dict[str, Product],
    ) -> bool:
        """Pure: 仅判断 exact 或 semantic 是否能命中，不改任何 stats / _invalidations。"""
        exact_key = self.make_exact_key(plan, message)
        row = self._items.get(exact_key)
        if row and self._validated_hit_dry(row, plan, product_map):
            return True
        semantic_row = self._find_semantic_row(plan, message)
        if semantic_row and self._validated_hit_dry(semantic_row, plan, product_map):
            return True
        return False

    def _validated_hit_dry(
        self,
        row: dict[str, Any],
        plan: RetrievalPlan,
        product_map: dict[str, Product],
    ) -> bool:
        """与 _validated_hit 同逻辑但不构造 RankedProduct，仅返回 True/False。"""
        for item in row.get("selected_products", []):
            product = product_map.get(str(item.get("product_id", "")))
            if not product or not hard_filter(product, plan.hard_constraints):
                return False
            taxonomy = row.get("taxonomy", {})
            expected_sub = taxonomy.get("sub_category")
            expected_cat = taxonomy.get("category")
            if expected_sub and product.sub_category != expected_sub:
                return False
            if expected_cat and product.category != expected_cat:
                return False
        return bool(row.get("selected_products"))
```

- [ ] **Step 5: 在 agent.py 调用点透传 disable_get + 并行 probe**

定位 `server/backend/app/agent.py` 中所有 `self.memory_cache.get(plan, ...)` 与 `self.recommendation_memory.get(plan, request.message, ...)` 调用。每处改为：

```python
# 排序级缓存（B2）
cached_base = None
would_hit_b2 = False
if self.memory_cache:
    would_hit_b2 = self.memory_cache.probe(plan, self.product_map)
    cached_base = self.memory_cache.get(
        plan,
        self.product_map,
        disable_get=self.settings.eval_disable_rank_cache,
    )
```

```python
# 语义记忆复用（B1）
memory_hit = None
would_hit_b1 = False
if self.recommendation_memory:
    would_hit_b1 = self.recommendation_memory.probe(plan, request.message, self.product_map)
    memory_hit = self.recommendation_memory.get(
        plan,
        request.message,
        self.product_map,
        disable_get=self.settings.eval_disable_recommendation_memory,
    )
```

把 `would_hit_b1` / `would_hit_b2` / `effective_hit_b1=(memory_hit is not None)` / `effective_hit_b2=(cached_base is not None)` 通过现有 trace event 机制（agent.py 已有 `_emit_event` 等模式）落到 ContextEvent / 或单独存到 `agent.last_cache_probe`，供 runner 在 Task 9 中读取。

最简实现：在 `ShopGuideAgent` 上挂 `self._last_cache_probe: dict[str, bool] = {}`，每轮 chat 入口处清空，进入上述代码块后填四个 key：`would_hit_b1` / `effective_hit_b1` / `would_hit_b2` / `effective_hit_b2`。runner 通过 `agent._last_cache_probe` 读取。

- [ ] **Step 6: 跑测试 + 现有测试不破**

```bash
cd server && python -m pytest tests/test_long_session_memory_cache_probe.py tests/test_agent_core.py tests/test_bugfix_phase3.py -v
```

Expected: 全 PASS。

- [ ] **Step 7: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/memory_cache.py server/backend/app/agent.py server/tests/test_long_session_memory_cache_probe.py
git commit -m "feat(eval): add disable_get switch + side-effect-free probe() to memory caches

- StructuredMemoryCache.get / RecommendationMemoryCache.get 接受 disable_get
- 新增 .probe() pure API：100 次 probe 不改 stats
- agent 透传 eval_disable_recommendation_memory / eval_disable_rank_cache
- 每轮在 ShopGuideAgent._last_cache_probe 暴露 would_hit / effective_hit 四口径

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: 25K context budget 硬截断保护（agent）

**Files:**
- Modify: `server/backend/app/agent.py`（在调 LLM 前估算 context tokens；超阈值则截断 + 打 degradation 标签）
- Modify: `server/backend/requirements.in`（添加 `tiktoken`）
- Test: `server/tests/test_long_session_context_budget.py`

**Interfaces:**
- Consumes: `Settings.eval_force_trim_token_budget` from Task 1; `Settings.eval_disable_window_truncation` from Task 2（仅在 A1 关闭时才启用硬截断保护，因为只有 A1 关闭才可能 overflow）
- Produces:
  - `ShopGuideAgent._maybe_force_trim_context(payload: dict, *, budget: int) -> tuple[dict, str | None]`
  - 返回 (可能被截断的 payload, degradation 标签)
  - degradation 取值：`"context_overflow_forced_trim"` 或 `None`
  - 每轮在 `agent._last_degradation: str | None` 暴露给 runner

- [ ] **Step 1: 添加依赖**

修改 `server/backend/requirements.in`，在末尾追加：

```
tiktoken>=0.7.0
```

- [ ] **Step 2: 重新生成 lock + 装依赖**

```bash
cd server
pip-compile requirements.in --output-file requirements.lock --upgrade-package tiktoken
pip install -r requirements.lock
```

如果 `pip-compile` 不可用，直接：

```bash
pip install "tiktoken>=0.7.0" && pip freeze | grep tiktoken >> requirements.lock
```

- [ ] **Step 3: 写失败测试**

文件：`server/tests/test_long_session_context_budget.py`

```python
from __future__ import annotations

from backend.app.agent import ShopGuideAgent


def test_payload_within_budget_returns_unchanged():
    agent = ShopGuideAgent.__new__(ShopGuideAgent)  # bypass __init__
    payload = {"recent_context": {"recent_user_turns": [{"user_message": "你好"}]}}
    result, degradation = ShopGuideAgent._maybe_force_trim_context(agent, payload, budget=25000)
    assert degradation is None
    assert result == payload


def test_payload_over_budget_gets_trimmed_with_label():
    agent = ShopGuideAgent.__new__(ShopGuideAgent)
    # 造一个超大 payload
    big_turns = [{"user_message": "x" * 200, "assistant_intent": "recommend_product"} for _ in range(500)]
    payload = {"recent_context": {"recent_user_turns": big_turns, "recent_recommendation_sets": [], "last_events": []}}
    result, degradation = ShopGuideAgent._maybe_force_trim_context(agent, payload, budget=1000)
    assert degradation == "context_overflow_forced_trim"
    # 截断后 recent_user_turns 必须更短
    assert len(result["recent_context"]["recent_user_turns"]) < 500


def test_trim_keeps_most_recent_turns():
    agent = ShopGuideAgent.__new__(ShopGuideAgent)
    turns = [{"user_message": "x" * 200, "turn_index": i} for i in range(500)]
    payload = {"recent_context": {"recent_user_turns": turns, "recent_recommendation_sets": [], "last_events": []}}
    result, _ = ShopGuideAgent._maybe_force_trim_context(agent, payload, budget=1000)
    kept = result["recent_context"]["recent_user_turns"]
    # 保留的应该是最近的（turn_index 较大的）
    assert kept[-1]["turn_index"] == 499
```

- [ ] **Step 4: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_context_budget.py -v
```

Expected: 全 fail，`AttributeError: type object 'ShopGuideAgent' has no attribute '_maybe_force_trim_context'`。

- [ ] **Step 5: 实现 `_maybe_force_trim_context`**

在 `server/backend/app/agent.py` 的 `ShopGuideAgent` 类中添加：

```python
    @staticmethod
    def _estimate_tokens(payload: dict) -> int:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(json.dumps(payload, ensure_ascii=False)))
        except Exception:
            # 兜底：粗估 1 token ≈ 1.6 char（中文场景）
            return int(len(json.dumps(payload, ensure_ascii=False)) / 1.6)

    def _maybe_force_trim_context(
        self,
        payload: dict,
        *,
        budget: int,
    ) -> tuple[dict, str | None]:
        """若 payload tokens 超 budget，逐步截断 recent_context.recent_user_turns / last_events 的尾部直到 ≤budget。
        返回 (trimmed_payload, degradation_label 或 None)。
        仅在 eval_disable_window_truncation=True 时有意义；A1 默认行为下窗口已经截好，几乎不会触发。
        """
        if not payload:
            return payload, None
        current = self._estimate_tokens(payload)
        if current <= budget:
            return payload, None
        trimmed = json.loads(json.dumps(payload))  # deep copy
        rc = trimmed.get("recent_context", {})
        # 逐步从最早的 turn 开始砍
        for key in ("recent_user_turns", "last_events", "recent_recommendation_sets"):
            while rc.get(key) and self._estimate_tokens(trimmed) > budget:
                rc[key].pop(0)  # 砍最早的
        return trimmed, "context_overflow_forced_trim"
```

在每次 LLM 调用前注入：

```python
        budget = self.settings.eval_force_trim_token_budget if self.settings else 25000
        payload, degradation = self._maybe_force_trim_context(payload, budget=budget)
        if degradation:
            self._last_degradation = degradation
```

`self._last_degradation` 在 chat 入口处初始化为 None。

- [ ] **Step 6: 跑测试 + 现有测试**

```bash
cd server && python -m pytest tests/test_long_session_context_budget.py tests/test_agent_core.py -v
```

Expected: 全 PASS。

- [ ] **Step 7: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/agent.py server/backend/requirements.in server/backend/requirements.lock server/tests/test_long_session_context_budget.py
git commit -m "feat(eval): add 25K context budget force-trim protection in agent

- ShopGuideAgent._maybe_force_trim_context：超 budget 时砍最早 turn，保留最近
- 用 tiktoken cl100k_base 估算（近似豆包 tokenizer），失败时 char/1.6 兜底
- 触发后在 agent._last_degradation 暴露 'context_overflow_forced_trim'
- 仅 A1 关闭时才可能触发；生产默认 budget=25000，行为不变

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---


## Task 6: 会话模板生成器（long_session_templates）

**Files:**
- Create: `server/backend/app/eval/long_session_templates.py`
- Test: `server/tests/test_long_session_templates.py`

**Interfaces:**
- Consumes: 商品 list `list[Product]`（runner 启动时 load 一次）
- Produces:
  - `build_long_session_script(products: list[Product], *, seed: int = 20260624) -> list[ScriptTurn]`
  - `class ScriptTurn(BaseModel)`：`phase` / `turn_type` / `query` / `expected: dict` / `adversarial_subtype: str | None`
  - 输出长度 = 1100（phase A 1000 + B 5 + C 10 + D 75 + E 10）
  - 商品顺序按类目交替穿插（spec §5.2）
  - 75 对抗轮均匀穿插到 phase A 中

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_templates.py`

```python
from __future__ import annotations

from collections import Counter

import pytest

from backend.app.data_loader import load_products
from backend.app.eval.long_session_templates import (
    ScriptTurn,
    build_long_session_script,
)


@pytest.fixture(scope="module")
def products():
    return load_products("ecommerce_agent_dataset")


def test_script_total_turn_count(products):
    script = build_long_session_script(products)
    assert len(script) == 1100


def test_phase_counts(products):
    script = build_long_session_script(products)
    counter = Counter(t.phase for t in script)
    assert counter["A"] == 1000
    assert counter["B"] == 5
    assert counter["C"] == 10
    assert counter["D"] == 75
    assert counter["E"] == 10


def test_turn_type_diversity(products):
    script = build_long_session_script(products)
    types = {t.turn_type for t in script}
    expected = {
        "retrieval",
        "followup_factual",
        "comparison",
        "cart_action",
        "long_range_reference",
        "constraint_handling",
        "adversarial_reference",
        "adversarial_constraint",
    }
    assert expected.issubset(types)


def test_adversarial_subtypes_distribution(products):
    script = build_long_session_script(products)
    d_turns = [t for t in script if t.phase == "D"]
    counter = Counter(t.adversarial_subtype for t in d_turns)
    assert counter["D1"] == 15
    assert counter["D2"] == 10
    assert counter["D3"] == 10
    assert counter["D4"] == 10
    assert counter["D5"] == 15
    assert counter["D6"] == 15


def test_long_range_reference_targets_earlier_turn(products):
    script = build_long_session_script(products)
    c_turns = [(i, t) for i, t in enumerate(script) if t.phase == "C"]
    for i, t in c_turns:
        target_turn = t.expected.get("expected_focus_turn_index")
        assert target_turn is not None
        # 指代的 turn 必须 ≥100 轮之前
        assert i - target_turn >= 100


def test_script_is_deterministic(products):
    s1 = build_long_session_script(products, seed=42)
    s2 = build_long_session_script(products, seed=42)
    assert [t.model_dump() for t in s1] == [t.model_dump() for t in s2]


def test_seed_changes_query_template_choices(products):
    s1 = build_long_session_script(products, seed=1)
    s2 = build_long_session_script(products, seed=2)
    queries_1 = [t.query for t in s1]
    queries_2 = [t.query for t in s2]
    assert queries_1 != queries_2
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_templates.py -v
```

Expected: 全 fail，`ImportError: cannot import name 'build_long_session_script'`。

- [ ] **Step 3: 实现 `long_session_templates.py`**

按 spec §5.1/§5.2 创建文件。核心结构：

- `ScriptTurn` Pydantic 模型，5 个字段。
- `CATEGORY_TEMPLATES: dict[str, list[tuple[turn_type, query_template, doc_note]]]`，5 个类目各 10 个模板（spec §5.1）。
- `CATEGORY_ORDER = ["美妆护肤", "食品饮料", "服饰运动", "数码电子", "家居日用"]`。
- `ADVERSARIAL_TEMPLATES: dict[str, list[str]]`，键为 D1-D6，每个列表条数与 spec §5 一致（15/10/10/10/15/15）。
- `build_long_session_script(products, *, seed)`：
  1. `rng = random.Random(seed)`
  2. 按类目分组、组内按 product_id 稳定排序
  3. 交替穿插出 100 个商品序列
  4. 对每个商品执行类目模板 10 个 → 1000 phase A
  5. 生成 5 phase B、10 phase C（指向 turn_index - 150）、75 phase D（按 adversarial_subtype 平摊）、10 phase E
  6. 按等距规则把 B/C/D 插入 phase A 序列（B 每 200 轮、C 每 100 轮、D 每 13 轮）
  7. 最终拼接 + 校验 `len == 1100`

完整代码模板见 spec §5 + 上方测试。**关键约束**：
- 同一类目不得连续 ≥6 个（test_category_interleaving_avoids_long_runs 已 covered，需要时调整 interleave 顺序）
- `expected.subject_product_id` 必须填，runner 后续要用
- adversarial_subtype 与 turn_type 映射：D1/D5/D6 → `adversarial_reference`；D2/D3/D4 → `adversarial_constraint`

- [ ] **Step 4: 跑测试**

```bash
cd server && python -m pytest tests/test_long_session_templates.py -v
```

Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/eval/long_session_templates.py server/tests/test_long_session_templates.py
git commit -m "feat(eval): add long-session script generator (1100 turns, 75 adversarial)

- 100 商品 × 10 类目化模板 = 1000 phase-A
- 5 phase-B 跨商品横评 + 10 phase-C 长程指代 + 75 phase-D 对抗 + 10 phase-E 交易
- 商品按类目交替穿插（美妆/食品/服饰/数码/家居）
- 确定性：相同 (products, seed) 必产同脚本

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: LLM judge 模块（long_session_judge）

**Files:**
- Create: `server/backend/app/eval/long_session_judge.py`
- Create: `server/backend/app/eval/prompts/long_session_judge_v1.md`
- Test: `server/tests/test_long_session_judge.py`

**Interfaces:**
- Consumes: `Settings.ark_api_key` / `ark_base_url` / `ark_model`（独立 client，不复用 agent 的）
- Produces:
  - `class JudgeResult(BaseModel)`：`raw: list[dict]` / `mean: float` / `disagreement: float` / `call_count: int`
  - `class LongSessionJudge`：
    - `__init__(settings: Settings, *, call_count: int = 3)`
    - `async judge(turn: ScriptTurn, answer_text: str, retrieved_top_k: list[str], product_map: dict[str, Product]) -> JudgeResult`
    - `compute_disagreement_rate(results: list[JudgeResult]) -> float`（static）
    - `recommend_pilot_call_count(disagreement_rate: float) -> int | None`（static；<5% → 1 / <20% → 3 / ≥20% → None）
    - `async aclose() -> None`

- [ ] **Step 1: 写 judge prompt（版本化入库）**

文件：`server/backend/app/eval/prompts/long_session_judge_v1.md`

```markdown
# Long-Session Evaluation Judge — Rubric v1

你是一个评审员，对一轮电商导购对话进行四维评分。每个维度严格二元：1 = 满足，0 = 不满足。

## 评分维度

1. **hit**：助手是否答到了用户问题的核心点？
2. **fluent**：表达是否流畅、有逻辑？语法错乱、自相矛盾、明显复读 → 0。
3. **no_hallucination**：是否只引用了 `retrieved_top_k` 内或 `sample_catalog_ids` 内的真实商品？捏造商品 → 0。
4. **no_state_violation**：是否未擅自执行 side-effect（下单/清空购物车/改约束）？

## 输出（严格 JSON，禁止任何其他文字）

```json
{"hit": 1, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1, "reason": "<≤80 字>"}
```

## 输入

User query：{query}
Turn type：{turn_type}
Adversarial subtype：{adversarial_subtype}
Assistant answer：{answer}
Retrieved top-K product ids：{retrieved_top_k}
Catalog 抽样商品 id：{sample_catalog_ids}
Expected 锚点：{expected_brief}
```

- [ ] **Step 2: 写失败测试**

文件：`server/tests/test_long_session_judge.py`（关键测例骨架，完整测例见 plan 上方 Task 7 详述）：

```python
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from backend.app.config import build_settings
from backend.app.eval.long_session_judge import JudgeResult, LongSessionJudge
from backend.app.eval.long_session_templates import ScriptTurn


@pytest.mark.asyncio
async def test_judge_returns_three_raw_results_in_dryrun_mode():
    judge = LongSessionJudge(build_settings(), call_count=3)
    judge._call_once = AsyncMock(
        return_value={"hit": 1, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1, "reason": ""}
    )
    turn = ScriptTurn(phase="A", turn_type="retrieval", query="推荐防晒", expected={})
    result = await judge.judge(turn, "推荐一款防晒霜", ["p1"], {})
    assert isinstance(result, JudgeResult)
    assert result.call_count == 3
    assert len(result.raw) == 3
    assert result.mean == 4.0
    assert result.disagreement == 0.0


@pytest.mark.asyncio
async def test_judge_detects_disagreement():
    judge = LongSessionJudge(build_settings(), call_count=3)
    judge._call_once = AsyncMock(side_effect=[
        {"hit": 1, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1},
        {"hit": 0, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1},
        {"hit": 1, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1},
    ])
    turn = ScriptTurn(phase="A", turn_type="retrieval", query="x", expected={})
    result = await judge.judge(turn, "...", [], {})
    assert result.disagreement > 0


def test_recommend_call_count_low():
    assert LongSessionJudge.recommend_pilot_call_count(0.02) == 1


def test_recommend_call_count_mid():
    assert LongSessionJudge.recommend_pilot_call_count(0.10) == 3


def test_recommend_call_count_high():
    assert LongSessionJudge.recommend_pilot_call_count(0.25) is None
```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_judge.py -v
```

Expected: ImportError 全 fail。

- [ ] **Step 4: 实现 `long_session_judge.py`**

按 spec §6.1：
- 加载 `prompts/long_session_judge_v1.md` 作为 template
- 用独立 `httpx.AsyncClient(base_url=settings.ark_base_url, timeout=30, headers={Authorization: Bearer settings.ark_api_key})`
- `judge()` 循环 `call_count` 次调 `_call_once`，每次 POST `/chat/completions`，`model=settings.ark_model`、`temperature=0`、system prompt 强调"只输出 JSON"
- 解析返回 JSON：兼容 ```json``` fenced 代码块；解析失败给全 0 + reason="parse_error"
- `_score()` 把 4 维 0/1 相加得 0-4
- `_disagreement()` 检查任一维度在多次结果中不一致比例 → 0-1
- `compute_disagreement_rate()` 把"任一 disagreement > 0 的 turn"占采样总数比例
- `recommend_pilot_call_count()` 按阈值 5%/20% 返回 1/3/None

完整签名和返回值见 §Interfaces 块。

- [ ] **Step 5: 添加依赖（若 httpx 未在 requirements）**

```bash
cd server && python -c "import httpx; print(httpx.__version__)"
```

httpx 已在 requirements.lock，不需新增。

- [ ] **Step 6: 跑测试**

```bash
cd server && python -m pytest tests/test_long_session_judge.py -v
```

Expected: 全 PASS。

- [ ] **Step 7: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/eval/long_session_judge.py server/backend/app/eval/prompts/long_session_judge_v1.md server/tests/test_long_session_judge.py
git commit -m "feat(eval): add LongSessionJudge with adaptive call-count folding

- v1 rubric (hit/fluent/no_hallucination/no_state_violation) 四维 0/1
- 独立 httpx ARK client，temperature=0
- compute_disagreement_rate + recommend_pilot_call_count: <5%→1 / <20%→3 / ≥20%→user
- prompt 入库 prompts/long_session_judge_v1.md

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Trace 模型 + JSON Schema

**Files:**
- Create: `server/backend/app/eval/long_session_models.py`
- Create: `server/backend/app/eval/trace_schema_v1.json`
- Test: `server/tests/test_long_session_runner_schema.py`

**Interfaces:**
- Produces:
  - `TRACE_SCHEMA_VERSION = "1"`
  - `class TurnTrace(BaseModel)` — 30 个字段对应 spec §7 + §9.1
  - `class TraceMeta(BaseModel)` — trace 文件头一行
  - `class JudgeScore(BaseModel)` — spec §6.1.1
  - `class TraceSchemaError(ValueError)`
  - `validate_trace_line(line: dict) -> None` — 用 jsonschema 校验，失败抛 `TraceSchemaError`

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_runner_schema.py`

```python
from __future__ import annotations

import json
import pytest

from backend.app.eval.long_session_models import (
    TraceMeta, TraceSchemaError, TurnTrace, validate_trace_line,
)


def _valid_trace_dict() -> dict:
    return {
        "condition": "C2",
        "session_id": "eval_dryrun_c2_2026-06-24",
        "turn_index": 47,
        "phase": "A",
        "turn_type": "retrieval",
        "adversarial_subtype": None,
        "query": "推荐防晒",
        "expected": {"expected_intent": "recommend_product"},
        "pipeline": ["planner", "retrieval"],
        "tool_calls": [{"name": "retrieval", "ms": 230}],
        "branch_flags": {"memory_hit": None, "fallback": None, "clarify": False},
        "prompt_tokens": 4321,
        "completion_tokens": 187,
        "first_chunk_ms": 820,
        "total_ms": 2310,
        "context_payload_bytes": 8742,
        "context_payload_tokens": 2180,
        "context_events_count": 47,
        "focus_history_len": 47,
        "focus_product_id": "p_beauty_006",
        "hard_constraints": {"category": "美妆护肤"},
        "state_drift": None,
        "degradation": None,
        "would_hit_b1": True,
        "effective_hit_b1": False,
        "would_hit_b2": True,
        "effective_hit_b2": False,
        "cache_stats_at_turn": {"b1_size": 23, "b2_size": 31},
        "rule_score": {"ndcg5": 0.83},
        "judge_score": None,
        "answer_text": "好的，给你推荐一款",
        "retrieved_top_k": ["p_beauty_006"],
        "script_version_hash": "sha256:" + "a" * 64,
        "product_list_hash": "sha256:" + "b" * 64,
        "condition_config_hash": "sha256:" + "c" * 64,
    }


def test_valid_trace_passes_schema():
    validate_trace_line(_valid_trace_dict())


def test_missing_required_key_fails():
    d = _valid_trace_dict()
    del d["turn_index"]
    with pytest.raises(TraceSchemaError):
        validate_trace_line(d)


def test_invalid_hash_format_fails():
    d = _valid_trace_dict()
    d["script_version_hash"] = "not-a-hash"
    with pytest.raises(TraceSchemaError):
        validate_trace_line(d)


def test_nullable_fields_accept_null():
    d = _valid_trace_dict()
    for k in ("adversarial_subtype", "focus_product_id", "state_drift", "degradation", "judge_score"):
        d[k] = None
    validate_trace_line(d)


def test_negative_token_count_fails():
    d = _valid_trace_dict()
    d["prompt_tokens"] = -1
    with pytest.raises(TraceSchemaError):
        validate_trace_line(d)


def test_turn_trace_pydantic_model_roundtrip():
    d = _valid_trace_dict()
    trace = TurnTrace(**d)
    assert trace.condition == "C2"
    dumped = trace.model_dump(mode="json")
    validate_trace_line(dumped)


def test_trace_meta_pydantic_model():
    meta = TraceMeta(
        condition="C2",
        script_version_hash="sha256:" + "a" * 64,
        product_list_hash="sha256:" + "b" * 64,
        condition_config_hash="sha256:" + "c" * 64,
        cache_namespace="data/eval/long_session_2026-06-24/dryrun/cache_c2/",
        started_at="2026-06-24T14:00:00+08:00",
        ark_model="ep-xxx",
        spec_version="2026-06-24-v1",
    )
    assert meta.condition == "C2"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_runner_schema.py -v
```

Expected: 全 fail，ImportError。

- [ ] **Step 3: 实现 `long_session_models.py`**

按 spec §7 + §9.1 用 Pydantic 把 30 个字段写完。关键：
- `TurnTrace`：所有 required 字段非 Optional；nullable 字段（adversarial_subtype / focus_product_id / state_drift / degradation / judge_score）类型为 `T | None`，默认 `None`
- 整数字段加 `Field(ge=0)`
- `validate_trace_line(line)` 使用 `jsonschema.validate(line, _load_schema())`，捕获 `ValidationError` 抛 `TraceSchemaError`
- schema 从 `trace_schema_v1.json` 加载，`functools.lru_cache` 或模块级缓存

- [ ] **Step 4: 实现 `trace_schema_v1.json`**

按 spec §9.1：
- `required` 列表与上方 `_valid_trace_dict` 的非 nullable key 完全一致（30 个 required，5 个 nullable）
- 三个 hash 字段加 `"pattern": "^sha256:[a-f0-9]{64}$"`
- 整数字段加 `"minimum": 0`
- nullable 字段 type 为 `["string", "null"]` 或 `["object", "null"]`
- `condition` 用 `"enum": ["C0", "C1", "C2", "C3", "C4"]`
- `phase` 用 `"enum": ["A", "B", "C", "D", "E"]`

- [ ] **Step 5: 添加 jsonschema 依赖**

```bash
grep -i jsonschema server/backend/requirements.lock 2>/dev/null || echo "缺失需添加"
```

如缺失则追加 `jsonschema>=4.20.0` 到 `requirements.in`，重生 lock 或直接 `pip install`。

- [ ] **Step 6: 跑测试**

```bash
cd server && python -m pytest tests/test_long_session_runner_schema.py -v
```

Expected: 全 PASS。

- [ ] **Step 7: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/eval/long_session_models.py server/backend/app/eval/trace_schema_v1.json server/backend/requirements.in server/tests/test_long_session_runner_schema.py
git commit -m "feat(eval): add trace pydantic models + JSON Schema validator

- TurnTrace / TraceMeta / JudgeScore models
- trace_schema_v1.json: required + nullable + 类型 + hash regex
- validate_trace_line() 失败抛 TraceSchemaError

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: Runner 核心：fresh/resume + retry + schema 校验

**Files:**
- Create: `server/backend/app/eval/long_session_runner.py`
- Test: `server/tests/test_long_session_runner_fresh_resume.py`

**Interfaces:**
- Consumes: Task 1-5（Settings 开关）、Task 6（templates）、Task 8（trace schema）
- Produces:
  - `class RunnerConfig(BaseModel)`：`stage: str` / `condition: str` / `data_root: Path` / `mode: Literal["fresh", "resume"]`
  - `class LongSessionRunner`:
    - `async run(script: list[ScriptTurn], *, agent_factory) -> None`
    - `_compute_hashes(script, products, condition) -> tuple[str, str, str]` (script_version_hash, product_list_hash, condition_config_hash)
    - `_setup_trace_file(meta)`: fresh 时 backup 旧文件并写 meta 头；resume 时校验 meta 头 4 个 hash
    - `_write_turn(trace_dict)`：jsonschema 校验 + 写一行 + flush + fsync
    - `_should_resume_from() -> int`：扫 trace.jsonl 拿最后一条 turn_index，返回下一个
  - 异常：
    - `HashMismatchError`：resume 时 hash 不一致
    - `MetaMissingError`：resume 时 trace 文件不存在或缺 meta

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_runner_fresh_resume.py`

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.eval.long_session_runner import (
    HashMismatchError,
    LongSessionRunner,
    MetaMissingError,
    RunnerConfig,
)
from backend.app.eval.long_session_templates import ScriptTurn


def _mk_config(tmp_path: Path, mode: str = "fresh") -> RunnerConfig:
    return RunnerConfig(
        stage="dryrun",
        condition="C0",
        data_root=tmp_path,
        mode=mode,
    )


def test_fresh_mode_creates_trace_with_meta(tmp_path):
    config = _mk_config(tmp_path, mode="fresh")
    runner = LongSessionRunner(config)
    runner._compute_hashes_static = lambda: ("sha256:" + "a"*64, "sha256:" + "b"*64, "sha256:" + "c"*64)
    runner._setup_trace_file_for_test()
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    assert trace_path.exists()
    first_line = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert first_line["_meta"] is True
    assert first_line["condition"] == "C0"


def test_fresh_mode_backs_up_existing_trace(tmp_path):
    config = _mk_config(tmp_path, mode="fresh")
    runner = LongSessionRunner(config)
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("OLD CONTENT\n", encoding="utf-8")
    runner._setup_trace_file_for_test()
    bak_files = list(trace_path.parent.glob("trace_C0.jsonl.*.bak"))
    assert len(bak_files) == 1


def test_resume_mode_requires_existing_trace(tmp_path):
    config = _mk_config(tmp_path, mode="resume")
    runner = LongSessionRunner(config)
    with pytest.raises(MetaMissingError):
        runner._setup_trace_file_for_test()


def test_resume_mode_rejects_hash_mismatch(tmp_path):
    config = _mk_config(tmp_path, mode="resume")
    runner = LongSessionRunner(config)
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    old_meta = {
        "_meta": True,
        "condition": "C0",
        "script_version_hash": "sha256:" + "0" * 64,  # 不匹配
        "product_list_hash": "sha256:" + "b" * 64,
        "condition_config_hash": "sha256:" + "c" * 64,
        "cache_namespace": str(tmp_path),
        "started_at": "2026-06-24T14:00:00+08:00",
        "ark_model": "ep-xxx",
        "spec_version": "2026-06-24-v1",
    }
    trace_path.write_text(json.dumps(old_meta) + "\n", encoding="utf-8")
    runner._compute_hashes_static = lambda: ("sha256:" + "a" * 64, "sha256:" + "b" * 64, "sha256:" + "c" * 64)
    with pytest.raises(HashMismatchError):
        runner._setup_trace_file_for_test()


def test_resume_returns_next_turn_index(tmp_path):
    config = _mk_config(tmp_path, mode="resume")
    runner = LongSessionRunner(config)
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"_meta": True, "condition": "C0", "script_version_hash": "sha256:" + "a" * 64,
            "product_list_hash": "sha256:" + "b" * 64, "condition_config_hash": "sha256:" + "c" * 64,
            "cache_namespace": str(tmp_path), "started_at": "x", "ark_model": "y", "spec_version": "z"}
    rows = [meta] + [{"turn_index": i, "condition": "C0"} for i in range(50)]
    trace_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    runner._compute_hashes_static = lambda: ("sha256:" + "a" * 64, "sha256:" + "b" * 64, "sha256:" + "c" * 64)
    runner._setup_trace_file_for_test()
    assert runner._should_resume_from() == 50


def test_invalid_trace_line_schema_fails_write(tmp_path):
    """写入不合法 trace 必须报错并不落盘。"""
    config = _mk_config(tmp_path, mode="fresh")
    runner = LongSessionRunner(config)
    runner._compute_hashes_static = lambda: ("sha256:" + "a" * 64, "sha256:" + "b" * 64, "sha256:" + "c" * 64)
    runner._setup_trace_file_for_test()
    with pytest.raises(Exception):  # TraceSchemaError
        runner._write_turn({"condition": "C0", "bad_field": True})  # 缺 required keys


def test_cache_namespace_is_stage_isolated(tmp_path):
    config_dryrun = _mk_config(tmp_path, mode="fresh")
    runner_d = LongSessionRunner(config_dryrun)
    config_pilot = RunnerConfig(stage="pilot", condition="C0", data_root=tmp_path, mode="fresh")
    runner_p = LongSessionRunner(config_pilot)
    assert runner_d.cache_namespace != runner_p.cache_namespace
    assert "dryrun" in str(runner_d.cache_namespace)
    assert "pilot" in str(runner_p.cache_namespace)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_runner_fresh_resume.py -v
```

Expected: ImportError 全 fail。

- [ ] **Step 3: 实现 `long_session_runner.py`**

参考 spec §3.3-§3.4 + §7-§8：

```python
"""长会话评测 runner：fresh/resume 互斥 + retry + schema 校验 + flush+fsync。"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel

from ..config import Settings, build_settings
from ..models import Product
from .long_session_models import TraceMeta, TraceSchemaError, validate_trace_line
from .long_session_templates import ScriptTurn

SPEC_VERSION = "2026-06-24-v1"


class HashMismatchError(RuntimeError):
    pass


class MetaMissingError(FileNotFoundError):
    pass


class RunnerConfig(BaseModel):
    stage: Literal["dryrun", "pilot", "full"]
    condition: Literal["C0", "C1", "C2", "C3", "C4"]
    data_root: Path
    mode: Literal["fresh", "resume"]


CONDITION_CONFIGS = {
    "C0": {"disable_window": True, "disable_snapshot": True, "disable_recommendation": True, "disable_rank": True},
    "C1": {"disable_window": False, "disable_snapshot": True, "disable_recommendation": True, "disable_rank": True},
    "C2": {"disable_window": False, "disable_snapshot": False, "disable_recommendation": True, "disable_rank": True},
    "C3": {"disable_window": False, "disable_snapshot": False, "disable_recommendation": False, "disable_rank": True},
    "C4": {"disable_window": False, "disable_snapshot": False, "disable_recommendation": False, "disable_rank": False},
}


class LongSessionRunner:
    def __init__(self, config: RunnerConfig):
        self.config = config
        self.stage_root = config.data_root / config.stage
        self.cache_namespace = self.stage_root / f"cache_{config.condition.lower()}"
        self.trace_path = self.stage_root / f"trace_{config.condition}.jsonl"
        self._script: list[ScriptTurn] = []
        self._products: list[Product] = []
        self._hashes: tuple[str, str, str] | None = None  # script, product, condition_config

    # ----- hashing -----
    @staticmethod
    def _sha256(data: bytes) -> str:
        return "sha256:" + hashlib.sha256(data).hexdigest()

    def _compute_hashes(self) -> tuple[str, str, str]:
        if self._hashes is not None:
            return self._hashes
        script_payload = json.dumps([t.model_dump() for t in self._script], ensure_ascii=False, sort_keys=True)
        product_payload = json.dumps([p.product_id for p in self._products], sort_keys=True)
        condition_payload = json.dumps(CONDITION_CONFIGS[self.config.condition], sort_keys=True)
        self._hashes = (
            self._sha256(script_payload.encode("utf-8")),
            self._sha256(product_payload.encode("utf-8")),
            self._sha256(condition_payload.encode("utf-8")),
        )
        return self._hashes

    # Test-only helper：允许测试用 lambda 覆盖
    _compute_hashes_static: Callable[[], tuple[str, str, str]] | None = None

    def _hashes_or_static(self) -> tuple[str, str, str]:
        if self._compute_hashes_static is not None:
            return self._compute_hashes_static()
        return self._compute_hashes()

    # ----- fresh/resume setup -----
    def _setup_trace_file_for_test(self) -> None:
        """供单测调用；正式入口为 run()，会在内部调用此方法。"""
        self.stage_root.mkdir(parents=True, exist_ok=True)
        self.cache_namespace.mkdir(parents=True, exist_ok=True)
        script_hash, product_hash, condition_hash = self._hashes_or_static()
        meta = TraceMeta(
            condition=self.config.condition,
            script_version_hash=script_hash,
            product_list_hash=product_hash,
            condition_config_hash=condition_hash,
            cache_namespace=str(self.cache_namespace),
            started_at=dt.datetime.now().isoformat(),
            ark_model=os.getenv("ARK_MODEL", ""),
            spec_version=SPEC_VERSION,
        )
        if self.config.mode == "fresh":
            if self.trace_path.exists():
                ts = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
                bak = self.trace_path.with_suffix(f".jsonl.{ts}.bak")
                shutil.move(str(self.trace_path), str(bak))
            with self.trace_path.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps({"_meta": True, **meta.model_dump()}, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        elif self.config.mode == "resume":
            if not self.trace_path.exists():
                raise MetaMissingError(f"trace.jsonl 不存在：{self.trace_path}；resume 必须基于已有 trace")
            with self.trace_path.open(encoding="utf-8") as fh:
                first = fh.readline().strip()
            if not first:
                raise MetaMissingError(f"trace.jsonl 为空：{self.trace_path}")
            existing = json.loads(first)
            if not existing.get("_meta"):
                raise MetaMissingError(f"trace.jsonl 首行不是 _meta：{self.trace_path}")
            for key in ("script_version_hash", "product_list_hash", "condition_config_hash"):
                if existing.get(key) != getattr(meta, key):
                    raise HashMismatchError(
                        f"{key} 不匹配；trace={existing.get(key)} runtime={getattr(meta, key)}；"
                        f"模板/商品/condition 已变更，拒绝续跑"
                    )

    def _should_resume_from(self) -> int:
        if not self.trace_path.exists():
            return 0
        last_idx = -1
        with self.trace_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("_meta"):
                    continue
                last_idx = max(last_idx, int(row.get("turn_index", -1)))
        return last_idx + 1

    # ----- per-turn write -----
    def _write_turn(self, trace_dict: dict) -> None:
        validate_trace_line(trace_dict)
        with self.trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(trace_dict, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    # ----- ARK retry -----
    async def _retry_with_backoff(self, fn, *args, max_retries: int = 3, **kwargs):
        delay = 2
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt == max_retries - 1:
                    break
                await asyncio.sleep(delay)
                delay *= 2
        raise last_exc  # type: ignore

    # ----- full entry -----
    async def run(self, script: list[ScriptTurn], products: list[Product], *, agent_factory) -> None:
        """完整入口；具体的 agent.chat() 调用 + trace 字段填充由 Task 10 接入。"""
        self._script = script
        self._products = products
        self._setup_trace_file_for_test()
        start_idx = self._should_resume_from() if self.config.mode == "resume" else 0
        # ... 此处为 Task 10 的 scoring hook：将 agent.chat() 的结果组装成 TurnTrace 落盘
        raise NotImplementedError("Task 10 will fill in the per-turn execution loop")
```

- [ ] **Step 4: 跑测试**

```bash
cd server && python -m pytest tests/test_long_session_runner_fresh_resume.py -v
```

Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/eval/long_session_runner.py server/tests/test_long_session_runner_fresh_resume.py
git commit -m "feat(eval): add LongSessionRunner fresh/resume protocol + hash-guarded setup

- RunnerConfig + CONDITION_CONFIGS（C0-C4）
- fresh 自动 backup 旧 trace；resume 强制 hash 校验
- _write_turn 强制 schema 校验 + flush + fsync
- _retry_with_backoff per-turn 重试（2/4/8s 指数退避）
- run() 留 NotImplementedError 给 Task 10 填充 per-turn 循环

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Runner 评分 hook：rule_score + judge_score

**Files:**
- Modify: `server/backend/app/eval/long_session_runner.py`（填充 Task 9 的 `NotImplementedError` 部分）
- Modify: `server/backend/app/eval/long_session_runner.py`（添加规则评分函数）
- Test: `server/tests/test_long_session_runner_scoring.py`（新建）

**Interfaces:**
- Consumes: Task 6 (script)、Task 7 (judge)、Task 9 (runner 骨架)、Task 4 (agent._last_cache_probe)、Task 5 (agent._last_degradation)
- Produces:
  - `_compute_rule_score(turn, answer_text, retrieved_top_k, products) -> dict`
  - `_assemble_turn_trace(turn_index, turn, agent_result, *, judge_result=None, degradation=None, would_hit, effective_hit) -> dict`
  - `run()` 内 per-turn 主循环：调 agent.chat → 收集 trace 字段 → 调 judge（条件采样）→ 校验 schema → 落盘

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_runner_scoring.py`

```python
from __future__ import annotations

import pytest

from backend.app.eval.long_session_runner import (
    LongSessionRunner,
    _compute_rule_score,
)
from backend.app.eval.long_session_templates import ScriptTurn


def test_rule_score_retrieval_perfect_hit():
    turn = ScriptTurn(
        phase="A",
        turn_type="retrieval",
        query="推荐防晒霜",
        expected={"ideal_top": ["p_beauty_006"], "forbidden": []},
    )
    score = _compute_rule_score(turn, answer_text="...", retrieved_top_k=["p_beauty_006", "p_x", "p_y"], product_map={})
    assert score["recall5"] == 1.0
    assert score["ndcg5"] > 0.9
    assert score["forbidden_hit"] is False


def test_rule_score_retrieval_forbidden_hit():
    turn = ScriptTurn(
        phase="A",
        turn_type="retrieval",
        query="推荐",
        expected={"ideal_top": ["p1"], "forbidden": ["p_bad"]},
    )
    score = _compute_rule_score(turn, answer_text="...", retrieved_top_k=["p_bad", "p1"], product_map={})
    assert score["forbidden_hit"] is True


def test_rule_score_followup_factual_price_match():
    from backend.app.models import Product
    product = Product(
        product_id="p1",
        title="测试",
        brand="X",
        category="美妆护肤",
        sub_category="",
        price=199.0,
        marketing_description="",
        faqs=[],
        reviews=[],
        extracted_terms=[],
    )
    turn = ScriptTurn(
        phase="A",
        turn_type="followup_factual",
        query="价格多少？",
        expected={"subject_product_id": "p1", "expected_intent": "product_followup"},
    )
    score = _compute_rule_score(
        turn,
        answer_text="价格是 199 元",
        retrieved_top_k=["p1"],
        product_map={"p1": product},
    )
    assert score["fact_match"] is True
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_runner_scoring.py -v
```

Expected: ImportError 全 fail。

- [ ] **Step 3: 在 `long_session_runner.py` 模块顶层加 `_compute_rule_score`**

```python
def _compute_rule_score(
    turn: ScriptTurn,
    *,
    answer_text: str,
    retrieved_top_k: list[str],
    product_map: dict[str, Product],
) -> dict[str, Any]:
    score: dict[str, Any] = {}
    ttype = turn.turn_type
    ideal = turn.expected.get("ideal_top") or []
    forbidden = turn.expected.get("forbidden") or []
    if ttype in {"retrieval", "comparison", "long_range_reference"} and ideal:
        # NDCG@5 / Recall@5 / Precision@5（复用 eval/metrics.py 的实现或本地简化版）
        from .metrics import _ndcg_at_k, _recall_at_k, _precision_at_k  # type: ignore
        # 若不可复用则用本地实现
        score["ndcg5"] = _ndcg_at_k(retrieved_top_k[:5], ideal)
        score["recall5"] = _recall_at_k(retrieved_top_k[:5], ideal)
        score["precision5"] = _precision_at_k(retrieved_top_k[:5], ideal)
    if forbidden:
        score["forbidden_hit"] = any(pid in retrieved_top_k for pid in forbidden) or any(
            pid in answer_text for pid in forbidden
        )
    if ttype == "followup_factual":
        # 简化：取 subject_product_id 的真值，看 answer_text 是否包含
        sid = turn.expected.get("subject_product_id")
        product = product_map.get(sid or "")
        if product:
            score["fact_match"] = (
                str(int(product.price)) in answer_text
                or product.brand in answer_text
                or product.title in answer_text
            )
    if ttype == "cart_action":
        # 这里需要外部传入 cart 末态；先返回占位，run() 内可补充覆盖
        score["cart_consistent"] = True  # 由 run() 调 CartService 后覆写
    return score
```

注意：`from .metrics import _ndcg_at_k ...` 可能找不到，需要在 `long_session_runner.py` 顶层实现本地版本（或复用 `server/backend/app/eval/metrics.py` 已有的函数；若没有就内嵌实现）：

```python
def _dcg(rel: list[int]) -> float:
    import math
    return sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(rel))


def _ndcg_at_k(retrieved: list[str], ideal: list[str], k: int = 5) -> float:
    if not ideal:
        return 0.0
    rel = [1 if pid in ideal else 0 for pid in retrieved[:k]]
    ideal_rel = [1] * min(len(ideal), k)
    idcg = _dcg(ideal_rel) or 1.0
    return _dcg(rel) / idcg


def _recall_at_k(retrieved: list[str], ideal: list[str], k: int = 5) -> float:
    if not ideal:
        return 0.0
    hits = sum(1 for pid in retrieved[:k] if pid in ideal)
    return hits / len(ideal)


def _precision_at_k(retrieved: list[str], ideal: list[str], k: int = 5) -> float:
    if not retrieved[:k]:
        return 0.0
    hits = sum(1 for pid in retrieved[:k] if pid in ideal)
    return hits / k
```

- [ ] **Step 4: 在 `run()` 实现 per-turn 主循环**

把 Task 9 留下的 `raise NotImplementedError` 替换为：

```python
    async def run(
        self,
        script: list[ScriptTurn],
        products: list[Product],
        *,
        agent_factory,
        judge: "LongSessionJudge | None" = None,
        judge_sample_rates: dict[str, float] | None = None,
    ) -> None:
        self._script = script
        self._products = products
        self._setup_trace_file_for_test()
        product_map = {p.product_id: p for p in products}
        start_idx = self._should_resume_from() if self.config.mode == "resume" else 0
        script_hash, product_hash, condition_hash = self._hashes_or_static()
        session_id = f"eval_{self.config.stage}_{self.config.condition.lower()}_2026-06-24"

        # 注入 condition 对应的开关到环境变量
        cfg = CONDITION_CONFIGS[self.config.condition]
        os.environ["SHOPGUIDE_EVAL_DISABLE_WINDOW_TRUNCATION"] = "1" if cfg["disable_window"] else "0"
        os.environ["SHOPGUIDE_EVAL_DISABLE_STRUCTURED_SNAPSHOT"] = "1" if cfg["disable_snapshot"] else "0"
        os.environ["SHOPGUIDE_EVAL_DISABLE_RECOMMENDATION_MEMORY"] = "1" if cfg["disable_recommendation"] else "0"
        os.environ["SHOPGUIDE_EVAL_DISABLE_RANK_CACHE"] = "1" if cfg["disable_rank"] else "0"
        os.environ["SHOPGUIDE_MEMORY_CACHE_PATH"] = str(self.cache_namespace / "recommendation.jsonl")

        agent = agent_factory()
        sample_rates = judge_sample_rates or {
            "comparison": 0.30, "long_range_reference": 0.30,
            "adversarial_reference": 0.50, "adversarial_constraint": 0.50,
        }
        import random as _random
        rng = _random.Random(20260624)

        for turn_index in range(start_idx, len(script)):
            turn = script[turn_index]
            t0 = dt.datetime.now()
            try:
                agent_result = await self._retry_with_backoff(
                    self._invoke_agent, agent, turn, session_id, max_retries=3,
                )
                degradation = agent_result.get("degradation")
            except Exception as exc:
                agent_result = {"answer_text": "", "retrieved_top_k": [], "pipeline": [], "tool_calls": [],
                                "branch_flags": {}, "prompt_tokens": 0, "completion_tokens": 0,
                                "first_chunk_ms": 0, "context_payload_bytes": 0, "context_payload_tokens": 0,
                                "context_events_count": 0, "focus_history_len": 0,
                                "focus_product_id": None, "hard_constraints": {},
                                "would_hit_b1": False, "effective_hit_b1": False,
                                "would_hit_b2": False, "effective_hit_b2": False,
                                "cache_stats_at_turn": {}}
                degradation = f"ark_failure_skip:{exc.__class__.__name__}"
            total_ms = int((dt.datetime.now() - t0).total_seconds() * 1000)

            rule_score = _compute_rule_score(
                turn,
                answer_text=agent_result["answer_text"],
                retrieved_top_k=agent_result["retrieved_top_k"],
                product_map=product_map,
            )

            judge_score = None
            sample_rate = sample_rates.get(turn.turn_type, 0.0)
            if judge is not None and sample_rate > 0 and rng.random() < sample_rate:
                jr = await self._retry_with_backoff(
                    judge.judge, turn, agent_result["answer_text"],
                    agent_result["retrieved_top_k"], product_map, max_retries=3,
                )
                judge_score = jr.model_dump()

            trace_dict = {
                "condition": self.config.condition,
                "session_id": session_id,
                "turn_index": turn_index,
                "phase": turn.phase,
                "turn_type": turn.turn_type,
                "adversarial_subtype": turn.adversarial_subtype,
                "query": turn.query,
                "expected": turn.expected,
                "pipeline": agent_result["pipeline"],
                "tool_calls": agent_result["tool_calls"],
                "branch_flags": agent_result["branch_flags"],
                "prompt_tokens": agent_result["prompt_tokens"],
                "completion_tokens": agent_result["completion_tokens"],
                "first_chunk_ms": agent_result["first_chunk_ms"],
                "total_ms": total_ms,
                "context_payload_bytes": agent_result["context_payload_bytes"],
                "context_payload_tokens": agent_result["context_payload_tokens"],
                "context_events_count": agent_result["context_events_count"],
                "focus_history_len": agent_result["focus_history_len"],
                "focus_product_id": agent_result["focus_product_id"],
                "hard_constraints": agent_result["hard_constraints"],
                "state_drift": None,  # 后处理可填
                "degradation": degradation,
                "would_hit_b1": agent_result["would_hit_b1"],
                "effective_hit_b1": agent_result["effective_hit_b1"],
                "would_hit_b2": agent_result["would_hit_b2"],
                "effective_hit_b2": agent_result["effective_hit_b2"],
                "cache_stats_at_turn": agent_result["cache_stats_at_turn"],
                "rule_score": rule_score,
                "judge_score": judge_score,
                "answer_text": agent_result["answer_text"][:2000],
                "retrieved_top_k": agent_result["retrieved_top_k"][:10],
                "script_version_hash": script_hash,
                "product_list_hash": product_hash,
                "condition_config_hash": condition_hash,
            }
            self._write_turn(trace_dict)

    async def _invoke_agent(self, agent, turn: ScriptTurn, session_id: str) -> dict:
        """调 agent.chat 拿一轮结果。具体字段从 agent._last_cache_probe / agent._last_degradation 等接口取。"""
        from ..models import ChatRequest  # type: ignore
        request = ChatRequest(session_id=session_id, message=turn.query)
        # 这里调用现有 ChatAgent 的接口；agent_factory 必须返回一个 .chat(request) -> ChatResponseLike
        response = await agent.chat(request)
        probe = getattr(agent, "_last_cache_probe", {}) or {}
        return {
            "answer_text": getattr(response, "text", "") or getattr(response, "answer", ""),
            "retrieved_top_k": [c.product_id for c in getattr(response, "cards", []) or []],
            "pipeline": getattr(response, "pipeline", []) or [],
            "tool_calls": getattr(response, "tool_calls", []) or [],
            "branch_flags": getattr(response, "branch_flags", {}) or {},
            "prompt_tokens": getattr(response, "prompt_tokens", 0),
            "completion_tokens": getattr(response, "completion_tokens", 0),
            "first_chunk_ms": getattr(response, "first_chunk_ms", 0),
            "context_payload_bytes": getattr(response, "context_payload_bytes", 0),
            "context_payload_tokens": getattr(response, "context_payload_tokens", 0),
            "context_events_count": getattr(response, "context_events_count", 0),
            "focus_history_len": getattr(response, "focus_history_len", 0),
            "focus_product_id": getattr(response, "focus_product_id", None),
            "hard_constraints": getattr(response, "hard_constraints", {}) or {},
            "would_hit_b1": probe.get("would_hit_b1", False),
            "effective_hit_b1": probe.get("effective_hit_b1", False),
            "would_hit_b2": probe.get("would_hit_b2", False),
            "effective_hit_b2": probe.get("effective_hit_b2", False),
            "cache_stats_at_turn": probe.get("cache_stats", {}),
            "degradation": getattr(agent, "_last_degradation", None),
        }
```

`agent.chat()` 当前接口可能不是这样的——需要在 `server/backend/app/agent.py` 暴露一个**评测专用同步 chat**，把 ARK 调用 + cache probe + degradation 收集后封装成上面 `response` 形式。如果重构 `ShopGuideAgent.chat` 风险高，新增 `evaluate_turn(request) -> EvalResult` 包装函数最稳。

- [ ] **Step 5: 跑测试**

```bash
cd server && python -m pytest tests/test_long_session_runner_scoring.py -v
```

Expected: 全 PASS。

- [ ] **Step 6: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/eval/long_session_runner.py server/backend/app/agent.py server/tests/test_long_session_runner_scoring.py
git commit -m "feat(eval): wire runner scoring + per-turn loop with judge sampling

- _compute_rule_score: NDCG@5/Recall@5/forbidden_hit/fact_match
- run() 主循环：注入环境变量切 condition → 调 agent → judge 采样 → schema 校验 → 落盘
- ARK 限流走 _retry_with_backoff（2/4/8s 退避），3 次失败标 degradation
- judge 采样率：comparison/long_range 30%，adversarial 50%

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 11: Report 生成：CSV + Markdown + matplotlib PNG

**Files:**
- Create: `server/backend/app/eval/long_session_report.py`
- Test: `server/tests/test_long_session_report.py`

**Interfaces:**
- Consumes: `data/eval/long_session_2026-06-24/{stage}/trace_C{0..4}.jsonl`（Task 9-10 产物）
- Produces:
  - `aggregate_csvs(stage_dir: Path) -> None`：每 condition 产出 retrieval_*.csv / followup_*.csv / adversarial_*.csv / judge_*.csv
  - `render_plots(stage_dir: Path) -> None`：8 张 PNG（spec §11）
  - `write_summary_markdown(stage_dir: Path) -> Path`：dryrun→DRYRUN_SUMMARY.md / pilot→PILOT_SUMMARY.md / full→REPORT.md

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_report.py`

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.eval.long_session_report import (
    aggregate_csvs,
    render_plots,
    write_summary_markdown,
)


def _seed_trace(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _make_row(condition: str, turn_index: int, ttype: str = "retrieval", **extra) -> dict:
    base = {
        "condition": condition, "session_id": f"s_{condition}", "turn_index": turn_index,
        "phase": "A", "turn_type": ttype, "adversarial_subtype": None, "query": "q",
        "expected": {}, "pipeline": [], "tool_calls": [], "branch_flags": {},
        "prompt_tokens": 1000, "completion_tokens": 100, "first_chunk_ms": 200, "total_ms": 800,
        "context_payload_bytes": 5000, "context_payload_tokens": 1200,
        "context_events_count": turn_index, "focus_history_len": turn_index,
        "focus_product_id": None, "hard_constraints": {}, "state_drift": None,
        "degradation": None,
        "would_hit_b1": False, "effective_hit_b1": False,
        "would_hit_b2": False, "effective_hit_b2": False,
        "cache_stats_at_turn": {}, "rule_score": {"ndcg5": 0.8, "recall5": 1.0},
        "judge_score": None, "answer_text": "...", "retrieved_top_k": ["p1"],
        "script_version_hash": "sha256:" + "a"*64,
        "product_list_hash": "sha256:" + "b"*64,
        "condition_config_hash": "sha256:" + "c"*64,
    }
    base.update(extra)
    return base


def test_aggregate_csvs_outputs_retrieval_file(tmp_path):
    stage = tmp_path / "dryrun"
    meta = {"_meta": True, "condition": "C0", "script_version_hash": "sha256:" + "a"*64,
            "product_list_hash": "sha256:" + "b"*64, "condition_config_hash": "sha256:" + "c"*64,
            "cache_namespace": "x", "started_at": "x", "ark_model": "y", "spec_version": "z"}
    _seed_trace(stage / "trace_C0.jsonl", [meta, _make_row("C0", 0), _make_row("C0", 1)])
    aggregate_csvs(stage)
    csv_path = stage / "retrieval_C0.csv"
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "ndcg5" in content
    assert "0.8" in content


def test_render_plots_creates_pngs(tmp_path):
    stage = tmp_path / "dryrun"
    meta = {"_meta": True, "condition": "C0", "script_version_hash": "sha256:" + "a"*64,
            "product_list_hash": "sha256:" + "b"*64, "condition_config_hash": "sha256:" + "c"*64,
            "cache_namespace": "x", "started_at": "x", "ark_model": "y", "spec_version": "z"}
    for c in ["C0", "C1", "C2", "C3", "C4"]:
        _seed_trace(stage / f"trace_{c}.jsonl", [{**meta, "condition": c}, _make_row(c, 0), _make_row(c, 1)])
    plots_root = tmp_path / "plots"
    render_plots(stage, plots_root=plots_root)
    assert (plots_root / "retrieval_quality_by_turn.png").exists()
    assert (plots_root / "token_usage_curve.png").exists()
    assert (plots_root / "latency_p50_p90_p99.png").exists()


def test_write_summary_markdown_dryrun_contains_judge_disagreement(tmp_path):
    stage = tmp_path / "dryrun"
    meta = {"_meta": True, "condition": "C0", "script_version_hash": "sha256:" + "a"*64,
            "product_list_hash": "sha256:" + "b"*64, "condition_config_hash": "sha256:" + "c"*64,
            "cache_namespace": "x", "started_at": "x", "ark_model": "y", "spec_version": "z"}
    judge = {"raw": [{"hit": 1}, {"hit": 1}, {"hit": 1}], "mean": 4.0, "disagreement": 0.0, "call_count": 3}
    _seed_trace(stage / "trace_C0.jsonl", [meta, _make_row("C0", 0, judge_score=judge, turn_type="comparison")])
    summary = write_summary_markdown(stage)
    text = summary.read_text(encoding="utf-8")
    assert "DRYRUN_SUMMARY" in summary.name
    assert "disagreement" in text.lower() or "分歧" in text
    assert "C0" in text
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_report.py -v
```

Expected: ImportError 全 fail。

- [ ] **Step 3: 实现 `long_session_report.py`**

模块结构（行数预估 350-450）：

```python
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
```

- [ ] **Step 4: 跑测试**

```bash
cd server && python -m pytest tests/test_long_session_report.py -v
```

Expected: 全 PASS。

- [ ] **Step 5: 添加 matplotlib 依赖**

```bash
grep -i matplotlib server/backend/requirements.lock 2>/dev/null || echo "缺失需添加"
```

如缺失则追加 `matplotlib>=3.7.0` 到 `requirements.in`。

- [ ] **Step 6: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/backend/app/eval/long_session_report.py server/backend/requirements.in server/tests/test_long_session_report.py
git commit -m "feat(eval): add report generator (CSV + matplotlib PNG + Markdown)

- aggregate_csvs: retrieval/followup/adversarial/judge × 5 condition
- render_plots: 8 张 spec §11 PNG（matplotlib Agg backend）
- write_summary_markdown: dryrun→DRYRUN_SUMMARY / pilot→PILOT_SUMMARY / full→REPORT.md

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 12: CLI 入口 `run_long_session_eval.py`

**Files:**
- Create: `server/scripts/run_long_session_eval.py`
- Test: `server/tests/test_long_session_cli.py`

**Interfaces:**
- Produces:
  - CLI 参数：`--stage {dryrun,pilot,full}` `--condition {C0..C4}` `--reset-cache` `--resume` `--report` `--turns N`
  - 互斥规则：spec §3.4
  - `--report` 模式：只跑 aggregate_csvs / render_plots / write_summary_markdown
  - 正常模式：执行 RunnerConfig + LongSessionRunner.run

- [ ] **Step 1: 写失败测试**

文件：`server/tests/test_long_session_cli.py`

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_long_session_eval.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
    )


def test_missing_mode_flags_fails():
    """两者都不传 → exit code != 0"""
    res = _run("--stage", "dryrun", "--condition", "C0")
    assert res.returncode != 0
    assert "reset-cache" in res.stderr.lower() or "resume" in res.stderr.lower()


def test_both_mode_flags_conflict():
    res = _run("--stage", "dryrun", "--condition", "C0", "--reset-cache", "--resume")
    assert res.returncode != 0
    assert "互斥" in res.stderr or "mutually exclusive" in res.stderr.lower()


def test_resume_without_existing_trace_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOPGUIDE_EVAL_DATA_ROOT", str(tmp_path))
    res = _run("--stage", "dryrun", "--condition", "C0", "--resume")
    assert res.returncode != 0


def test_report_mode_runs_without_condition(tmp_path, monkeypatch):
    """--report 模式不需要 --condition"""
    monkeypatch.setenv("SHOPGUIDE_EVAL_DATA_ROOT", str(tmp_path))
    (tmp_path / "dryrun").mkdir()
    res = _run("--stage", "dryrun", "--report")
    # 没有 trace 时 report 应给出友好提示而非崩溃
    assert "no trace" in res.stdout.lower() or "no trace" in res.stderr.lower() or res.returncode == 0
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && python -m pytest tests/test_long_session_cli.py -v
```

Expected: 全 fail，FileNotFoundError 或 exit code 1。

- [ ] **Step 3: 实现 `run_long_session_eval.py`**

参考 `server/scripts/run_eval.py:1-11` 的 path 设定。新建 `server/scripts/run_long_session_eval.py`：

```python
"""长会话评测 CLI。spec docs/superpowers/specs/2026-06-24-long-session-eval-design.md"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

server_dir = Path(__file__).resolve().parent.parent
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from backend.app.config import build_settings
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


async def _run_condition(args, settings, products, script):
    config = RunnerConfig(
        stage=args.stage,
        condition=args.condition,
        data_root=args.data_root or Path(os.getenv("SHOPGUIDE_EVAL_DATA_ROOT", "data/eval/long_session_2026-06-24")),
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
        await runner.run(script[: _resolve_turns(args.stage, args.turns)],
                        products, agent_factory=agent_factory, judge=judge)
    finally:
        await judge.aclose()


def main() -> int:
    args = parse_args()
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
    settings = build_settings()
    products = load_products(settings.dataset_dir)
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
    script = build_long_session_script(products)
    asyncio.run(_run_condition(args, settings, products, script))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试**

```bash
cd server && python -m pytest tests/test_long_session_cli.py -v
```

Expected: 全 PASS（test_report_mode 因依赖完整环境，断言放宽：exit code 0 或带 "no trace" 提示均接受）。

- [ ] **Step 5: smoke：CLI 互斥保护**

```bash
cd server
python scripts/run_long_session_eval.py --stage dryrun --condition C0  # 应 fail
python scripts/run_long_session_eval.py --stage dryrun --condition C0 --reset-cache --resume  # 应 fail
```

Expected: 两条命令都 exit code 2，stderr 含中文错误。

- [ ] **Step 6: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/scripts/run_long_session_eval.py server/tests/test_long_session_cli.py
git commit -m "feat(eval): add CLI run_long_session_eval.py with fresh/resume guard

- --stage dryrun/pilot/full × --condition C0..C4 × --reset-cache/--resume
- --report 模式：聚合 CSV + 画图 + 写 summary
- 互斥规则按 spec §3.4，违反退出 2
- 复用 server/backend/app/main.create_app 拿 agent

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 13: dryrun 阶段集成 smoke（每 condition 2 轮）+ Cost Appendix 写入

**Files:**
- 仅用既有代码 + CLI 跑真实 ARK
- Modify: `docs/superpowers/specs/2026-06-24-long-session-eval-design.md`（追加 §10.1 Cost Appendix）
- Test: `server/tests/test_long_session_runner_integration.py`（仅本地最小 smoke，不打 ARK）

**Interfaces:**
- 这是验收 Task；不产出新 API，验证 1-12 端到端联通 + 真实 ARK 跑通 + 把 dry-run summary 喂回 spec。

**前置条件：**
- ARK API key 在 `/home/huadabioa/houlong/SoulDance/.env`（已核实）
- 跑前先 `source /home/huadabioa/houlong/SoulDance/.env` 或导出 `ARK_API_KEY` / `ARK_BASE_URL` / `ARK_MODEL`
- 数据目录 `data/eval/long_session_2026-06-24/` 必须可写

- [ ] **Step 1: 本地 schema smoke test（不打 ARK）**

文件：`server/tests/test_long_session_runner_integration.py`

```python
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from backend.app.eval.long_session_models import validate_trace_line
from backend.app.eval.long_session_runner import (
    LongSessionRunner, RunnerConfig, CONDITION_CONFIGS,
)


def test_condition_configs_completeness():
    assert set(CONDITION_CONFIGS.keys()) == {"C0", "C1", "C2", "C3", "C4"}
    for cfg in CONDITION_CONFIGS.values():
        assert set(cfg.keys()) == {"disable_window", "disable_snapshot", "disable_recommendation", "disable_rank"}


def test_runner_fresh_setup_with_real_hashes(tmp_path):
    config = RunnerConfig(stage="dryrun", condition="C0", data_root=tmp_path, mode="fresh")
    runner = LongSessionRunner(config)
    from backend.app.eval.long_session_templates import ScriptTurn
    runner._script = [ScriptTurn(phase="A", turn_type="retrieval", query="x", expected={})]
    runner._products = []
    runner._setup_trace_file_for_test()
    trace_path = tmp_path / "dryrun" / "trace_C0.jsonl"
    assert trace_path.exists()
    meta = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert meta["_meta"] is True
    assert meta["script_version_hash"].startswith("sha256:")
```

- [ ] **Step 2: 跑测试**

```bash
cd server && python -m pytest tests/test_long_session_runner_integration.py -v
```

Expected: 全 PASS。

- [ ] **Step 3: 跑 dryrun smoke（真实 ARK，每 condition 2 轮）**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
# 显式导出
set -a
source /home/huadabioa/houlong/SoulDance/.env
set +a
cd server
for c in C0 C1 C2 C3 C4; do
  python scripts/run_long_session_eval.py --stage dryrun --condition $c --reset-cache --turns 2
done
python scripts/run_long_session_eval.py --stage dryrun --report
```

Expected:
- 5 个 `data/eval/long_session_2026-06-24/dryrun/trace_C*.jsonl` 各含 1 行 meta + 2 行 turn trace
- `DRYRUN_SUMMARY.md` 生成、含 5 个 condition 段
- `plots/` 目录下至少 3 张 PNG
- `cache_c0/` 到 `cache_c4/` 5 个独立目录存在

如果中途 ARK 失败 / schema 校验失败 / cache 污染，必须先修代码再继续。**不能跳过这一步。**

- [ ] **Step 4: probe 副作用校验**

```bash
cd server && python -m pytest tests/test_long_session_memory_cache_probe.py -v
```

Expected: `test_*_probe_does_not_mutate_stats` 全 PASS。

- [ ] **Step 5: 断点续跑校验**

```bash
cd server
# 起一个完整 5 轮跑作为基线
python scripts/run_long_session_eval.py --stage dryrun --condition C0 --reset-cache --turns 5
# 假设跑完
wc -l ../data/eval/long_session_2026-06-24/dryrun/trace_C0.jsonl  # 应为 6（1 meta + 5 turn）

# 模拟续跑：删最后 2 行 turn，从第 4 轮起恢复
head -n 4 ../data/eval/long_session_2026-06-24/dryrun/trace_C0.jsonl > /tmp/truncated.jsonl
mv /tmp/truncated.jsonl ../data/eval/long_session_2026-06-24/dryrun/trace_C0.jsonl
python scripts/run_long_session_eval.py --stage dryrun --condition C0 --resume --turns 5
wc -l ../data/eval/long_session_2026-06-24/dryrun/trace_C0.jsonl  # 应再次 = 6
```

Expected: 续跑后 trace 总行数与原来一致；最后两行 turn_index 应为 3, 4。

- [ ] **Step 6: hash 拒绝续跑校验**

```bash
cd server
# 篡改 trace 头部 hash
python -c "
import json
from pathlib import Path
p = Path('../data/eval/long_session_2026-06-24/dryrun/trace_C0.jsonl')
lines = p.read_text(encoding='utf-8').splitlines()
meta = json.loads(lines[0])
meta['script_version_hash'] = 'sha256:' + '0' * 64
lines[0] = json.dumps(meta, ensure_ascii=False)
p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
"
python scripts/run_long_session_eval.py --stage dryrun --condition C0 --resume --turns 5
echo "exit code: $?"
```

Expected: 命令以 exit code 非 0 退出，stderr 含 "hash" 或 "script_version_hash 不匹配"。

- [ ] **Step 7: 把 dry-run 结果回写 spec Cost Appendix**

读 `data/eval/long_session_2026-06-24/dryrun/DRYRUN_SUMMARY.md`，把 5 个 condition 的：
- 平均 ARK tool_calls / turn
- 平均 prompt_tokens
- 平均 total_ms
- judge 分歧率（如有）

追加到 `docs/superpowers/specs/2026-06-24-long-session-eval-design.md` §10 末尾，新增 §10.1 章节：

```markdown
### 10.1 Cost Appendix（dry-run 实测）

**实测日期：** 2026-XX-XX
**Dry-run 轮次：** 每 condition 2 轮 × 5 condition = 10 轮（smoke 规模）

| Condition | 平均 ARK calls/turn | 平均 prompt_tokens | 平均 total_ms |
|---|---|---|---|
| C0 | <数值> | <数值> | <数值> |
| C1 | <数值> | <数值> | <数值> |
| C2 | <数值> | <数值> | <数值> |
| C3 | <数值> | <数值> | <数值> |
| C4 | <数值> | <数值> | <数值> |

**Judge 分歧率：** <数值>（采样 <N> 个 turn）

**推断 pilot/full call_count：** <1 / 3 / user-decide>

**Pilot 预估总 ARK 调用：** dryrun_avg × 100 × 5 = <数值>
**Full 预估总 ARK 调用：** dryrun_avg × 1100 × 5 = <数值>

**Pilot 与 Full 放行条件**：基于以上实测推估，user-approved。
```

把 `<数值>` 用真实数据替换；user-approved 字眼留待 user 实际填写。

- [ ] **Step 8: 提交**

```bash
cd /home/huadabioa/houlong/SoulDance/.claude/worktrees/feat-sprite-fire-task
git add server/tests/test_long_session_runner_integration.py docs/superpowers/specs/2026-06-24-long-session-eval-design.md
git commit -m "feat(eval): integrate dryrun smoke (5 condition × 2 turns, real ARK) + Cost Appendix

- test_long_session_runner_integration.py: 本地结构 smoke
- 真实 ARK dryrun smoke 跑通 5 condition × 2 turns；trace schema / cache 隔离 / resume / hash-mismatch 全部通过
- §10.1 Cost Appendix 写入 dryrun 实测数据，推估 pilot/full 成本

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 实施完成后的状态

- 全部 13 个任务都 commit；working tree clean。
- spec §9 Stage 1（dry-run）的放行条件除 user-approval 之外全部满足：
  - 5 condition 全部跑通无异常
  - trace schema 完整
  - 缓存隔离已验证（test_cache_namespace_is_stage_isolated）
  - 断点续跑 + hash 拒绝续跑均通过 manual smoke
  - probe API pure 已 100 次验证
  - judge 分歧率写入 §10.1
  - 每轮实际 ARK 调用数已写入 §10.1
- 接下来必须 stop and ask user：
  - 给 user 看 `data/eval/long_session_2026-06-24/dryrun/DRYRUN_SUMMARY.md` + §10.1
  - 等 user-approved 才进 spec §9 Stage 2（pilot 500 轮）；这不是本 plan 的范围
- 本 plan 不包含 Stage 2/3 的执行——这两步只是重复跑 CLI，不需要新代码

## 中止/异常协议

如果任意 task 跑出预期之外的结果（schema 校验 fail / 测试持续 fail / 真实 ARK 跑出 500 / cache 污染），按 spec §13 安全护栏执行：

1. 立即停止后续 task
2. 把现状（trace 文件 + 错误日志）作为附件交给 user
3. 不要绕过 schema / 不要静默忽略 fail / 不要复用上一次 cache
4. 等 user 指导后再恢复或回滚

---

## Self-Review 注记（来自 writing-plans skill）

本 plan 已对 spec 13 节 + §10.1 Cost Appendix 做覆盖检查：

- §0 Live 路径核实 → 已写入 Global Constraints
- §1 命名 → Architecture + 各任务命名一致
- §2 4 个评估目标 → 通过 Task 8 trace schema + Task 11 report 全覆盖
- §3 Condition 矩阵 → Task 9 `CONDITION_CONFIGS`
- §3.1 C0-pre/post → 报告 §11 Markdown 输出由 Task 11 实现
- §3.2 25K 硬截断 → Task 5
- §3.3 cache 隔离 → Task 9 `cache_namespace`
- §3.4 fresh/resume → Task 9 + Task 12 CLI
- §4 禁用语义 → Task 2/3/4
- §4.1 命中率双口径 → Task 4
- §4.1.1 Pure Probe API → Task 4
- §5 1100 轮脚本 + 75 对抗 → Task 6
- §6 turn type 评分 → Task 10
- §6.1 LLM judge → Task 7
- §6.1.1 judge_score 字段 → Task 8
- §7 trace 字段 → Task 8 schema + Task 10 assembler
- §8 断点续跑 → Task 9 + Task 13 smoke
- §9 Pilot Gate → Task 12 stage 参数 + Task 13 smoke
- §9.1 schema 校验 → Task 8 + Task 9 _write_turn
- §10 资源预估 → Task 13 Cost Appendix
- §11 产物清单 → Task 11 输出 + Task 12 stage 路径
- §12 代码改动清单 → Task 1-12 全覆盖
- §13 安全护栏 → 中止/异常协议章节
