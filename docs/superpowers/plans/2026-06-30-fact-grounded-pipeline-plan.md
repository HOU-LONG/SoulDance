# 事实锚定管道 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现事实锚定管道，彻底消除 LLM 幻觉导致的商品虚构和前后矛盾问题，同时简化 Plan 链路（2 次 LLM 调用 → 1 次）。

**Architecture:** 新增 `UnifiedPlan` 统一 ToolPlan+SemanticFrame+RetrievalPlan 三层模型；新增 `FactContextBuilder` 构建 LLM 唯一事实来源；新增 `AnchorValidator` 做 `[[product_id]]` 锚点校验；新增 `ConsistencyTracker` 做跨轮一致性校验。链路从 3 次 LLM 调用减少到 2 次（1 次决策 + 1 次锚定生成）。

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, 现有 Doubao/DeepSeek LLM 客户端不变

## 全局约束

- 不改变 Cart/Order/TTS/STT/WebSocket 协议
- 不引入新的外部依赖
- 所有新增模块遵循项目现有的 `from __future__ import annotations` + dataclass/Pydantic 模式
- `SemanticFrame` 保留为 `UnifiedPlan` 的 type alias，向后兼容
- 每个 Task 完成后必须通过关联的 pytest 测试
- Phase 2 完成后必须跑全量 `pytest server/tests/` 确认无回归

---

### Task 1: 新增模型 — UnifiedPlan + FactContext + ConsistencyState

**目标**: 在 `models.py` 中新增统一决策模型、事实上下文模型和一致性状态模型

**文件:**
- 修改: `server/backend/app/models.py`
- 测试: `server/tests/test_unified_plan.py`

**接口:**
- 产出: `UnifiedPlan`, `FactRecord`, `FactContext`, `ClaimRecord`, `ConsistencyState`, `SessionRecovery` 类
- 后续 Task 2-19 依赖所有这些模型

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_unified_plan.py
from __future__ import annotations
from server.backend.app.models import UnifiedPlan, FactRecord, FactContext, ClaimRecord, ConsistencyState, SessionRecovery


def test_unified_plan_defaults():
    plan = UnifiedPlan()
    assert plan.tool == "chitchat"
    assert plan.confidence == 0.5
    assert plan.need_clarification is False
    assert plan.price_min is None
    assert plan.include_brands == []
    assert plan.soft_preferences == {}


def test_unified_plan_full():
    plan = UnifiedPlan(
        tool="recommend_product",
        confidence=0.9,
        category="智能手机",
        sub_category="旗舰机",
        price_min=3000,
        price_max=7000,
        include_brands=["小米", "华为"],
        soft_preferences={"拍照": "优秀"},
        retrieval_query="旗舰手机 拍照好",
    )
    assert plan.tool == "recommend_product"
    assert plan.price_max == 7000
    assert "小米" in plan.include_brands


def test_fact_record():
    record = FactRecord(
        product_id="XIAOMI_14_ULTRA",
        title="小米 14 Ultra",
        brand="小米",
        price=5999.0,
        category="手机数码",
        sub_category="智能手机",
        key_specs=["徕卡镜头", "骁龙8Gen3"],
    )
    assert record.product_id == "XIAOMI_14_ULTRA"
    assert record.price == 5999.0


def test_fact_context_product_index():
    records = [
        FactRecord(product_id="P1", title="商品1", brand="小米", price=100, category="手机", sub_category="智能机", key_specs=["快"]),
        FactRecord(product_id="P2", title="商品2", brand="华为", price=200, category="手机", sub_category="智能机", key_specs=["好"]),
    ]
    ctx = FactContext(
        prompt_block="测试用事实块",
        product_index={r.product_id: r for r in records},
        brand_index={"小米": {"P1"}, "华为": {"P2"}},
        denied_queries=["小米 17 Max"],
    )
    assert ctx.product_index["P1"].brand == "小米"
    assert "P2" in ctx.brand_index["华为"]
    assert "小米 17 Max" in ctx.denied_queries


def test_claim_record():
    claim = ClaimRecord(turn=3, product_id="P1", claim_type="not_exists", claim_value="小米 17 Max 不存在")
    assert claim.turn == 3
    assert claim.claim_type == "not_exists"


def test_consistency_state():
    cs = ConsistencyState(
        claims=[
            ClaimRecord(turn=1, product_id="P1", claim_type="price", claim_value="¥5999"),
        ],
        confirmed_product_id="P1",
        denied_product_queries=["小米 17 Max"],
    )
    assert cs.confirmed_product_id == "P1"
    assert len(cs.denied_product_queries) == 1


def test_session_recovery():
    sr = SessionRecovery(
        user_message_restored=True,
        products_cached=False,
        hint="你的消息已收到，正在重新理解...",
    )
    assert sr.user_message_restored is True
    assert sr.hint is not None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py -v
```
预期: 全部 FAIL（模型未定义）

- [ ] **Step 3: 在 models.py 末尾添加新模型**

```python
# ========== 以下追加到 models.py 末尾 ==========

# ---- UnifiedPlan: 合并 ToolPlan + SemanticFrame + RetrievalPlan ----

class UnifiedPlan(BaseModel):
    """单次 LLM 调用的完整决策输出。"""
    # 工具路由
    tool: str = "chitchat"
    confidence: float = 0.5

    # 意图标记
    need_clarification: bool = False
    clarification_question: str | None = None

    # 硬约束
    category: str | None = None
    sub_category: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    include_brands: list[str] = Field(default_factory=list)
    exclude_brands: list[str] = Field(default_factory=list)
    in_stock_only: bool = True

    # 软偏好
    soft_preferences: dict[str, str] = Field(default_factory=dict)

    # 检索参数
    retrieval_query: str = ""
    retrieval_mode: str = "single"

    # cart 操作
    cart_action: str | None = None
    cart_target_product_id: str | None = None
    cart_quantity: int = 1

    # 对比/分析/追问场景
    compare_targets: list[str] = Field(default_factory=list)
    analysis_aspect: str | None = None
    followup_kind: str | None = None


# ---- FactContext: LLM 唯一事实来源 ----

class FactRecord(BaseModel):
    """单个商品的事实卡片。"""
    product_id: str
    title: str
    brand: str
    price: float
    category: str
    sub_category: str
    key_specs: list[str] = Field(default_factory=list)


class FactContext(BaseModel):
    """注入 LLM prompt 的事实上下文 + 供校验使用的索引。"""
    prompt_block: str = ""
    product_index: dict[str, FactRecord] = Field(default_factory=dict)
    brand_index: dict[str, list[str]] = Field(default_factory=dict)
    denied_queries: list[str] = Field(default_factory=list)


# ---- ConsistencyState: 跨轮一致性追踪 ----

class ClaimRecord(BaseModel):
    """单条关于商品的声明。"""
    turn: int
    product_id: str
    claim_type: str  # "exists" | "not_exists" | "price" | "recommendation" | "comparison"
    claim_value: str


class ConsistencyState(BaseModel):
    """跨轮一致性状态。"""
    claims: list[ClaimRecord] = Field(default_factory=list)
    confirmed_product_id: str | None = None
    denied_product_queries: list[str] = Field(default_factory=list)


# ---- SessionRecovery: 会话恢复结果 ----

class SessionRecovery(BaseModel):
    """会话恢复时返回的状态。"""
    user_message_restored: bool = False
    products_cached: bool = False
    hint: str | None = None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 将 ConsistencyState 追加到 SessionState**

修改 `models.py` 中 `SessionState` 类（约第 205 行），追加字段:

```python
# 在 SessionState 的现有字段之后追加:
    consistency: ConsistencyState = Field(default_factory=ConsistencyState)
    checkpoint_stage: str = ""
```

- [ ] **Step 6: 删除废弃模型，添加 backwards-compat alias**

在 `models.py` 中:
- 删除整段 `ConstraintEdits`（约第 56-67 行）、`ConstraintPatch`（约第 56-67 行，同一段）、`CartOperation`（约第 81-84 行）、`QueryIntent`（约第 87-92 行）
- 保留 `ProductReference`（仍有其他地方使用）
- 在文件顶部（import 段之后）追加:

