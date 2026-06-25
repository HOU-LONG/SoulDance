# Pilot Readiness — 缺口修复设计草案

**STATUS: DRAFT — 待评审，未进入实现**
**Date:** 2026-06-25
**Owner:** HOU-LONG
**Scope:** 在启动 long-session evaluation pilot 阶段（500 turns）之前，补齐 4 项关键缺口：runner 与 main 的 `handle_message` API 漂移、trace 中 token 计数为 0、trace 中 tool_calls/pipeline 为空、ARK 连续调用稳定性未验证。

---

## 0. 上下文

`feat/rag-eval-overhaul` 已 merge 到 main（19 commits），dryrun smoke（13 真实 ARK 调用）通过。Spec `docs/superpowers/specs/2026-06-24-long-session-eval-design.md` §10.1 Cost Appendix 已记录：

> **已知数据缺口（待后续修复）：**
> - `prompt_tokens` / `tool_calls` 全为 0。原因：Task 10 的 `_invoke_agent` 当前只从 `handle_message` 的 events 里抽取 `assistant_text` 和 `product_card`，未抽取 token 计数与工具调用链。
> - Pilot 阶段进入前必须补齐。

外加 rebase 后发现的 P0：main 上 `handle_message(self, user_id, request)` 而 runner 仍传 `(request)` —— runtime 即报 `TypeError`。

本 spec 解决这 4 项，**不动 13 个 task 已实现的其他逻辑**，纯增量。

---

## 1. 4 项缺口

| ID | 缺口 | 当前 main 状况 | 修复内容 |
|---|---|---|---|
| **A** | `handle_message` 签名漂移 | `(self, user_id: str, request: ChatRequest)` | runner 调用点改传 `user_id="eval_runner"`；session_id 改用 `(user_id, session_id)` 组合 |
| **B** | token 计数缺失 | LLM client 已有 `last_usage_by_call_kind: dict[str, LLMUsage]` | runner 每轮调用前 clear、调用后 sum 所有 `is_authoritative=True` 的 LLMUsage |
| **C** | tool_calls / pipeline 缺失 | events 含 `assistant_state`/`products_start` 等 15+ type | runner 解析 events → `pipeline_stages` 列表 + `tool_calls` 列表 |
| **D** | ARK 连续调用稳定性未验证 | dryrun 仅 13 次调用 | 新增 `--smoke-stress` CLI 模式，单 condition 50 轮，验证不被限流 |

---

## 2. 详细设计

### 2.1 缺口 A：handle_message 签名修复

**当前**（runner.py:354）：
```python
events = await agent.handle_message(request)
```

**修复后**：
```python
events = await agent.handle_message(self._eval_user_id, request)
```

**`_eval_user_id` 设计：**
- `LongSessionRunner.__init__` 增加常量 `self._eval_user_id = f"eval_{stage}_runner"`
- 例：`eval_dryrun_runner` / `eval_pilot_runner` / `eval_full_runner`
- 与生产 anonymous user (`ANONYMOUS_USER_ID`) 完全隔离
- 与 stage × condition cache namespace 一致，evaluation 数据不会污染生产 session_store

**Trace 字段无新增**——`session_id` 字段仍由 runner 控制（`eval_{stage}_c{N}_2026-06-24`）。

**测试**：
- 单测 `test_runner_uses_eval_user_id`：构造 mock agent，验证 `handle_message` 被以 `(user_id, request)` 调用
- 真实 ARK smoke 验证

### 2.2 缺口 B：token 计数抽取

**机制利用：** main 上 `DoubaoLLMClient.last_usage_by_call_kind` 已实现，由 `record_usage()` 在每次真实 ARK 调用后写入。

**关键约束：**
- `LLMClientWithBreaker` 是 wrapper，**不透传** `last_usage_by_call_kind`，必须通过 `.client.last_usage_by_call_kind` 访问
- `FakeLLMClient` 无此属性（evaluation 用真 ARK，理论上不打 fake，但要兜底）

**抽取流程**（在 `_invoke_agent` 内）：

