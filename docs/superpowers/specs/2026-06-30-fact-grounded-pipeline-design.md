# 事实锚定管道 — 设计文档

> 日期：2026-06-30
> 状态：已确认
> 关联：ShopGuide Agent 幻觉问题根因修复

---

## 1. 问题定义

### 1.1 根因

LLM 在生成推荐文本时，**没有强制绑定到数据库真实商品**，导致：

- **P0 — 虚构商品**：AI 编造不存在的商品型号和虚假价格（如"小米 17 Max ¥6499"），存在商业欺诈风险
- **P1 — 前后矛盾**：同一轮对话中对同一商品的判定结果不一致（先说"不存在"，后在推荐列表中凭空出现）
- **P2 — 上下文丢失**：服务异常后会话状态丢失，重复询问用户已明确的信息
- **P3 — 幻觉逃逸**：现有 HallucinationChecker 只在事后检测，已流式输出的幻觉内容无法撤回
- **P4 — 降级无状态**：降级提示丢失用户上下文，体验粗糙

### 1.2 架构层面根因

当前链路有 2 次 LLM 调用在做重叠的事：`ToolPlanner.plan()` 和 `IntentCompiler.compile()` 各自用 LLM 提取约束信息，然后通过 `_merge_tool_plan_into_ir()` 互相覆盖。这不仅是冗余，还引入了不一致的可能性。

---

## 2. 目标架构

### 2.1 简化后的链路

```
用户消息
  → ToolPlanner.plan()      [LLM #1 唯一决策]  → UnifiedPlan
       ├── tool + confidence
       ├── constraints（硬/软/品牌/价格）
       ├── query_terms
       └── intent_hints（clarification 标记等）
  → StateReducer.apply()    [纯规则]           → 写入 SessionState（含 denial cache）
  → Retriever.search()      [BM25+向量+RRF]    → 候选商品
  → Ranker.rank()           [纯规则]           → 排序结果
  → FactContextBuilder      [纯规则]           → 事实上下文
       ├── prompt_block（含 [[product_id]] 锚点事实表，注入 LLM system prompt）
       ├── product_index（供 AnchorValidator 校验用）
       └── denied_queries（来自 ConsistencyTracker 的否定缓存）
  → LLM Generate            [LLM #2 锚定生成]  → 锚点标记文本（全量缓冲，不流式推送）
  → AnchorValidator         [纯规则]           → 锚点→真实商品 校验+替换+清洗
  → ConsistencyTracker      [纯规则]           → 跨轮一致性校验
  → 流式推送给用户
```

**关键变化：**
- LLM 调用从 3 次减少到 2 次（决策 1 次 + 生成 1 次）
- `SemanticFrame` / `RetrievalPlan` / `ToolPlan` 合并为 `UnifiedPlan`
- 删除 `IntentCompiler` 的 LLM 路径，保留纯规则逻辑合并到 `StateReducer`
- 删除 `_merge_tool_plan_into_ir()` workaround
- 新增 `FactContextBuilder`、`AnchorValidator`、`ConsistencyTracker`

### 2.2 保留不变的模块

- `StateReducer`、`QueryBuilder`（输入从 SemanticFrame 改为 UnifiedPlan）
- `AdaptiveRetriever`、`Reranker`、`Ranker`
- `ToolPlanner`（增强输出字段，引擎不变）
- `ToolRegistry`、各 Tool
- `SessionStore`、`CartService`、`OrderService`
- `CircuitBreaker`

---

## 3. 数据模型

### 3.1 UnifiedPlan（合并 ToolPlan + SemanticFrame + RetrievalPlan）

```python
class UnifiedPlan(BaseModel):
    """单次 LLM 调用的完整决策输出。"""
    # ---- 工具路由（原 ToolPlan） ----
    tool: str = "chitchat"
    confidence: float = 0.5

    # ---- 意图标记（原 SemanticFrame） ----
    need_clarification: bool = False
    clarification_question: str | None = None

    # ---- 硬约束（原 HardConstraints + ConstraintEdits） ----
    category: str | None = None
    sub_category: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    include_brands: list[str] = Field(default_factory=list)
    exclude_brands: list[str] = Field(default_factory=list)
    in_stock_only: bool = True

    # ---- 软偏好 ----
    soft_preferences: dict[str, str] = Field(default_factory=dict)

    # ---- 检索参数 ----
    retrieval_query: str = ""
    retrieval_mode: str = "single"

    # ---- cart 操作 ----
    cart_action: str | None = None
    cart_target_product_id: str | None = None
    cart_quantity: int = 1
```