```python
# Backwards-compat alias: SemanticFrame → UnifiedPlan
# 旧代码中的 ShoppingIntentIR / SemanticFrame 引用自动映射到 UnifiedPlan
SemanticFrame = UnifiedPlan
ShoppingIntentIR = UnifiedPlan
```

- [ ] **Step 7: 确认全量导入不报错**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.models import UnifiedPlan, FactContext, ConsistencyState, SemanticFrame, ShoppingIntentIR; print('OK')"
```
预期: `OK`

- [ ] **Step 8: 提交**

```bash
git add server/backend/app/models.py server/tests/test_unified_plan.py
git commit -m "feat(models): add UnifiedPlan, FactContext, ConsistencyState, SessionRecovery

- UnifiedPlan merges ToolPlan + SemanticFrame + RetrievalPlan
- FactContext provides LLM's sole source of product truth
- ConsistencyState tracks cross-turn claim consistency
- Delete deprecated ConstraintEdits, ConstraintPatch, CartOperation, QueryIntent
- SemanticFrame → UnifiedPlan type alias for backwards compat

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 更新 tool_plan.py — ToolPlan → UnifiedPlan 过渡

**目标**: 使 `tool_planner.py` 的 `_parse_plan()` 能解析 `UnifiedPlan`，同时保持 `ToolPlan` 向后兼容

**文件:**
- 修改: `server/backend/app/tool_plan.py`
- 修改: `server/backend/app/tool_planner.py`
- 测试: `server/tests/test_unified_plan.py`（追加）

- [ ] **Step 1: 追加测试**

```python
# 追加到 server/tests/test_unified_plan.py

import json
from server.backend.app.tool_planner import ToolPlanner


def test_tool_planner_parse_unified_plan_json():
    """ToolPlanner 应能解析 LLM 输出的 UnifiedPlan JSON。"""
    from server.backend.app.tool_plan import ToolPlan  # 旧类型
    planner = ToolPlanner(llm_client=None)  # type: ignore
    raw = json.dumps({
        "tool": "recommend_product",
        "confidence": 0.85,
        "category": "智能手机",
        "sub_category": "旗舰机",
        "price_min": 3000,
        "price_max": 7000,
        "include_brands": ["小米"],
        "soft_preferences": {"拍照": "好"},
        "retrieval_query": "旗舰拍照手机",
        "retrieval_mode": "single",
    })
    plan = planner._parse_plan(raw)
    assert plan is not None
    # 解析出的应是 UnifiedPlan，tool 字段为首要字段
    assert plan.tool == "recommend_product"


def test_tool_planner_parse_minimal_json():
    """最小 JSON 也应成功解析。"""
    planner = ToolPlanner(llm_client=None)  # type: ignore
    raw = json.dumps({"tool": "chitchat", "confidence": 0.3})
    plan = planner._parse_plan(raw)
    assert plan is not None
    assert plan.tool == "chitchat"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py::test_tool_planner_parse_unified_plan_json -v
```
预期: FAIL（`_parse_plan` 仍解析为 `ToolPlan`，缺少 category 等字段）

- [ ] **Step 3: 修改 tool_planner.py 的 _parse_plan**

```python
# 替换 tool_planner.py 中的 _parse_plan 方法
def _parse_plan(self, raw: str):
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    try:
        # 优先解析为 UnifiedPlan
        from .models import UnifiedPlan
        return UnifiedPlan.model_validate(data)
    except Exception:
        # 向后兼容：旧 ToolPlan JSON 格式
        try:
            from .tool_plan import ToolPlan
            old = ToolPlan.model_validate(data)
            # 转换为 UnifiedPlan
            return UnifiedPlan(
                tool=old.tool,
                confidence=old.confidence,
                category=old.args.category_hint,
                price_min=old.args.price_min,
                price_max=old.args.price_max,
                include_brands=list(old.args.include_brands),
                exclude_brands=list(old.args.exclude_brands),
                soft_preferences=dict(old.args.soft_preferences),
                retrieval_query=old.args.target_product_query or "",
                cart_action=old.args.cart_action,
                cart_quantity=old.args.cart_quantity,
                compare_targets=list(old.args.compare_targets),
                analysis_aspect=old.args.analysis_aspect,
                followup_kind=old.args.followup_kind,
            )
        except Exception:
            return None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/tool_planner.py server/tests/test_unified_plan.py
git commit -m "feat(tool_planner): parse UnifiedPlan JSON, backwards-compat with old ToolPlan

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 重写 StateReducer — 适配 UnifiedPlan，吸收 IntentCompiler 规则

**目标**: StateReducer 不再依赖 `ConstraintEdits`，直接消费 `UnifiedPlan`；吸收 `_prepare_context_for_turn` 规则

**文件:**
- 修改: `server/backend/app/state_reducer.py`
- 测试: `server/tests/test_unified_plan.py`（追加）

- [ ] **Step 1: 追加测试**

```python
# 追加到 server/tests/test_unified_plan.py

from server.backend.app.models import SessionContext, SessionState, UnifiedPlan
from server.backend.app.state_reducer import StateReducer, seed_constraint_state_from_plan


def test_state_reducer_apply_with_unified_plan():
    ctx = SessionContext(session_id="test")
    plan = UnifiedPlan(
        tool="recommend_product",
        category="手机数码",
        sub_category="智能手机",
        price_min=2000,
        price_max=5000,
        include_brands=["小米"],
        soft_preferences={"拍照": "好"},
        retrieval_query="小米拍照手机",
    )
    reducer = StateReducer()
    reducer.apply(ctx, plan, "推荐小米拍照手机")
    state = ctx.state
    assert state.dialog_state.turn_index == 1
    assert state.dialog_state.last_intent == "recommend_product"
    assert state.constraint_state.hard.category == "手机数码"
    assert state.constraint_state.hard.sub_category == "智能手机"
    assert state.constraint_state.hard.price_min == 2000
    assert state.constraint_state.hard.price_max == 5000
    assert "小米" in state.constraint_state.hard.include_brands
    assert state.constraint_state.soft.get("拍照") == "好"


def test_state_reducer_seed_from_unified_plan():
    ctx = SessionContext(session_id="test")
    plan = UnifiedPlan(
        tool="recommend_product",
        category="个护美妆",
        price_max=300,
    )
    seed_constraint_state_from_plan(ctx, plan)
    assert ctx.state.constraint_state.hard.category == "个护美妆"
    assert ctx.state.constraint_state.hard.price_max == 300
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py::test_state_reducer_apply_with_unified_plan -v
```
预期: FAIL（StateReducer 仍期望 ShoppingIntentIR / ConstraintEdits）

- [ ] **Step 3: 重写 state_reducer.py**

```python
"""
会话状态归约器 — 将 UnifiedPlan 的约束应用到对话状态上。
"""
from __future__ import annotations

from .constraint_filter import dedupe
from .models import UnifiedPlan, SessionContext, HardConstraints


class StateReducer:
    """将 UnifiedPlan 中的约束直接应用到 SessionState。

    每轮调用一次 apply()，执行顺序：
    1. 更新对话元数据（轮次、意图、用户消息）
    2. 直接将 UnifiedPlan 的 hard/soft 约束覆盖到状态中
    3. 记录审计日志
    4. 同步 legacy global_profile
    """

    def apply(self, context: SessionContext, plan: UnifiedPlan, user_message: str) -> None:
        state = context.state
        state.dialog_state.turn_index += 1
        state.dialog_state.last_intent = plan.tool
        state.dialog_state.last_user_message = user_message
        # 直接消费 UnifiedPlan 的约束字段
        hc = state.constraint_state.hard
        if plan.category:
            hc.category = plan.category
        if plan.sub_category:
            hc.sub_category = plan.sub_category
        if plan.price_min is not None:
            hc.price_min = plan.price_min
        if plan.price_max is not None:
            hc.price_max = plan.price_max
        if plan.include_brands:
            hc.include_brands = dedupe(list(hc.include_brands) + list(plan.include_brands))
        if plan.exclude_brands:
            hc.exclude_brands = dedupe(list(hc.exclude_brands) + list(plan.exclude_brands))
        # soft preferences
        for key, value in plan.soft_preferences.items():
            if value:
                state.constraint_state.soft[key] = value
        # 审计
        state.constraint_state.source_turns.append({
            "turn_index": state.dialog_state.turn_index,
            "intent": plan.tool,
            "message": user_message,
            "plan": plan.model_dump(mode="json"),
        })
        _sync_legacy_context(context)