```python
async def _invoke_agent(self, agent, turn: ScriptTurn, session_id: str) -> dict:
    # 1) 清零 usage（取出真正的底层 client）
    real_client = self._unwrap_llm_client(agent.llm_client)
    if hasattr(real_client, "last_usage_by_call_kind"):
        real_client.last_usage_by_call_kind.clear()

    # 2) 调 handle_message（缺口 A 已修）
    request = ChatRequest(type="user_message", session_id=session_id, message=turn.query)
    events = await agent.handle_message(self._eval_user_id, request)

    # 3) 解析 events（缺口 C 在此一起完成）
    parsed = self._parse_events(events)

    # 4) 汇总 token
    usage_records = []
    if hasattr(real_client, "last_usage_by_call_kind"):
        usage_records = list(real_client.last_usage_by_call_kind.values())

    auth_records = [u for u in usage_records if u.is_authoritative]
    prompt_tokens = sum(u.prompt_tokens or 0 for u in auth_records)
    completion_tokens = sum(u.completion_tokens or 0 for u in auth_records)
    ark_call_count = len(usage_records)  # 即使 non-authoritative 也算入

    return {
        **parsed,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "ark_call_count": ark_call_count,
        "usage_records": [u.model_dump() for u in usage_records],
        # ...
    }
```

**`_unwrap_llm_client` 帮助函数**：
```python
@staticmethod
def _unwrap_llm_client(client):
    """剥掉 LLMClientWithBreaker / 任意 wrapper，返回真正的 LLM client。"""
    seen = set()
    while id(client) not in seen:
        seen.add(id(client))
        if hasattr(client, "last_usage_by_call_kind"):
            return client
        inner = getattr(client, "client", None) or getattr(client, "inner", None)
        if inner is None:
            return client
        client = inner
    return client
```

**Trace schema 扩展**：
- `prompt_tokens` / `completion_tokens`：已是 schema required，但现状 0；本次填真实数据
- 新增可选字段 `ark_call_count: int >= 0`、`usage_records: list[dict]`（供答辩报告深度引用）

### 2.3 缺口 C：tool_calls / pipeline 抽取

**事件类型映射规则：**

| event.type | pipeline 阶段 | 计入 tool_calls？ |
|---|---|---|
| `assistant_state` (phase=planning) | `planner` | ✗ |
| `assistant_state` (phase=retrieval) | `retrieval` | ✓ name="retrieval" |
| `assistant_state` (phase=ranking) | `ranker` | ✓ name="ranker" |
| `assistant_state` (phase=answering) | `answer` | ✗ |
| `products_start` | `retrieval` | ✓ name="products_dispatch" |
| `bundle_start` | `bundle_tool` | ✓ name="bundle_tool" |
| `comparison_result` | `comparison_tool` | ✓ name="comparison_tool" |
| `clarification_request` | `clarify_tool` | ✓ name="clarify_tool" |
| `text_delta`（首次） | `answer` | ✗ |
| `done` | — | ✗ |

**规则要点：**
- pipeline 列表按出现顺序、去重相邻重复（连续 5 个 `assistant_state(answering)` 算一个 `answer`）
- tool_calls 中每条带 `{"name": "...", "event_index": int}`，event_index 用于回溯，无 `ms` 字段（events 不带耗时——`total_ms` 仍由 runner wall-clock 测量）
- 不识别的 event type 不计入

**实现：**

```python
def _parse_events(self, events: list[dict]) -> dict:
    answer_parts = []
    retrieved_ids = []
    pipeline = []
    tool_calls = []
    branch_flags = {"memory_hit": None, "fallback": None, "clarify": False}
    first_text_seen = False

    for idx, event in enumerate(events):
        t = event.get("type")
        if t == "text_delta":
            answer_parts.append(event.get("delta", ""))
            if not first_text_seen:
                pipeline.append("answer")
                first_text_seen = True
        elif t == "products_done":
            for card in event.get("products", []) or []:
                pid = card.get("product_id")
                if pid:
                    retrieved_ids.append(pid)
        elif t == "assistant_state":
            phase = event.get("phase") or event.get("label", "").lower()
            stage = {"planning": "planner", "retrieval": "retrieval",
                     "ranking": "ranker", "answering": "answer"}.get(phase)
            if stage and (not pipeline or pipeline[-1] != stage):
                pipeline.append(stage)
            if stage in ("retrieval", "ranker"):
                tool_calls.append({"name": stage, "event_index": idx})
        elif t == "products_start":
            if not pipeline or pipeline[-1] != "retrieval":
                pipeline.append("retrieval")
            tool_calls.append({"name": "products_dispatch", "event_index": idx})
        elif t == "bundle_start":
            pipeline.append("bundle_tool")
            tool_calls.append({"name": "bundle_tool", "event_index": idx})
        elif t == "comparison_result":
            pipeline.append("comparison_tool")
            tool_calls.append({"name": "comparison_tool", "event_index": idx})
        elif t == "clarification_request":
            pipeline.append("clarify_tool")
            tool_calls.append({"name": "clarify_tool", "event_index": idx})
            branch_flags["clarify"] = True
        elif t == "hallucination_corrected":
            branch_flags["fallback"] = "hallucination_check"
    return {
        "answer_text": "".join(answer_parts),
        "retrieved_top_k": retrieved_ids,
        "pipeline": pipeline,
        "tool_calls": tool_calls,
        "branch_flags": branch_flags,
    }
```