### 3.2 FactContext（事实上下文，LLM 的唯一商品信息来源）

```python
@dataclass
class FactRecord:
    product_id: str
    title: str
    brand: str
    price: float
    category: str
    sub_category: str
    key_specs: list[str]    # 从 marketing_description + reviews 提取的核心卖点

@dataclass
class FactContext:
    prompt_block: str                       # 注入 LLM prompt 的事实部分
    product_index: dict[str, FactRecord]    # product_id → FactRecord
    brand_index: dict[str, set[str]]        # brand → {product_id, ...}
    denied_queries: list[str]               # 本次不应出现的查询词（来自 ConsistencyTracker）
```

### 3.3 ConsistencyState（跨轮一致性追踪，追加到 SessionState）

```python
class ClaimRecord(BaseModel):
    turn: int
    product_id: str
    claim_type: str          # "exists" | "not_exists" | "price" | "recommendation" | "comparison"
    claim_value: str

class ConsistencyState(BaseModel):
    claims: list[ClaimRecord] = Field(default_factory=list)
    confirmed_product_id: str | None = None
    denied_product_queries: list[str] = Field(default_factory=list)
```

### 3.4 删除的模型

| 模型 | 原因 |
|------|------|
| `ConstraintEdits` | UnifiedPlan 直接包含约束字段，不需要 add/remove/relax 的增量编辑 |
| `ConstraintPatch` | 同上 |
| `CartOperation` | UnifiedPlan 直接包含 cart_* 字段 |
| `QueryIntent` | UnifiedPlan 直接包含 query_terms + category_hint |
| `SemanticFrame` → 保留为 `UnifiedPlan` 的 type alias | 向后兼容 |

---

## 4. 核心模块设计

### 4.1 FactContextBuilder

**文件**: `server/backend/app/fact_context.py`

**职责**: 将 `UnifiedPlan` + 检索结果 + DB 商品数据组装为 `FactContext`

**输入**: `UnifiedPlan` + `list[RankedProduct]`

**prompt_block 格式**（注入 LLM system prompt 的末尾）：

```
[可用商品事实库] — 以下是你唯一可以引用的商品信息。
引用时必须使用 [[product_id]] 锚点格式。
任何未列在此库中的商品名称、型号、价格均视为不存在，禁止提及。

1. [[XIAOMI_14_ULTRA]]
   名称: 小米 14 Ultra
   品牌: 小米 | 价格: ¥5999
   核心卖点: 徕卡光学镜头 | 骁龙8Gen3 | 1英寸大底主摄

2. [[XIAOMI_15_PRO]]
   名称: 小米 15 Pro
   品牌: 小米 | 价格: ¥5299
   核心卖点: 6.73英寸2K屏 | 骁龙8Gen4 | 120W快充

规则：
- 推荐或提及任何商品时，必须使用准确的 [[product_id]] 锚点
- 如果要比较价格/参数，只能使用上面列出的数值
- 如果用户问的商品不在库中，直接说"库中暂无此商品，请确认型号"
- 不要编造任何商品名称、型号或价格
```

**关键规格提取逻辑**:
- 从 `marketing_description` 中提取前 3 个技术关键词
- 从 `reviews` 中按频率提取 top 2 用户评价关键词
- 合并去重后取前 5 个作为 `key_specs`

### 4.2 AnchorValidator

**文件**: `server/backend/app/anchor_validator.py`

**职责**: 校验 LLM 生成的文本中每个 `[[product_id]]` 锚点

**处理流程**:

```
Step 1: extract_anchors(text) → list[str]
  正则: \[\[([A-Za-z0-9_-]+)\]\]
  找到所有被 LLM 引用的 product_id

Step 2: resolve(anchors, fact_context) → dict[str, FactRecord | None]
  每个 anchor 在 fact_context.product_index 中查找
  找到 → FactRecord
  找不到 → None（标记为虚构引用）

Step 3: validate(resolved) → ValidationResult
  - 所有 anchor 都解析成功 → VALID
  - 有解析失败的 anchor → 移除该锚点 + 其上下文句子
  - 没有任何有效 anchor → 整个输出替换为 fallback

Step 4: expand(text, resolved) → str
  将 [[XIAOMI_14_ULTRA]] 替换为 "**小米 14 Ultra**"（加粗显示名）
  同时记录需要下发的 product_item 列表

Step 5: detect_stray_names(expanded_text, fact_context) → list[str]
  扫描替换后的文本中是否还有数据库中的商品名出现但无对应锚点
  （LLM 没用锚点格式，直接写了商品名）
  有 → 标记为 stray_name，降级处理
```

**3 种异常场景处理**:

| 场景 | 检测方式 | 处理 |
|------|----------|------|
| 锚点解析失败 | `product_id not in product_index` | 移除该锚点及其所在句子，替换为"该商品" |
| 裸奔商品名 | 文本中出现 title/brand 但没有对应锚点 | 检测到 → fallback 文本替换，yield `hallucination_corrected` 事件 |
| 价格/参数偏差（兜底） | 复用 HallucinationChecker 的价格比对 | 触发 protection，替换价格为 FactContext 中的价格 |

### 4.3 ConsistencyTracker

**文件**: `server/backend/app/consistency_tracker.py`

**职责**: 跨轮次校验回答一致性

**3 条核心规则**（纯规则，不调 LLM）:

```
Rule 1 — Denial Cache（否定缓存）
  IF 之前声明某查询词"不存在于商品库"
  THEN 后续检索结果中必须硬过滤包含该查询词的商品
  IMPL: 在 FactContextBuilder 构建时注入 denied_queries，AnchorValidator 中校验

Rule 2 — Price Consistency（价格一致性）
  IF 同一 product_id 在不同轮次中被提到
  THEN 价格必须与 FactContext 一致
  IMPL: AnchorValidator.expand() 时强制使用 FactContext 中的价格

Rule 3 — Focus Drift Detection（焦点漂移）
  IF confirmed_product_id 已设置
  THEN 如果新回复中主要推荐了无关商品，注入 focus_reminder 到下一轮 prompt
  IMPL: 在推送前检查，若漂移 → 在 context 中标记，下轮 prompt 开头注入提醒
```

**执行时机**: 在 AnchorValidator 之后、推送用户之前

### 4.4 链路简化

**删除模块**:
- `intent_compiler.py` — 删除 `IntentCompiler` 类
- `semantic_layer.py` — 删除 `SemanticParser.parse()` 的 LLM 路径，保留 `rule_semantic_frame()` 作为 ToolPlanner LLM 失败兜底
- `agent.py` — 删除 `_merge_tool_plan_into_ir()`

**合并逻辑**:
- `IntentCompiler` 中的 `_prepare_context_for_turn()` 规则逻辑 → `StateReducer`
- `IntentCompiler` 中的澄清回答检测 → `StateReducer`

### 4.5 会话持久化（P2）

**3 个自动 checkpoint 插入点**（在 `agent.py` 的 `stream_message()` 中）:

```
1. Turn Start — 用户消息到达后立即保存
2. Post-Retrieve — 检索+排序完成后保存
3. Turn End — 完整回复推送完成后保存
```

**SessionStore 新增方法**:

```python
async def checkpoint(self, user_id: str, session_id: str, stage: str) -> None:
    """fire-and-forget 异步写入，失败只记 log"""

def recover(self, user_id: str, session_id: str) -> SessionRecovery:
    """返回上次 checkpoint 状态 + 恢复提示"""
```

**SessionState 新增字段**: `checkpoint_stage: str`

### 4.6 优雅降级（P4）

**核心变更**: 所有 fallback 文案从无状态通用文本 → 上下文感知提示

```python
def fallback_text_for_failure(reason: str, context: SessionContext | None = None) -> str:
    # 从 context 提取 last_query、last_product_ids
    # 输出包含具体商品名/查询词的上下文感知提示
```

**异常边界统一**（在 `_do_stream_message()` 中）:

```python
try:
    # 正常流程
except RetrievalUnavailableError:
    await self.sessions.checkpoint(user_id, request.session_id, "post_error")
    yield from self._degraded_response("retrieval_unavailable", context)
except LLMUnavailableError:
    await self.sessions.checkpoint(user_id, request.session_id, "post_error")
    yield from self._degraded_response("llm_unavailable", context)
```