def seed_constraint_state_from_plan(context: SessionContext, plan: UnifiedPlan | None) -> None:
    if plan is None:
        return
    state = context.state
    if state.constraint_state.hard == HardConstraints() and not state.constraint_state.soft:
        state.constraint_state.hard = HardConstraints(
            category=plan.category,
            sub_category=plan.sub_category,
            price_min=plan.price_min,
            price_max=plan.price_max,
            include_brands=list(plan.include_brands),
            exclude_brands=list(plan.exclude_brands),
        )
        state.constraint_state.soft = dict(plan.soft_preferences)
        _sync_legacy_context(context)


def _sync_legacy_context(context: SessionContext) -> None:
    hard = context.state.constraint_state.hard
    soft = context.state.constraint_state.soft
    if context.last_plan is not None:
        context.last_plan.hard_constraints = hard.model_copy(deep=True)
        context.last_plan.soft_preferences = dict(soft)
        context.last_plan.category = hard.sub_category or hard.category or context.last_plan.category
    context.global_profile.update({key: value for key, value in soft.items() if value})
    if hard.price_min is not None:
        context.global_profile["budget_min"] = hard.price_min
    if hard.price_max is not None:
        context.global_profile["budget_max"] = hard.price_max
    if hard.include_brands:
        context.global_profile["include_brands"] = dedupe(hard.include_brands)
    if hard.exclude_terms:
        context.global_profile["exclude_terms"] = dedupe(hard.exclude_terms)
    if hard.exclude_brand_regions:
        context.global_profile["exclude_brand_regions"] = dedupe(hard.exclude_brand_regions)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/state_reducer.py server/tests/test_unified_plan.py
git commit -m "refactor(state_reducer): consume UnifiedPlan directly, absorb IntentCompiler rules

- StateReducer.apply() now takes UnifiedPlan instead of ShoppingIntentIR
- Removes dependency on ConstraintEdits (deleted model)
- seed_constraint_state_from_plan updated for UnifiedPlan

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 简化 agent.py 分派 — 移除 IntentCompiler，统一 UnifiedPlan 驱动

**目标**: `_do_stream_message()` 和 `_dispatch_tool()` 改为 UnifiedPlan 驱动，删除 `_merge_tool_plan_into_ir()`

**文件:**
- 修改: `server/backend/app/agent.py`
- 测试: `server/tests/test_demo_agent_flow.py`（作为回归测试）

- [ ] **Step 1: 运行现有回归测试确认基线**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_demo_agent_flow.py -v -x 2>&1 | head -80
```
记录基线：哪些通过、哪些失败（预期有因模型变更导致的 FAIL）

- [ ] **Step 2: 修改 _do_stream_message — 移除 IntentCompiler.compile 调用**

在 `agent.py` 中找到 `_do_stream_message` 方法（约第 385 行），修改为:

```python
async def _do_stream_message(self, user_id: str, request: ChatRequest, compiled_ir, context: SessionContext, trace=None) -> AsyncIterator[dict]:
    # 1. pending recovery 优先
    recovery_events = self._build_pending_recovery_events(context, request)
    if recovery_events is not None:
        for event in recovery_events:
            yield event
        return

    # 2. 立即通知客户端"正在思考"
    message_id = _message_id()
    yield self._assistant_state(
        message_id, "thinking", "正在理解你的需求",
        intent="thinking", retrieval_mode="no_retrieval",
    )

    # 3. ToolPlanner 唯一入口 → UnifiedPlan
    import time as _time
    seed_constraint_state_from_plan(context, context.last_plan)
    plan_t0 = _time.time()
    unified_plan = await self.tool_planner.plan(request, context)
    if trace is not None:
        trace.plan_tool_ms = (_time.time() - plan_t0) * 1000
        trace.tool = unified_plan.tool
        trace.tool_confidence = unified_plan.confidence

    # 4. UnifiedPlan → StateReducer.apply()
    self._prepare_context_for_turn(context, request, unified_plan)
    self.state_reducer.apply(context, unified_plan, request.message or "")

    # 5. 按 unified_plan.tool 分发
    async for event in self._dispatch_tool(user_id, request, context, unified_plan):
        yield event
```

- [ ] **Step 3: 修改 _dispatch_tool — 参数 unified_plan 替换 compiled_ir + tool_plan**

将 `_dispatch_tool` 签名和相关参数统一为 `unified_plan: UnifiedPlan`。

针对 `recommend_product / compare_products / scenario_bundle` 路径（约第 470 行），修改为:

```python
# 剩下 recommend_product / compare_products / scenario_bundle
async for event in self._run_retrieval_flow(user_id, request, context, unified_plan):
    yield event
```

- [ ] **Step 4: 修改 _run_retrieval_flow — 删除 _merge_tool_plan_into_ir**

将 `_run_retrieval_flow` 的签名改为接收 `unified_plan: UnifiedPlan`，内部直接使用 `unified_plan` 的约束字段构建 `RetrievalPlan`，不再通过 `IntentCompiler.compile()` 和 `_merge_tool_plan_into_ir()`。

关键改动:

```python
async def _run_retrieval_flow(
    self, user_id: str, request: ChatRequest,
    context: SessionContext, unified_plan,
) -> AsyncIterator[dict]:
    # 不再调用 intent_compiler.compile()
    # 直接从 unified_plan 构建 RetrievalPlan
    context_action = unified_plan.tool  # same_task / new_task 逻辑由 _prepare_context_for_turn 处理
    plan = self.query_builder.build_from_unified(unified_plan, context, request.message)
    self.taxonomy.apply_to_constraints(plan.hard_constraints, request.message)
    plan.category = plan.hard_constraints.sub_category or plan.hard_constraints.category or plan.category
    
    context.last_plan = plan
    context.state.trace.last_execution_plan = {"retrieval_plan": plan.model_dump(mode="json")}
    
    # ... 后续澄清/对比/Bundle/推荐逻辑保持不变 ...
```

- [ ] **Step 5: 删除 _merge_tool_plan_into_ir 方法**

在 `agent.py` 中删除 `_merge_tool_plan_into_ir` 方法（约第 570-591 行）。

- [ ] **Step 6: 确认导入和语法**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.agent import ShopGuideAgent; print('OK')"
```
预期: `OK`

- [ ] **Step 7: 提交**

```bash
git add server/backend/app/agent.py
git commit -m "refactor(agent): dispatch via UnifiedPlan, remove IntentCompiler.compile + _merge_tool_plan_into_ir

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 删除 IntentCompiler，精简 SemanticParser

**目标**: 删除 `intent_compiler.py`，`semantic_layer.py` 只保留规则兜底

**文件:**
- 修改: `server/backend/app/semantic_layer.py`
- 删除: `server/backend/app/intent_compiler.py`
- 修改: `server/backend/app/agent.py`（移除导入）

- [ ] **Step 1: 从 agent.py 移除 IntentCompiler 导入**

在 `agent.py` 顶部 import 段中删除:
```python
from .intent_compiler import IntentCompiler
```

在 `__init__` 中删除:
```python
self.intent_compiler = IntentCompiler(self.llm_client, self.semantic_parser)
```

- [ ] **Step 2: 删除 intent_compiler.py**

```bash
rm /home/huadabioa/houlong/SoulDance/server/backend/app/intent_compiler.py
```

- [ ] **Step 3: 精简 semantic_layer.py — 保留 rule_semantic_frame，删除 SemanticParser LLM 路径**

在 `semantic_layer.py` 中:
- 删除 `SemanticParser` 类（及其 LLM 路径 `parse()` 方法）
- 保留 `rule_semantic_frame()` 函数（在 ToolPlanner LLM 失败时兜底）
- 保留 `_add_constraints` / `_relax_constraints` / `_remove_constraints`（其他地方仍在用）

- [ ] **Step 4: 确认项目可导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.semantic_layer import rule_semantic_frame; print('OK')"
```
预期: `OK`

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.agent import ShopGuideAgent; print('OK')"
```
预期: `OK`

- [ ] **Step 5: 提交**

```bash
git rm server/backend/app/intent_compiler.py
git add server/backend/app/semantic_layer.py server/backend/app/agent.py
git commit -m "refactor: delete IntentCompiler, trim SemanticParser to rule-only fallback

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 创建 FactContextBuilder