**测试：**
- `test_parse_events_planner_retrieval_answer_flow`：构造典型事件流，验证 pipeline 顺序
- `test_parse_events_clarify_branch`：clarify 事件触发 branch_flags
- `test_parse_events_relative_dedupe`：连续相同 stage 去重

### 2.4 缺口 D：ARK 连续调用稳定性 smoke

**目的**：验证 pilot 500 轮里 ARK 不会因连续调用触发限流；如果触发，spec §8 的 2/4/8s 退避 + max_retries=3 能否兜住。

**实施**：
- CLI 新增 `--smoke-stress` flag（与 `--reset-cache`/`--resume`/`--report` 互斥）
- 模式：`--stage dryrun --condition C0 --smoke-stress`，固定跑 **50 轮 phase A**
- 落 trace 到 `data/eval/long_session_2026-06-24/dryrun/stress_trace_C0.jsonl`（与 dryrun 主 trace 隔离）
- 报告：成功率、ARK 错误码分布、retry 触发次数、平均/P99 时延

**通过条件**：
- 0 个 `degradation: "ark_failure_skip"`
- retry 次数 < 10%（即 50 轮里 < 5 次重试）
- P99 时延 < 12s

**不通过则**：暂停 pilot 启动，调查限流原因。

---

## 3. 实施顺序

1. **A**（10 min）：runner 加 `_eval_user_id`，`_invoke_agent` 调用签名修复，run() 主循环传 user_id
2. **B**（30 min）：`_unwrap_llm_client` 帮助函数 + `_invoke_agent` 内 clear/sum 流程 + trace 新字段
3. **C**（40 min）：`_parse_events` 方法 + 3 个单测
4. **D**（20 min）：CLI 加 `--smoke-stress` + runner 加 stress mode

完成后跑 **复测 dryrun smoke**（5 condition × 2 turns），确认 trace 现在含真实 token / pipeline 数据，更新 spec §10.1 Cost Appendix。

---

## 4. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `_unwrap_llm_client` 进入死循环 | seen set 兜底 |
| stream_response 的 token usage 只在最后一个 chunk | 现有 `record_usage` 已处理（D2 path 验证：参考 main 上 stream_response 实现） |
| event.phase 字段名实际不叫 "phase" | 实施时打印一次真实 event，按真名映射；本 spec 给出的 mapping 是 best-guess |
| eval_runner user_id 与生产 user_profile_store 隔离不严 | session_store 已用 (user_id, session_id) tuple，eval_runner 这个 user_id 在生产里不可能出现 |
| `--smoke-stress` 跑超 50 轮 ARK 不限流但跑超 100 轮限流 | smoke 只是早期信号；pilot 500 轮真打到限流时 retry 协议接管 |

---

## 5. 验收 Gate

完成后必须满足：

1. 所有 4 项缺口修复 commit 落地
2. dryrun 复测：5 condition × 2 turns，全部 trace 含真实 `prompt_tokens > 0`、`pipeline` 非空、`ark_call_count > 0`
3. `--smoke-stress` 单 condition × 50 轮通过
4. spec `2026-06-24-long-session-eval-design.md` §10.1 Cost Appendix 用真实数据更新（含 token / 每轮 ARK 调用数）
5. 现有 56 个 long_session 测试 + 151 个核心测试不 fail
6. 增量新增测试至少 5 个（_parse_events × 3 + _unwrap_llm_client + token sum）

放行 pilot 启动需要 user-approved 上述 6 条 + 看完更新后的 Cost Appendix。

---

## 6. 不在本范围

- pilot 100 轮 × 5 condition 实际执行（属于 Stage 2 范围）
- judge 自适应折叠规则的调整（dryrun 阶段未触发 judge 采样，pilot 才需要）
- 报告 PNG 数从 3 张增加到 8 张（spec §11 完整产物清单）—— Task 11 实现保留接口，pilot 后再补全
- 任何 spec §7 trace schema 字段以外的新增（仅扩展 nullable 可选字段）

**本 spec 在 user-approved 前不进入实现阶段。**