---

## 5. 实现计划

### Phase 1：数据模型统一（基础层）

| 文件 | 改动 |
|------|------|
| `models.py` | 新增 `UnifiedPlan`、`FactContext`、`FactRecord`、`ClaimRecord`、`ConsistencyState`；删除 `ConstraintEdits`、`ConstraintPatch`、`CartOperation`、`QueryIntent` |
| `tool_plan.py` | `ToolPlan` → `UnifiedPlan` 替换 |

### Phase 2：链路简化

| 文件 | 改动 |
|------|------|
| `tool_planner.py` | 增强 prompt 输出完整 UnifiedPlan JSON；`_parse_plan()` 解析 UnifiedPlan |
| `agent.py` | 删除 `_merge_tool_plan_into_ir()`；`_do_stream_message()` 改为直接从 UnifiedPlan 驱动 |
| `state_reducer.py` | 吸收 IntentCompiler 的规则逻辑 |
| `intent_compiler.py` | 删除 |
| `semantic_layer.py` | 删除 LLM 路径，保留 rule 兜底 |
| `tools/*.py` | 参数从 `compiled_ir` + `plan` → `unified_plan` |

### Phase 3：事实锚定管道（P0 + P3）

| 文件 | 改动 |
|------|------|
| **新建 `fact_context.py`** | FactContextBuilder 完整实现 |
| **新建 `anchor_validator.py`** | AnchorValidator 完整实现 |
| `agent.py` | prompt 注入 FactContext；生成改为全量缓冲 → 校验 → 推送 |
| `hallucination_checker.py` | 保留价格检测作为兜底；去掉虚构 ID/名称检测 |
| `degradation.py` | 新增 hallucination_blocked / anchor_validation_failed 场景 |

### Phase 4：一致性约束（P1）

| 文件 | 改动 |
|------|------|
| **新建 `consistency_tracker.py`** | ConsistencyTracker 完整实现 |
| `models.py` | SessionState 新增 consistency 字段 |
| `agent.py` | AnchorValidator 之后调用 ConsistencyTracker |

### Phase 5：会话持久化 + 优雅降级（P2 + P4）

| 文件 | 改动 |
|------|------|
| `session_store.py` | 新增 checkpoint() 和 recover() |
| `models.py` | SessionState 新增 checkpoint_stage |
| `agent.py` | 3 个 checkpoint 插入点 + 统一异常边界 |
| `degradation.py` | 所有 fallback 改为上下文感知 |

### 测试

| 文件 | 内容 |
|------|------|
| `test_fact_context.py` | FactContextBuilder 构建正确性 |
| `test_anchor_validator.py` | 锚点解析/异常处理 |
| `test_consistency_tracker.py` | 3 条规则的拦截/放行判定 |
| `test_unified_plan.py` | UnifiedPlan JSON 解析 |
| `test_session_checkpoint.py` | checkpoint 写入/恢复 |
| `test_degradation.py` | 上下文感知降级文案 |

---

## 6. 风险与缓解

| 风险 | 可能性 | 缓解 |
|------|--------|------|
| LLM 不遵循 `[[product_id]]` 锚点格式 | 中 | prompt 中 3-5 个 few-shot 示例；`detect_stray_names` 兜底；若广泛不遵循则降级到全量 fallback |
| UnifiedPlan JSON 字段过多，LLM 输出不稳定 | 中 | 所有字段设默认值；遗漏字段由 StateReducer 规则补全；`_rule_fallback()` 兜底 |
| Checkpoint 异步写入失败 | 低 | fire-and-forget 模式，失败只记 log；关键数据同时写内存 |
| Phase 2 链路简化导致回归 | 中 | Phase 2 后先跑全量 `pytest server/tests/`，确认无回归再进入 Phase 3 |
| 全量缓冲增加首字延迟 | 中 | 并行优化：检索+排序期间预加载 FactContext；AnchorValidator 纯 CPU 计算可忽略 |

---

## 7. 非目标（明确不做）

- 不改变 Cart/Order 的任何逻辑
- 不改变 TTS/STT 适配器
- 不改变 WebSocket 协议 / realtime_envelope
- 不改变 feedback_ranker / feedback_store
- 不引入新的外部依赖
- 不做 LLM 模型升级（当前 Doubao/DeepSeek 保持不变）