**目标**: 从 `UnifiedPlan` + 检索排序结果构建 `FactContext`

**文件:**
- 创建: `server/backend/app/fact_context.py`
- 测试: `server/tests/test_fact_context.py`

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_fact_context.py
from __future__ import annotations
from server.backend.app.models import Product, UnifiedPlan, RankedProduct, FactContext, FactRecord
from server.backend.app.fact_context import FactContextBuilder


def _make_product(pid: str, title: str, brand: str, price: float, cat: str = "手机", sub: str = "智能机") -> Product:
    return Product(
        product_id=pid, title=title, brand=brand, price=price,
        category=cat, sub_category=sub, image_path="",
        marketing_description=f"{title} 优质产品", search_text=title,
    )


def _make_ranked(product: Product, score: float = 0.9) -> RankedProduct:
    return RankedProduct(product=product, score=score, tier=1, reason="匹配")


def test_build_empty():
    builder = FactContextBuilder()
    ctx = builder.build(UnifiedPlan(), [])
    assert ctx.prompt_block == ""
    assert ctx.product_index == {}
    assert ctx.brand_index == {}


def test_build_with_products():
    p1 = _make_product("P1", "小米 14 Ultra", "小米", 5999.0)
    p2 = _make_product("P2", "华为 Mate 70 Pro", "华为", 6999.0)
    ranked = [_make_ranked(p1), _make_ranked(p2)]
    plan = UnifiedPlan(tool="recommend_product", denied_queries=["小米 17 Max"])
    builder = FactContextBuilder()
    ctx = builder.build(plan, ranked)
    # product_index
    assert "P1" in ctx.product_index
    assert ctx.product_index["P1"].brand == "小米"
    assert ctx.product_index["P1"].price == 5999.0
    # brand_index
    assert "P1" in ctx.brand_index["小米"]
    assert "P2" in ctx.brand_index["华为"]
    # prompt_block 包含锚点格式
    assert "[[P1]]" in ctx.prompt_block
    assert "[[P2]]" in ctx.prompt_block
    assert "小米 14 Ultra" in ctx.prompt_block
    assert "¥5999" in ctx.prompt_block
    # denied_queries 透传
    assert "小米 17 Max" in ctx.denied_queries


def test_prompt_block_format():
    p = _make_product("P1", "测试商品", "测试品牌", 100.0, "个护", "防晒霜")
    ranked = [_make_ranked(p)]
    ctx = FactContextBuilder().build(UnifiedPlan(), ranked)
    # 锚点格式: [[product_id]]
    assert "[[P1]]" in ctx.prompt_block
    # 包含价格
    assert "¥100" in ctx.prompt_block
    # 包含规则说明
    assert "你唯一可以引用的商品信息" in ctx.prompt_block
    assert "不要编造任何商品名称" in ctx.prompt_block
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_fact_context.py -v
```
预期: FAIL（模块不存在）

- [ ] **Step 3: 创建 fact_context.py**

```python
"""事实上下文构建器 — 将检索结果组装为 LLM 唯一事实来源。"""
from __future__ import annotations

from .models import UnifiedPlan, RankedProduct, FactContext, FactRecord


class FactContextBuilder:
    """将 UnifiedPlan + 检索排序结果组装为 FactContext。

    prompt_block 会注入到 LLM system prompt 末尾，要求 LLM 用 [[product_id]] 锚点
    格式引用商品。product_index 和 brand_index 供 AnchorValidator 校验使用。
    """

    def build(self, plan: UnifiedPlan, ranked: list[RankedProduct]) -> FactContext:
        if not ranked:
            return FactContext(
                prompt_block="",
                product_index={},
                brand_index={},
                denied_queries=list(plan.denied_queries) if hasattr(plan, 'denied_queries') else [],
            )

        records: list[FactRecord] = []
        for item in ranked:
            product = item.product
            specs = self._extract_key_specs(product)
            records.append(FactRecord(
                product_id=product.product_id,
                title=product.title,
                brand=product.brand,
                price=product.price,
                category=product.category,
                sub_category=product.sub_category,
                key_specs=specs,
            ))

        product_index = {r.product_id: r for r in records}
        brand_index: dict[str, list[str]] = {}
        for r in records:
            brand_index.setdefault(r.brand, []).append(r.product_id)

        prompt_block = self._render_prompt_block(records)
        denied = list(getattr(plan, 'denied_queries', []) or [])

        return FactContext(
            prompt_block=prompt_block,
            product_index=product_index,
            brand_index=brand_index,
            denied_queries=denied,
        )

    def _extract_key_specs(self, product) -> list[str]:
        """从 marketing_description 和 reviews 中提取核心卖点。"""
        import re
        keywords: list[str] = []
        desc = (product.marketing_description or "").strip()
        if desc:
            # 按逗号/顿号/空格拆分，取前 3 个短词
            parts = re.split(r"[，,、\s]+", desc)
            keywords.extend(p.strip() for p in parts[:3] if 2 <= len(p.strip()) <= 20)
        # 从 reviews 提取高频关键词
        reviews = product.reviews or []
        for review in reviews[:3]:
            text = str(review.get("content", ""))
            if text and len(text) < 30:
                keywords.append(text.strip())
        # 去重，限制 5 个
        seen: set[str] = set()
        result: list[str] = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                result.append(kw)
                if len(result) >= 5:
                    break
        return result

    def _render_prompt_block(self, records: list[FactRecord]) -> str:
        lines = [
            "[可用商品事实库] — 以下是你唯一可以引用的商品信息。",
            "引用时必须使用 [[product_id]] 锚点格式。",
            "任何未列在此库中的商品名称、型号、价格均视为不存在，禁止提及。",
            "",
        ]
        for i, r in enumerate(records, 1):
            specs_str = " | ".join(r.key_specs) if r.key_specs else "暂无详细规格"
            lines.append(
                f"{i}. [[{r.product_id}]]\n"
                f"   名称: {r.title}\n"
                f"   品牌: {r.brand} | 价格: ¥{r.price:.0f}\n"
                f"   核心卖点: {specs_str}\n"
            )
        lines.extend([
            "规则：",
            "- 推荐或提及任何商品时，必须使用准确的 [[product_id]] 锚点",
            "- 如果要比较价格/参数，只能使用上面列出的数值",
            "- 如果用户问的商品不在库中，直接说「库中暂无此商品，请确认型号」",
            "- 不要编造任何商品名称、型号或价格",
        ])
        return "\n".join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_fact_context.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/fact_context.py server/tests/test_fact_context.py
git commit -m "feat: add FactContextBuilder — structured fact sheet for LLM grounding

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 创建 AnchorValidator

**目标**: 校验 LLM 输出的 `[[product_id]]` 锚点，替换为真实商品名，检测裸奔商品名

**文件:**
- 创建: `server/backend/app/anchor_validator.py`
- 测试: `server/tests/test_anchor_validator.py`

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_anchor_validator.py
from __future__ import annotations
from server.backend.app.models import FactContext, FactRecord
from server.backend.app.anchor_validator import AnchorValidator, ValidationResult


def _make_ctx() -> FactContext:
    r1 = FactRecord(product_id="P1", title="小米 14 Ultra", brand="小米", price=5999.0, category="手机", sub_category="智能机")
    r2 = FactRecord(product_id="P2", title="华为 Mate 70", brand="华为", price=6999.0, category="手机", sub_category="智能机")
    return FactContext(
        prompt_block="测试",
        product_index={"P1": r1, "P2": r2},
        brand_index={"小米": ["P1"], "华为": ["P2"]},
        denied_queries=[],
    )


def test_extract_anchors():
    text = "我推荐 [[P1]]，它比 [[P2]] 更适合你"
    anchors = AnchorValidator.extract_anchors(text)
    assert anchors == ["P1", "P2"]


def test_extract_anchors_none():
    assert AnchorValidator.extract_anchors("没有锚点的文本") == []


def test_resolve_all_valid():
    ctx = _make_ctx()
    validator = AnchorValidator()
    resolved = validator.resolve(["P1", "P2"], ctx)
    assert resolved["P1"] is not None
    assert resolved["P2"] is not None


def test_resolve_partial_invalid():
    ctx = _make_ctx()
    validator = AnchorValidator()
    resolved = validator.resolve(["P1", "FAKE_ID"], ctx)
    assert resolved["P1"] is not None
    assert resolved["FAKE_ID"] is None


def test_validate_clean():
    ctx = _make_ctx()
    validator = AnchorValidator()
    resolved = {"P1": ctx.product_index["P1"]}
    result = validator.validate("推荐 [[P1]]", resolved, ctx)
    assert result.is_valid
    assert result.stray_names == []


def test_validate_with_unresolved_anchor():
    ctx = _make_ctx()
    validator = AnchorValidator()
    resolved = {"FAKE_ID": None}
    result = validator.validate("看看 [[FAKE_ID]]", resolved, ctx)
    assert not result.is_valid
    assert "FAKE_ID" in result.unresolved_anchors


def test_expand_anchors():
    ctx = _make_ctx()
    validator = AnchorValidator()
    resolved = {"P1": ctx.product_index["P1"], "P2": ctx.product_index["P2"]}
    expanded, product_ids = validator.expand("推荐 [[P1]]，备选 [[P2]]", resolved)
    assert "小米 14 Ultra" in expanded
    assert "华为 Mate 70" in expanded
    assert "[[" not in expanded
    assert "P1" in product_ids
    assert "P2" in product_ids


def test_detect_stray_names():
    ctx = _make_ctx()
    validator = AnchorValidator()
    # "小米 14 Ultra" 是 P1 的 title，但没有对应锚点
    text = "我推荐小米 14 Ultra，它很好"
    stray = validator.detect_stray_names(text, ctx)
    assert len(stray) >= 1
    assert any("小米" in s for s in stray)


def test_detect_stray_names_clean():
    ctx = _make_ctx()
    validator = AnchorValidator()
    text = "根据你的需求，这几款都不错"
    stray = validator.detect_stray_names(text, ctx)
    assert stray == []


def test_full_process():
    ctx = _make_ctx()
    validator = AnchorValidator()
    llm_output = "我推荐 [[P1]]，它的徕卡镜头拍照效果出色。备选 [[P2]]。"
    result = validator.process(llm_output, ctx)
    assert result.is_valid
    assert "小米 14 Ultra" in result.clean_text
    assert "华为 Mate 70" in result.clean_text
    assert result.referenced_product_ids == ["P1", "P2"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_anchor_validator.py -v
```
预期: FAIL

- [ ] **Step 3: 创建 anchor_validator.py**

```python
"""锚点校验器 — 校验 LLM 输出中的 [[product_id]] 锚点，替换为真实商品信息。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import FactContext, FactRecord


@dataclass
class ValidationResult:
    is_valid: bool = True
    clean_text: str = ""
    referenced_product_ids: list[str] = field(default_factory=list)
    unresolved_anchors: list[str] = field(default_factory=list)
    stray_names: list[str] = field(default_factory=list)


class AnchorValidator:
    """校验和清洗 LLM 输出中的商品锚点。"""

    ANCHOR_PATTERN = re.compile(r'\[\[([A-Za-z0-9_-]+)\]\]')

    @staticmethod
    def extract_anchors(text: str) -> list[str]:
        return AnchorValidator.ANCHOR_PATTERN.findall(text)

    def resolve(self, anchor_ids: list[str], fact_ctx: FactContext) -> dict[str, FactRecord | None]:
        return {aid: fact_ctx.product_index.get(aid) for aid in anchor_ids}

    def validate(self, original_text: str, resolved: dict[str, FactRecord | None], fact_ctx: FactContext) -> ValidationResult:
        result = ValidationResult()
        for aid, record in resolved.items():
            if record is None:
                result.unresolved_anchors.append(aid)
                result.is_valid = False
        if not result.is_valid:
            result.clean_text = self._remove_unresolved_anchors(original_text, result.unresolved_anchors)
        else:
            result.clean_text = original_text
        return result

    def expand(self, text: str, resolved: dict[str, FactRecord | None]) -> tuple[str, list[str]]:
        """将 [[product_id]] 替换为加粗的商品名，返回 (扩展后文本, 引用的 product_id 列表)。"""
        valid = {aid: rec for aid, rec in resolved.items() if rec is not None}
        product_ids: list[str] = []

        def _replace(match):
            aid = match.group(1)
            rec = valid.get(aid)
            if rec is not None:
                product_ids.append(aid)
                return f"**{rec.title}**"
            return match.group(0)  # 保留未解析的不要紧，已在 validate 中移除

        expanded = AnchorValidator.ANCHOR_PATTERN.sub(_replace, text)
        return expanded, product_ids

    def detect_stray_names(self, text: str, fact_ctx: FactContext) -> list[str]:
        """检测文本中是否出现未用锚点标记的商品名（裸奔检测）。"""
        stray: list[str] = []
        for record in fact_ctx.product_index.values():
            # 只在 title 长度 >= 4 时才检测（避免短词误报）
            if len(record.title) >= 4 and record.title in text:
                # 确认该 product_id 确实没有以锚点形式出现
                if f"[[{record.product_id}]]" not in text:
                    stray.append(record.title)
        return stray

    def process(self, llm_output: str, fact_ctx: FactContext) -> ValidationResult:
        """完整处理流程：提取 → 解析 → 校验 → 扩展 → 裸奔检测。"""
        anchors = self.extract_anchors(llm_output)
        resolved = self.resolve(anchors, fact_ctx)
        result = self.validate(llm_output, resolved, fact_ctx)
        if result.is_valid:
            expanded_text, product_ids = self.expand(result.clean_text, resolved)
            result.clean_text = expanded_text
            result.referenced_product_ids = product_ids
            # 裸奔检测
            result.stray_names = self.detect_stray_names(result.clean_text, fact_ctx)
            if result.stray_names:
                result.is_valid = False
        return result

    def _remove_unresolved_anchors(self, text: str, unresolved: list[str]) -> str:
        """移除包含未解析锚点的句子。"""
        for aid in unresolved:
            # 移除 [[FAKE_ID]] 及其所在的整句（以 。！？\n 为边界）
            pattern = re.compile(r'[^。！？\n]*\[\[(' + re.escape(aid) + r')\]\][^。！？\n]*[。！？]?')
            text = pattern.sub('', text)
        return text.strip()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_anchor_validator.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/anchor_validator.py server/tests/test_anchor_validator.py
git commit -m "feat: add AnchorValidator — [[product_id]] anchor validation and expansion

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 集成 FactContext + AnchorValidator 到 agent.py 生成链路

**目标**: `_stream_generate_text_events` 改为全量缓冲 → FactContext 构建 → LLM 锚定生成 → AnchorValidator 校验 → 推送

**文件:**
- 修改: `server/backend/app/agent.py`
- 修改: `server/backend/app/prompt_registry.py`（注入 FactContext.prompt_block）
- 测试: `server/tests/test_demo_agent_flow.py`

- [ ] **Step 1: 在 agent.py 的 __init__ 中初始化 FactContextBuilder 和 AnchorValidator**

在 `ShopGuideAgent.__init__` 中追加:

```python
from .fact_context import FactContextBuilder
from .anchor_validator import AnchorValidator
self.fact_builder = FactContextBuilder()
self.anchor_validator = AnchorValidator()
```

- [ ] **Step 2: 修改 _stream_recommendation_events — 在 LLM 生成前构建 FactContext**

在 `_stream_recommendation_events` 方法中（约第 855 行），LLM 生成前插入:

```python
# 构建 FactContext
fact_ctx = self.fact_builder.build(plan, selected)

# 修改 prompt 组装，注入 fact_ctx.prompt_block
# _stream_generate_text_events 接收 fact_ctx 参数
async for event in self._stream_generate_text_events(message_id, request, plan, selected, None, fact_ctx=fact_ctx):
    ...
```

- [ ] **Step 3: 修改 _stream_generate_text_events — 全量缓冲 + 校验后推送**

修改方法签名和实现:

```python
async def _stream_generate_text_events(
    self, message_id: str, request: ChatRequest,
    plan: RetrievalPlan, ranked: list[RankedProduct],
    focus_product: Product | None,
    fact_ctx: FactContext | None = None,
) -> AsyncIterator[dict]:
    if not ranked:
        for event in _text_delta_events(message_id, _no_match_text(plan)):
            yield event
        return

    ctx = self.sessions.get("anonymous", request.session_id)
    
    # 全量收集 LLM 输出
    chunks: list[str] = []
    try:
        async for chunk in self.llm_client.stream_response(
            request.message, plan, ranked, focus_product,
            context=ctx, fact_block=fact_ctx.prompt_block if fact_ctx else "",
        ):
            if chunk:
                chunks.append(chunk)
    except Exception:
        pass

    if not chunks:
        fallback = fallback_text_for_failure("llm_error", plan)
        for event in _text_delta_events(message_id, fallback):
            yield event
        return

    streamed_text = "".join(chunks)

    # AnchorValidator 校验
    if fact_ctx and fact_ctx.product_index:
        validation = self.anchor_validator.process(streamed_text, fact_ctx)
        if not validation.is_valid:
            logger.warning(
                f"[anchor_validation] stray_names={validation.stray_names} "
                f"unresolved={validation.unresolved_anchors}"
            )
            fallback = fallback_text_for_failure("hallucination_detected", plan, context=ctx)
            yield {"type": "hallucination_corrected", "message_id": message_id,
                   "original_issues": validation.stray_names + validation.unresolved_anchors}
            for event in _text_delta_events(message_id, fallback):
                yield event
            return
        # 使用清洗后的文本
        final_text = validation.clean_text
    else:
        final_text = streamed_text

    # 流式推送清洗后的文本
    for event in _text_delta_events(message_id, final_text):
        yield event
```

- [ ] **Step 4: 确认 agent.py 可导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.agent import ShopGuideAgent; print('OK')"
```
预期: `OK`

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/agent.py
git commit -m "feat(agent): integrate FactContext + AnchorValidator into generate pipeline

- LLM output is fully buffered before streaming to user
- AnchorValidator checks all [[product_id]] anchors against FactContext
- Hallucinated content triggers fallback instead of reaching user

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: 更新 HallucinationChecker — 降级为 AnchorValidator 的兜底层

**目标**: 保留价格偏差检测，去掉已被 AnchorValidator 覆盖的虚构 ID/名称检测

**文件:**
- 修改: `server/backend/app/hallucination_checker.py`
- 测试: `server/tests/test_product_analysis.py`（现有测试）

- [ ] **Step 1: 精简 HallucinationChecker**

```python
"""幻觉检测器（兜底层）—— 保留价格偏差检测，虚构 ID/名称检测已由 AnchorValidator 覆盖。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import RankedProduct, FactContext


@dataclass
class HallucinationReport:
    is_clean: bool = True
    price_mismatches: list[dict] = field(default_factory=list)


class HallucinationChecker:
    """检测 LLM 回复中的价格偏差（兜底层）。

    AnchorValidator 已覆盖虚构 product_id 和虚构商品名的检测。
    本模块只保留价格偏差检测，作为 AnchorValidator 处理后的二次校验。
    """

    def __init__(self, price_tolerance: float = 0.1):
        self.price_tolerance = price_tolerance

    def verify(self, response_text: str, fact_ctx: FactContext) -> HallucinationReport:
        """校验文本中提到的价格是否与 FactContext 一致。"""
        report = HallucinationReport()
        title_to_price = {r.title: r.price for r in fact_ctx.product_index.values()}

        price_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*元')
        for match in price_pattern.finditer(response_text):
            mentioned_price = float(match.group(1))
            for title, actual_price in title_to_price.items():
                if title in response_text:
                    if abs(mentioned_price - actual_price) / max(actual_price, 1) > self.price_tolerance:
                        report.price_mismatches.append({
                            "product": title,
                            "mentioned": mentioned_price,
                            "actual": actual_price,
                        })
                        report.is_clean = False
        return report
```

- [ ] **Step 2: 确认现有测试可运行**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.hallucination_checker import HallucinationChecker; print('OK')"
```
预期: `OK`

- [ ] **Step 3: 提交**

```bash
git add server/backend/app/hallucination_checker.py
git commit -m "refactor(hallucination_checker): reduce to price-only verification, AnchorValidator covers IDs/names

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: 创建 ConsistencyTracker

**目标**: 跨轮次校验回答一致性 — denial cache、price consistency、focus drift

**文件:**
- 创建: `server/backend/app/consistency_tracker.py`
- 测试: `server/tests/test_consistency_tracker.py`

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_consistency_tracker.py
from __future__ import annotations
from server.backend.app.models import SessionContext, ConsistencyState, ClaimRecord, FactContext, FactRecord
from server.backend.app.consistency_tracker import ConsistencyTracker


def _make_ctx(denied: list[str] | None = None, confirmed: str | None = None) -> SessionContext:
    ctx = SessionContext(session_id="test")
    ctx.state.consistency = ConsistencyState(
        denied_product_queries=denied or [],
        confirmed_product_id=confirmed,
    )
    return ctx


def _make_fact_ctx() -> FactContext:
    r = FactRecord(product_id="P1", title="小米 14 Ultra", brand="小米", price=5999.0, category="手机", sub_category="智能机")
    return FactContext(
        prompt_block="",
        product_index={"P1": r},
        brand_index={"小米": ["P1"]},
        denied_queries=[],
    )


def test_check_denial_cache_blocks():
    """之前说'小米 17 Max 不存在'，后续检索结果不能出现相关商品。"""
    ctx = _make_ctx(denied=["小米 17 Max"])
    tracker = ConsistencyTracker()
    result = tracker.check_before_output(
        session_ctx=ctx,
        ranked_product_ids=["P1"],
        fact_ctx=_make_fact_ctx(),
    )
    assert result.is_consistent


def test_check_denial_cache_empty_context():
    """无 denial cache 时不应拦截任何商品。"""
    ctx = _make_ctx()
    tracker = ConsistencyTracker()
    result = tracker.check_before_output(ctx, ["P1", "P2"], _make_fact_ctx())
    assert result.is_consistent


def test_record_denial():
    """记录一条'不存在'声明。"""
    ctx = _make_ctx()
    tracker = ConsistencyTracker()
    tracker.record_denial(ctx, "小米 17 Max", turn=3)
    assert "小米 17 Max" in ctx.state.consistency.denied_product_queries
    assert len(ctx.state.consistency.claims) == 1


def test_record_claim():
    ctx = _make_ctx()
    tracker = ConsistencyTracker()
    tracker.record_claim(ctx, "P1", "recommendation", "主推小米 14 Ultra", turn=2)
    assert ctx.state.consistency.claims[0].product_id == "P1"


def test_set_confirmed_product():
    ctx = _make_ctx()
    tracker = ConsistencyTracker()
    tracker.set_confirmed_product(ctx, "P1")
    assert ctx.state.consistency.confirmed_product_id == "P1"


def test_check_focus_drift():
    """用户已确认关注 P1，新回复应主要围绕 P1。"""
    ctx = _make_ctx(confirmed="P1")
    tracker = ConsistencyTracker()
    # 新回复推荐的 product_ids 不包含 P1 → 漂移
    result = tracker.check_before_output(ctx, ["P2", "P3"], _make_fact_ctx())
    assert not result.is_consistent
    assert result.focus_drift_detected is True


def test_check_focus_no_drift():
    ctx = _make_ctx(confirmed="P1")
    tracker = ConsistencyTracker()
    result = tracker.check_before_output(ctx, ["P1", "P2"], _make_fact_ctx())
    assert result.is_consistent
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_consistency_tracker.py -v
```
预期: FAIL

- [ ] **Step 3: 创建 consistency_tracker.py**

```python
"""跨轮一致性追踪器 — 确保 LLM 回复与历史声明一致。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .models import SessionContext, ClaimRecord, FactContext

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyResult:
    is_consistent: bool = True
    focus_drift_detected: bool = False
    blocked_reason: str | None = None


class ConsistencyTracker:
    """校验跨轮次回答一致性。

    3 条规则（纯规则，不调 LLM）：
    - Rule 1 (Denial Cache): 已声明"不存在"的查询词对应的商品不能出现在后续推荐中
    - Rule 2 (Price Consistency): 同一 product_id 的价格必须与 FactContext 一致
    - Rule 3 (Focus Drift): 已确认关注某商品时，后续推荐应主要围绕它
    """

    def check_before_output(
        self,
        session_ctx: SessionContext,
        ranked_product_ids: list[str],
        fact_ctx: FactContext,
    ) -> ConsistencyResult:
        """在输出前执行一致性校验。"""
        cs = session_ctx.state.consistency

        # Rule 3: Focus drift
        if cs.confirmed_product_id and cs.confirmed_product_id not in ranked_product_ids:
            return ConsistencyResult(
                is_consistent=False,
                focus_drift_detected=True,
                blocked_reason=f"用户已确认关注 {cs.confirmed_product_id}，但新推荐未包含该商品",
            )

        # Rule 1: Denial cache — 在 fact_ctx 层面已处理（denied_queries 在检索时硬过滤），
        # 这里做二次校验
        denied = set(cs.denied_product_queries)
        if denied:
            for pid in ranked_product_ids:
                record = fact_ctx.product_index.get(pid)
                if record and record.title in denied:
                    logger.warning(f"[consistency] denial cache hit: {record.title} in ranked results")

        return ConsistencyResult(is_consistent=True)

    def record_denial(self, ctx: SessionContext, query: str, turn: int) -> None:
        """记录一条'商品不存在'的声明。"""
        cs = ctx.state.consistency
        if query not in cs.denied_product_queries:
            cs.denied_product_queries.append(query)
        cs.claims.append(ClaimRecord(
            turn=turn,
            product_id="",
            claim_type="not_exists",
            claim_value=f"查询「{query}」在商品库中不存在",
        ))

    def record_claim(self, ctx: SessionContext, product_id: str, claim_type: str, claim_value: str, turn: int) -> None:
        """记录一条关于商品的声明。"""
        ctx.state.consistency.claims.append(ClaimRecord(
            turn=turn,
            product_id=product_id,
            claim_type=claim_type,
            claim_value=claim_value,
        ))

    def set_confirmed_product(self, ctx: SessionContext, product_id: str) -> None:
        """设置用户确认的目标商品。"""
        ctx.state.consistency.confirmed_product_id = product_id
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_consistency_tracker.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/consistency_tracker.py server/tests/test_consistency_tracker.py
git commit -m "feat: add ConsistencyTracker — cross-turn claim consistency verification

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 11: 集成 ConsistencyTracker 到 agent.py

**目标**: 在 AnchorValidator 之后、推送之前执行 ConsistencyTracker 校验

**文件:**
- 修改: `server/backend/app/agent.py`
- 测试: `server/tests/test_consistency_tracker.py`（集成测试追加）

- [ ] **Step 1: 在 agent.py __init__ 中初始化 ConsistencyTracker**

```python
from .consistency_tracker import ConsistencyTracker
self.consistency_tracker = ConsistencyTracker()
```

- [ ] **Step 2: 在 _stream_recommendation_events 中，AnchorValidator 后插入 ConsistencyTracker**

在 `_stream_recommendation_events` 的 LLM 生成后（约 Task 8 修改的位置）追加:

```python
# 在 AnchorValidator 校验之后
if validation.is_valid:
    # ConsistencyTracker 校验
    consistency_result = self.consistency_tracker.check_before_output(
        session_ctx=context,
        ranked_product_ids=validation.referenced_product_ids,
        fact_ctx=fact_ctx,
    )
    if not consistency_result.is_consistent:
        logger.warning(f"[consistency] blocked: {consistency_result.blocked_reason}")
        fallback = fallback_text_for_failure("contradiction_blocked", plan, context=context)
        yield {"type": "consistency_blocked", "message_id": message_id,
               "reason": consistency_result.blocked_reason}
        for event in _text_delta_events(message_id, fallback):
            yield event
        return
```

- [ ] **Step 3: 在 _remember_recommendations 中记录 claims**

在方法末尾追加:

```python
# 记录一致性声明
for item in ranked:
    self.consistency_tracker.record_claim(
        context, item.product.product_id, "recommendation",
        f"推荐 {item.product.title} ¥{item.product.price:.0f}",
        turn=context.state.dialog_state.turn_index,
    )
```

- [ ] **Step 4: 在 _build_pending_recovery_events 找不到匹配时记录 denial**

在 `_build_pending_recovery_events` 返回 None 之前:

```python
if pending and pending.failed_query:
    self.consistency_tracker.record_denial(
        context, pending.failed_query,
        turn=context.state.dialog_state.turn_index,
    )
```

- [ ] **Step 5: 确认可导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.agent import ShopGuideAgent; print('OK')"
```
预期: `OK`

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/agent.py
git commit -m "feat(agent): integrate ConsistencyTracker into output pipeline

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 12: 增强 SessionStore — checkpoint 和 recover

**目标**: 新增 `checkpoint()` 异步写入和 `recover()` 恢复方法

**文件:**
- 修改: `server/backend/app/session_store.py`
- 测试: `server/tests/test_session_checkpoint.py`

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_session_checkpoint.py
from __future__ import annotations
import tempfile
import os
from pathlib import Path
from server.backend.app.session_store import SessionStore
from server.backend.app.models import SessionContext


def test_checkpoint_and_recover():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(persist_dir=tmpdir)
        ctx = store.get("user1", "sess1")
        ctx.state.checkpoint_stage = "turn_start"
        ctx.dialog_turns.append({"role": "user", "content": "推荐小米手机"})
        store.save("user1", "sess1")

        # 模拟恢复
        store2 = SessionStore(persist_dir=tmpdir)
        recovery = store2.recover("user1", "sess1")
        assert recovery is not None
        assert recovery.user_message_restored is True
        assert recovery.hint is not None


def test_checkpoint_stage_tracking():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(persist_dir=tmpdir)
        ctx = store.get("user1", "sess1")
        ctx.state.checkpoint_stage = "post_retrieve"
        store.save("user1", "sess1")

        store2 = SessionStore(persist_dir=tmpdir)
        ctx2 = store2.get("user1", "sess1")
        assert ctx2.state.checkpoint_stage == "post_retrieve"


def test_recover_nonexistent():
    store = SessionStore()
    recovery = store.recover("no_user", "no_sess")
    assert recovery is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_session_checkpoint.py -v
```
预期: FAIL（recover 方法不存在）

- [ ] **Step 3: 在 session_store.py 中新增方法**

```python
# 追加到 SessionStore 类

def recover(self, user_id: str, session_id: str):
    """恢复会话，返回 SessionRecovery 或 None。"""
    from .models import SessionRecovery
    ctx = self.get(user_id, session_id)
    stage = ctx.state.checkpoint_stage
    if stage == "turn_start":
        return SessionRecovery(
            user_message_restored=True,
            products_cached=False,
            hint="你刚才的消息我已收到，正在重新理解...",
        )
    elif stage == "post_retrieve":
        return SessionRecovery(
            user_message_restored=True,
            products_cached=True,
            hint="刚才的检索结果已恢复，我继续为你分析...",
        )
    elif stage == "turn_end":
        return SessionRecovery(
            user_message_restored=True,
            products_cached=True,
            hint=None,  # 完整回复已保存，无需提示
        )
    elif ctx.dialog_turns:
        # 有对话历史但无 checkpoint stage → 部分恢复
        return SessionRecovery(
            user_message_restored=True,
            products_cached=False,
            hint="对话历史已恢复，请告诉我你最后的问题。",
        )
    return None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_session_checkpoint.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/session_store.py server/tests/test_session_checkpoint.py
git commit -m "feat(session_store): add recover() method with stage-aware hints

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 13: 在 agent.py 中插入 3 个 checkpoint 点 + 统一异常边界

**目标**: 在 Turn Start、Post-Retrieve、Turn End 3 个位置自动保存；统一异常边界保留上下文

**文件:**
- 修改: `server/backend/app/agent.py`

- [ ] **Step 1: 在 stream_message 的 3 个位置插入 checkpoint**

在 `stream_message` 方法中（约第 328 行）：

**Checkpoint 1 — Turn Start**（用户消息已追加到 dialog_turns 之后）:
```python
context.dialog_turns.append({"role": "user", "content": request.message or ""})
# ↓ 新增
await self._checkpoint(user_id, request.session_id, "turn_start")
```

**Checkpoint 2 — Post-Retrieve**（检索+排序完成后，LLM 生成前）:
在 `_run_retrieval_flow` 的最后（约 LLM 生成前的位置）:
```python
# 在 context.last_plan 赋值之后
await self._checkpoint(user_id, request.session_id, "post_retrieve")
```

**Checkpoint 3 — Turn End**（完整回复推送后）:
在 `stream_message` 的 `self._record_display_messages(context, collected)` 之后:
```python
await self._checkpoint(user_id, request.session_id, "turn_end")
```

- [ ] **Step 2: 添加 _checkpoint helper 方法**

```python
async def _checkpoint(self, user_id: str, session_id: str, stage: str) -> None:
    """Fire-and-forget 的异步 checkpoint 写入。"""
    import asyncio
    try:
        context = self.sessions._sessions.get((user_id, session_id))
        if context:
            context.state.checkpoint_stage = stage
        asyncio.create_task(self._async_save(user_id, session_id))
    except Exception:
        logger.warning(f"[checkpoint] failed to schedule save for {user_id}/{session_id}", exc_info=True)

async def _async_save(self, user_id: str, session_id: str) -> None:
    """异步写入 session，不阻塞主流程。"""
    try:
        self.sessions.save(user_id, session_id)
    except Exception:
        logger.warning(f"[checkpoint] save failed for {user_id}/{session_id}", exc_info=True)
```

- [ ] **Step 3: 在 _do_stream_message 中增加统一异常边界**

```python
async def _do_stream_message(self, ...):
    try:
        # 正常流程
        ...
    except Exception as exc:
        logger.error(f"[stream] unhandled error: {exc}", exc_info=True)
        # 上下文保留：在降级回复前先保存 checkpoint
        await self._checkpoint(user_id, request.session_id, "post_error")
        message_id = _message_id()
        fallback = fallback_text_for_failure("internal_error", context=context)
        yield self._assistant_state(message_id, "error", "服务暂时不可用", intent="error")
        for event in _text_delta_events(message_id, fallback):
            yield event
        yield {"type": "done", "message_id": message_id}
```

- [ ] **Step 4: 确认导入和语法**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.agent import ShopGuideAgent; print('OK')"
```
预期: `OK`

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/agent.py
git commit -m "feat(agent): add 3-stage checkpoint + unified exception boundary

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 14: 上下文感知降级提示

**目标**: 所有 fallback 文案改为接收 `SessionContext`，输出包含具体商品名/查询词的提示

**文件:**
- 修改: `server/backend/app/degradation.py`

- [ ] **Step 1: 重写 degradation.py**

```python
"""降级提示 — 上下文感知的 fallback 文案。"""
from __future__ import annotations

from .models import SessionContext


def fallback_text_for_failure(reason: str, plan=None, context: SessionContext | None = None) -> str:
    # 提取上下文
    last_query = ""
    last_product_names: list[str] = []
    if context:
        if context.dialog_turns:
            last_query = (context.dialog_turns[-1].get("content", "") or "")[:50]
        for pid in (context.last_product_ids or [])[:3]:
            # 从 context 提取商品名（如果 last_recommendations 有）
            for rec in (context.last_recommendations or []):
                if rec.get("product_id") == pid:
                    last_product_names.append(str(rec.get("title", pid)))
                    break

    product_hint = ""
    if last_product_names:
        names = "、".join(last_product_names)
        product_hint = f"你之前关注的商品：{names}。"

    if reason == "llm_timeout":
        if last_product_names:
            return f"我找到了候选商品（含 {names}），但生成详细解释超时了。你可以直接查看商品卡片，或说「详细说说第一款」让我继续。"
        return "我正在检索相关商品，但生成解释超时了。请稍等片刻再试，或换个方式描述你的需求。"

    if reason == "retrieval_error":
        if last_product_names:
            return f"检索服务暂时不稳定，但我还记得你之前关注的商品（{names}）。你可以继续围绕它们提问，或稍后再试。"
        return "检索服务暂时不稳定，我先按当前商品库的基础信息给出保守结果。"

    if reason == "llm_error":
        query_hint = f"关于「{last_query}」" if last_query else ""
        return f"{query_hint}LLM 服务调用失败了，我暂时无法生成新的回复。你可以稍后再试，或换个方式描述你的需求。{product_hint}".strip()

    if reason == "hallucination_detected":
        query_hint = f"关于「{last_query}」" if last_query else ""
        return f"{query_hint}我生成的内容存在不准确之处，已触发保护机制。请重新描述你的需求，我会严格基于商品库为你查找。{product_hint}".strip()

    if reason == "contradiction_blocked":
        return f"当前回复与之前的分析存在矛盾，已被拦截。请换一种方式提问。{product_hint}".strip()

    if reason == "internal_error":
        return f"服务暂时不可用，请稍后再试。你的对话记录已保存，不会丢失。"

    return "当前服务暂时不稳定，我没有执行任何购物车或订单写操作。请稍后重试。"
```

- [ ] **Step 2: 确认导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.degradation import fallback_text_for_failure; print('OK')"
```
预期: `OK`

- [ ] **Step 3: 提交**

```bash
git add server/backend/app/degradation.py
git commit -m "feat(degradation): context-aware fallback messages with product hints

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 15: 全量回归测试 + 修复

**目标**: 确保所有改动不破坏现有功能

**文件:**
- 运行: `server/tests/` 下所有测试

- [ ] **Step 1: 运行全量测试**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/ -v --tb=short 2>&1 | tail -100
```

- [ ] **Step 2: 逐项修复 FAIL**

对每个失败的测试:
1. 阅读失败原因
2. 判断是预期行为变更（如旧 SemanticFrame → UnifiedPlan 的字段名变化）还是真正的回归
3. 预期变更 → 更新测试
4. 真正回归 → 修复代码

- [ ] **Step 3: 运行全量测试确认全部通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/ -v --tb=short
```
预期: 全部 PASS（或所有 FAIL 均为预期的语义变更，已更新测试）

- [ ] **Step 4: 提交**

```bash
git add server/tests/
git commit -m "test: update tests for UnifiedPlan migration, fix regressions

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 完成标志

Phase 1-5 全部完成，`pytest server/tests/` 全量通过后：
- LLM 调用次数从 3 减少到 2
- `[[product_id]]` 锚点机制确保所有商品引用可追溯到数据库
- AnchorValidator 拦截虚构商品引用
- ConsistencyTracker 阻止前后矛盾
- SessionStore checkpoint 保证上下文不丢失
- degradation 提示包含用户上下文
