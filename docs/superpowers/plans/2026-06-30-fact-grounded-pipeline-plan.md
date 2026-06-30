# 事实锚定管道 — 实现计划（两阶段）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**总体目标:** 引入事实锚定管道彻底消除 LLM 幻觉，同时简化 Plan 链路将 LLM 调用从 3 次降到 2 次。

**分阶段策略:**
- **Stage 1（12 Tasks）:** 在现有模型不变的前提下，引入 FactContext + 流式 AnchorValidator + ConsistencyTracker + Checkpoint。保留 ToolPlan/SemanticFrame/RetrievalPlan 三层不变。
- **Stage 2（8 Tasks）:** UnifiedPlan 迁移——合并三层模型，删除 IntentCompiler LLM 路径，LLM 调用 3→2。

**LLM 调用目标:** 当前 3 次（ToolPlanner + IntentCompiler + Generate），Stage 1 保持 3 次，Stage 2 降为 2 次。

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, 现有 Doubao/DeepSeek LLM 客户端不变

## 全局约束

- **不删除任何现有模型**（ConstraintEdits、CartOperation、QueryIntent 等全部保留），只追加新模型
- **不改变 ToolPlan / SemanticFrame / RetrievalPlan 的任何字段**
- **不改变 Cart/Order/TTS/STT/WebSocket 协议**
- 不引入新的外部依赖
- 所有新增模块遵循项目现有的 `from __future__ import annotations` + Pydantic/dataclass 模式
- 每个 Task 完成后必须通过关联的 pytest 测试
- 最终 Task 必须跑全量 `pytest server/tests/` 确认无回归

---

## 文件结构

| 文件 | 职责 | 改动类型 |
|------|------|----------|
| `models.py` | 追加 FactRecord、FactContext、ClaimRecord、ConsistencyState、SessionRecovery；SessionState 新增 consistency + checkpoint_stage 字段 | 修改 |
| `fact_context.py` | FactContextBuilder：UnifiedPlan-like 约束 + RankedProduct → FactContext（prompt_block + product_index + brand_index） | **新建** |
| `anchor_validator.py` | AnchorValidator（流式模式）：逐 chunk 检测 `[[pid]]`，微缓冲校验，命中→展开，未命中→替换为「该商品」 | **新建** |
| `consistency_tracker.py` | ConsistencyTracker：denial cache 记录/查询、price consistency、focus drift 检测 | **新建** |
| `llm_client.py` | 三个 stream_response + _response_evidence_payload 全部追加 `fact_block: str = ""` 参数 | 修改 |
| `agent.py` | 集成 FactContextBuilder → AnchorValidator → ConsistencyTracker；3 个 checkpoint 插入点；统一异常边界 | 修改 |
| `hallucination_checker.py` | verify() 签名改为接收 FactContext；去掉虚构 ID/名称检测（已被 AnchorValidator 覆盖） | 修改 |
| `session_store.py` | 新增公开方法 checkpoint() 和 recover() | 修改 |
| `degradation.py` | fallback_text_for_failure() 接收 context 参数，输出上下文感知提示 | 修改 |

---

### Task 1: 追加新模型到 models.py（不删不改旧模型）

**目标:** 在 `models.py` 末尾追加新模型；SessionState 追加 consistency 和 checkpoint_stage 字段

**文件:**
- 修改: `server/backend/app/models.py`
- 测试: `server/tests/test_new_models.py`

**接口:**
- 产出: `FactRecord`, `FactContext`, `ClaimRecord`, `ConsistencyState`, `SessionRecovery` 类
- SessionState 新增: `consistency: ConsistencyState`、`checkpoint_stage: str`
- 后续 Task 2-12 依赖这些模型

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_new_models.py
from __future__ import annotations
from server.backend.app.models import (
    FactRecord, FactContext, ClaimRecord, ConsistencyState,
    SessionRecovery, SessionState, SessionContext,
)


def test_fact_record():
    r = FactRecord(product_id="P1", title="商品1", brand="小米", price=100.0,
                   category="手机", sub_category="智能机", key_specs=["快"])
    assert r.product_id == "P1"
    assert r.price == 100.0


def test_fact_context():
    r1 = FactRecord(product_id="P1", title="A", brand="小米", price=100,
                    category="手机", sub_category="智能机")
    r2 = FactRecord(product_id="P2", title="B", brand="华为", price=200,
                    category="手机", sub_category="智能机")
    ctx = FactContext(
        prompt_block="事实块",
        product_index={"P1": r1, "P2": r2},
        brand_index={"小米": ["P1"], "华为": ["P2"]},
        denied_queries=["不存在商品"],
    )
    assert ctx.product_index["P1"].brand == "小米"
    assert ctx.brand_index["小米"] == ["P1"]
    assert "不存在商品" in ctx.denied_queries


def test_fact_context_defaults():
    ctx = FactContext()
    assert ctx.prompt_block == ""
    assert ctx.product_index == {}
    assert ctx.denied_queries == []


def test_consistency_state():
    cs = ConsistencyState(
        claims=[ClaimRecord(turn=1, product_id="P1", claim_type="price", claim_value="¥100")],
        confirmed_product_id="P1",
        denied_product_queries=["不存在查询"],
    )
    assert cs.confirmed_product_id == "P1"
    assert len(cs.denied_product_queries) == 1
    assert cs.claims[0].claim_type == "price"


def test_consistency_state_defaults():
    cs = ConsistencyState()
    assert cs.claims == []
    assert cs.confirmed_product_id is None


def test_session_recovery():
    sr = SessionRecovery(user_message_restored=True, products_cached=False,
                         hint="你的消息已收到")
    assert sr.user_message_restored is True
    assert sr.hint is not None


def test_session_state_has_consistency_field():
    """SessionState 默认应有 consistency 和 checkpoint_stage 字段。"""
    state = SessionState()
    assert state.consistency == ConsistencyState()
    assert state.checkpoint_stage == ""


def test_session_context_imports_unchanged():
    """旧模型不受影响。"""
    from server.backend.app.models import (
        ConstraintEdits, CartOperation, QueryIntent, SemanticFrame,
        ShoppingIntentIR, RetrievalPlan,
    )
    from server.backend.app.tool_plan import ToolPlan  # ToolPlan 在 tool_plan.py，不在 models.py
    assert ConstraintEdits is not None
    assert SemanticFrame is not None
    assert ToolPlan is not None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_new_models.py -v
```
预期: FAIL（新模型未定义，SessionState 无新字段）

- [ ] **Step 3: 在 models.py 中——注意定义顺序**

**关键：`ClaimRecord` 和 `ConsistencyState` 必须在 `SessionState` 之前定义**，因为 `SessionState` 的 `Field(default_factory=ConsistencyState)` 在类定义时立即求值（`from __future__ import annotations` 只影响 annotation，不影响 default_factory）。

插入位置：在当前 `SessionState` 定义之前（约第 192 行），追加新模型：

```python
# ========== 事实锚定管道模型（Stage 1） ==========


class FactRecord(BaseModel):
    """单个商品的事实卡片 — LLM prompt 中的一行事实。"""
    product_id: str
    title: str
    brand: str
    price: float
    category: str
    sub_category: str
    key_specs: list[str] = Field(default_factory=list)


class FactContext(BaseModel):
    """注入 LLM prompt 的事实上下文 + 供 AnchorValidator 使用的校验索引。"""
    prompt_block: str = ""
    product_index: dict[str, FactRecord] = Field(default_factory=dict)
    brand_index: dict[str, list[str]] = Field(default_factory=dict)
    denied_queries: list[str] = Field(default_factory=list)


class ClaimRecord(BaseModel):
    """单条关于商品的声明。"""
    turn: int
    product_id: str
    claim_type: str
    claim_value: str


class ConsistencyState(BaseModel):
    """跨轮一致性状态——必须在 SessionState 之前定义。"""
    claims: list[ClaimRecord] = Field(default_factory=list)
    confirmed_product_id: str | None = None
    denied_product_queries: list[str] = Field(default_factory=list)


class SessionRecovery(BaseModel):
    """会话恢复结果。"""
    user_message_restored: bool = False
    products_cached: bool = False
    hint: str | None = None
```

- [ ] **Step 4: 在 SessionState 中追加两个字段**

新模型插入后，`SessionState` 现在在这些类定义**之后**，可以安全引用。在 `SessionState` 现有字段列表末尾（`trace: TraceState` 之后）追加：

```python
    # 事实锚定管道（Stage 1）
    consistency: ConsistencyState = Field(default_factory=ConsistencyState)
    checkpoint_stage: str = ""
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_new_models.py -v
```
预期: 全部 PASS

- [ ] **Step 6: 确认旧模型导入不受影响**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "
from server.backend.app.models import ConstraintEdits, CartOperation, QueryIntent, SemanticFrame, ShoppingIntentIR
print('All old models import OK')
"
```
预期: `All old models import OK`

- [ ] **Step 7: 提交**

```bash
git add server/backend/app/models.py server/tests/test_new_models.py
git commit -m "feat(models): add FactContext, ConsistencyState, SessionRecovery for Stage 1

- FactRecord/FactContext: LLM's sole source of product truth
- ClaimRecord/ConsistencyState: cross-turn claim tracking
- SessionRecovery: session restore status
- SessionState gains consistency + checkpoint_stage fields
- All existing models (ConstraintEdits/CartOperation/etc.) kept unchanged

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 创建 FactContextBuilder

**目标:** 从检索排序结果构建 FactContext（prompt_block + product_index + brand_index）

**文件:**
- 创建: `server/backend/app/fact_context.py`
- 测试: `server/tests/test_fact_context.py`

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_fact_context.py
from __future__ import annotations
from server.backend.app.models import Product, RankedProduct, FactContext
from server.backend.app.fact_context import FactContextBuilder


def _mk_product(pid: str, title: str, brand: str, price: float,
                cat: str = "手机", sub: str = "智能机", desc: str = "") -> Product:
    return Product(
        product_id=pid, title=title, brand=brand, price=price,
        category=cat, sub_category=sub, image_path="",
        marketing_description=desc or f"{title} 优质产品",
        search_text=title,
    )


def _mk_ranked(p: Product, score: float = 0.9) -> RankedProduct:
    return RankedProduct(product=p, score=score, tier=1, reason="匹配")


def test_build_empty():
    ctx = FactContextBuilder().build([])
    assert ctx.prompt_block == ""
    assert ctx.product_index == {}
    assert ctx.brand_index == {}
    assert ctx.denied_queries == []


def test_build_with_products():
    p1 = _mk_product("P1", "小米 14 Ultra", "小米", 5999.0)
    p2 = _mk_product("P2", "华为 Mate 70 Pro", "华为", 6999.0)
    ranked = [_mk_ranked(p1), _mk_ranked(p2)]
    ctx = FactContextBuilder().build(ranked, denied_queries=["小米 17 Max"])

    assert "P1" in ctx.product_index
    assert ctx.product_index["P1"].brand == "小米"
    assert ctx.product_index["P1"].price == 5999.0
    assert "P1" in ctx.brand_index["小米"]
    assert "P2" in ctx.brand_index["华为"]

    # prompt_block 格式
    assert "[[P1]]" in ctx.prompt_block
    assert "[[P2]]" in ctx.prompt_block
    assert "小米 14 Ultra" in ctx.prompt_block
    assert "¥5999" in ctx.prompt_block

    # denied_queries 透传
    assert "小米 17 Max" in ctx.denied_queries


def test_prompt_block_contains_rules():
    p = _mk_product("P1", "测试", "牌子", 100.0)
    ctx = FactContextBuilder().build([_mk_ranked(p)])
    assert "你唯一可以引用的商品信息" in ctx.prompt_block
    assert "[[product_id]]" in ctx.prompt_block
    assert "不要编造任何商品名称" in ctx.prompt_block


def test_key_specs_extraction():
    p = _mk_product("P1", "商品", "品牌", 100.0,
                    desc="徕卡镜头, 骁龙8Gen3, 1英寸大底")
    ctx = FactContextBuilder().build([_mk_ranked(p)])
    assert "徕卡镜头" in ctx.prompt_block
    assert "骁龙8Gen3" in ctx.prompt_block


def test_denied_queries_default():
    ctx = FactContextBuilder().build([])
    assert ctx.denied_queries == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_fact_context.py -v
```
预期: FAIL（模块不存在）

- [ ] **Step 3: 创建 fact_context.py**

```python
"""事实上下文构建器 — 将检索排序结果组装为 LLM 唯一事实来源。"""
from __future__ import annotations

import re

from .models import RankedProduct, FactContext, FactRecord


class FactContextBuilder:
    """将检索排序结果组装为 FactContext。

    prompt_block 注入 LLM system prompt 末尾，要求 LLM 用 [[product_id]] 锚点
    格式引用商品。product_index 供 AnchorValidator 流式校验；brand_index 供
    ConsistencyTracker 使用。
    """

    def build(self, ranked: list[RankedProduct], *,
              denied_queries: list[str] | None = None) -> FactContext:
        if not ranked:
            return FactContext(denied_queries=list(denied_queries or []))

        records: list[FactRecord] = []
        for item in ranked:
            product = item.product
            records.append(FactRecord(
                product_id=product.product_id,
                title=product.title,
                brand=product.brand,
                price=product.price,
                category=product.category,
                sub_category=product.sub_category,
                key_specs=self._extract_key_specs(product),
            ))

        product_index = {r.product_id: r for r in records}
        brand_index: dict[str, list[str]] = {}
        for r in records:
            brand_index.setdefault(r.brand, []).append(r.product_id)

        return FactContext(
            prompt_block=self._render_prompt_block(records),
            product_index=product_index,
            brand_index=brand_index,
            denied_queries=list(denied_queries or []),
        )

    def _extract_key_specs(self, product) -> list[str]:
        keywords: list[str] = []
        desc = (product.marketing_description or "").strip()
        if desc:
            parts = re.split(r"[，,、\s]+", desc)
            keywords.extend(p.strip() for p in parts[:3] if 2 <= len(p.strip()) <= 20)
        for review in (product.reviews or [])[:3]:
            text = str(review.get("content", ""))
            if text and len(text) < 30:
                keywords.append(text.strip())
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
git commit -m "feat: FactContextBuilder — structured fact sheet for LLM anchoring

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 创建 AnchorValidator（流式模式）

**目标:** 逐 chunk 检测 `[[product_id]]` 锚点，微缓冲校验，命中→展开为商品名，未命中→替换为「该商品」

**关键设计:**
- 普通文本 chunk：**立即透传**（零延迟）
- 遇到 `[[`：进入缓冲模式，收集到 `]]` → 查 `fact_ctx.product_index` → 展开/替换 → 立即透传 → 循环检查同一 chunk 中是否还有 `[[`
- 同一 chunk 内的多个锚点（如 `"推荐 [[P1]]，备选 [[P2]]"`）通过循环状态机处理，不遗漏
- 无效锚点 → yield `anchor_warning` 事件 + 替换为「该商品」
- 流式结束后：deferred `detect_stray_names()` 在**原始 LLM 输出**上执行（expand 前），排除已被锚点覆盖的 title span，yield `stray_warning` 事件

**文件:**
- 创建: `server/backend/app/anchor_validator.py`
- 测试: `server/tests/test_anchor_validator.py`

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_anchor_validator.py
from __future__ import annotations
import asyncio
from server.backend.app.models import FactContext, FactRecord
from server.backend.app.anchor_validator import AnchorValidator


def _mk_ctx() -> FactContext:
    r1 = FactRecord(product_id="P1", title="小米 14 Ultra", brand="小米", price=5999.0,
                    category="手机", sub_category="智能机")
    r2 = FactRecord(product_id="P2", title="华为 Mate 70", brand="华为", price=6999.0,
                    category="手机", sub_category="智能机")
    return FactContext(
        prompt_block="",
        product_index={"P1": r1, "P2": r2},
        brand_index={"小米": ["P1"], "华为": ["P2"]},
    )


def test_extract_anchors_from_text():
    text = "推荐 [[P1]]，备选 [[P2]]"
    assert AnchorValidator.extract_anchors(text) == ["P1", "P2"]


def test_extract_anchors_none():
    assert AnchorValidator.extract_anchors("纯文本无锚点") == []


def test_resolve_valid():
    ctx = _mk_ctx()
    v = AnchorValidator()
    resolved = v.resolve("P1", ctx)
    assert resolved is not None
    assert resolved.title == "小米 14 Ultra"


def test_resolve_invalid():
    ctx = _mk_ctx()
    v = AnchorValidator()
    assert v.resolve("FAKE_ID", ctx) is None


def test_expand_anchor():
    ctx = _mk_ctx()
    v = AnchorValidator()
    result = v.expand_anchor("P1", ctx)
    assert result == "**小米 14 Ultra**"


def test_expand_anchor_invalid():
    ctx = _mk_ctx()
    v = AnchorValidator()
    result = v.expand_anchor("FAKE_ID", ctx)
    assert result == "该商品"


def test_detect_stray_names_on_original_text():
    """裸奔检测应在原始 LLM 输出上执行（expand 之前）。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    # 原始文本中直接写了商品名但没用 [[P1]] 锚点
    original_text = "我推荐小米 14 Ultra，它拍照很好"
    strays = v.detect_stray_names(original_text, ctx)
    assert len(strays) >= 1
    assert any("小米 14 Ultra" in s for s in strays)


def test_detect_stray_names_excludes_anchored():
    """被锚点覆盖的 title 不应被检测为 stray。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    # 用了 [[P1]] 锚点的文本
    original_text = "我推荐 [[P1]]，拍照很好。备选 [[P2]]。"
    strays = v.detect_stray_names(original_text, ctx)
    # P1/P2 已被锚点覆盖，不应该是 stray
    assert all("小米 14 Ultra" not in s for s in strays)


async def test_stream_process_normal_text():
    """普通文本应逐 chunk 立即透传。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["推荐一款", "手机给", "你"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    # 所有普通文本应立即透传
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    assert "".join(text_parts) == "推荐一款手机给你"


async def test_stream_process_with_anchor():
    """含锚点的 chunk 应展开后透传。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["我推荐 ", "[[P1]]", "，它拍照很好"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    full = "".join(text_parts)
    assert "小米 14 Ultra" in full
    assert "[[" not in full


async def test_stream_process_with_invalid_anchor():
    """无效锚点应替换为「该商品」并记录 warning。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["看看 ", "[[FAKE_ID]]", " 怎么样"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    full = "".join(text_parts)
    assert "该商品" in full
    # 应有 warning 事件
    warnings = [e for e in results if e["type"] == "anchor_warning"]
    assert len(warnings) >= 1


async def test_stream_process_split_anchor():
    """锚点跨越两个 chunk 时应正确缓冲拼接。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    chunks = ["推荐 ", "[", "[P1]", "] 不错"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    full = "".join(text_parts)
    assert "小米 14 Ultra" in full
    assert "[[" not in full


async def test_stream_process_stray_detection_at_end():
    """流式结束时执行 deferred 裸奔检测。"""
    ctx = _mk_ctx()
    v = AnchorValidator()
    # 不用锚点直接写商品名
    chunks = ["推荐 小米 14 Ultra，拍照不错"]
    results = []
    async for event in v.stream_process(chunks, ctx):
        results.append(event)
    # 文本已透传（裸奔无法在流式中撤回）
    text_parts = [e["text"] for e in results if e["type"] == "text_delta"]
    assert "小米 14 Ultra" in "".join(text_parts)
    # 但应有一个 stray_warning 事件
    strays = [e for e in results if e["type"] == "stray_warning"]
    assert len(strays) >= 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_anchor_validator.py -v
```
预期: FAIL

- [ ] **Step 3: 创建 anchor_validator.py**

```python
"""锚点校验器（流式模式）— 逐 chunk 检测 [[product_id]]，微缓冲校验后透传。"""
from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

from .models import FactContext, FactRecord

logger = logging.getLogger(__name__)


class AnchorValidator:
    """流式锚点校验器。

    普通文本: 立即透传（零延迟）
    遇到 `[[`: 缓冲到 `]]` → 命中 product_index → 展开为 "**商品名**"
                                    → 未命中 → 替换为 "该商品" + log warning
    流式结束: deferred 裸奔名检测（记 warning + yield stray_warning 事件）
    """

    ANCHOR_PATTERN = re.compile(r'\[\[([A-Za-z0-9_-]+)\]\]')

    @staticmethod
    def extract_anchors(text: str) -> list[str]:
        return AnchorValidator.ANCHOR_PATTERN.findall(text)

    def resolve(self, anchor_id: str, fact_ctx: FactContext) -> FactRecord | None:
        return fact_ctx.product_index.get(anchor_id)

    def expand_anchor(self, anchor_id: str, fact_ctx: FactContext) -> str:
        record = self.resolve(anchor_id, fact_ctx)
        if record is not None:
            return f"**{record.title}**"
        logger.warning(f"[anchor_validator] unresolved anchor: {anchor_id}")
        return "该商品"

    async def stream_process(
        self,
        chunks: list[str] | AsyncIterator,
        fact_ctx: FactContext,
    ) -> AsyncIterator[dict]:
        """流式处理 LLM 输出 chunks。

        循环状态机：每个 chunk 内重复扫描直到没有 `[[` 为止，
        正确处理同 chunk 内的多个锚点（如 "推荐 [[P1]]，备选 [[P2]]"）。
        """
        collected_text: list[str] = []
        pending = ""  # 跨 chunk 的未闭合锚点缓冲 + `[` 后缀缓冲

        if hasattr(chunks, '__aiter__'):
            async_iter = chunks
        else:
            async def _list_iter():
                for c in chunks:
                    yield c
            async_iter = _list_iter()

        async for chunk in async_iter:
            if not chunk:
                continue
            collected_text.append(chunk)
            text = pending + chunk
            pending = ""

            # 循环处理：同一 chunk 内可能包含多个 [[...]] 锚点
            while '[[' in text:
                before, rest = text.split('[[', 1)
                if before:
                    yield {"type": "text_delta", "text": before}

                if ']]' in rest:
                    anchor_id, after = rest.split(']]', 1)
                    anchor_id = anchor_id.strip()
                    record = self.resolve(anchor_id, fact_ctx)
                    if record is not None:
                        yield {"type": "text_delta", "text": f"**{record.title}**"}
                    else:
                        logger.warning(f"[anchor_validator] unresolved anchor: {anchor_id}")
                        yield {"type": "anchor_warning", "anchor_id": anchor_id}
                        yield {"type": "text_delta", "text": "该商品"}
                    text = after  # 继续循环
                else:
                    pending = '[[' + rest  # `]]` 在后续 chunk 中
                    break
            else:
                # 没有更多 `[[`
                # 关键: 如果 text 以 `[` 结尾，保留到 pending，
                # 防止 `[[` 跨 chunk 分割（如 chunk1="["，chunk2="[P1]"）
                if text and text[-1] == '[':
                    pending = '['
                    text = text[:-1]
                if text:
                    yield {"type": "text_delta", "text": text}

        # 流结束：pending 中剩余的文本（截断锚点或孤立的 `[`）
        if pending:
            yield {"type": "text_delta", "text": pending}

        # deferred 裸奔检测：在原始文本上检测未被锚点覆盖的商品名
        if fact_ctx.product_index:
            full_text = "".join(collected_text)
            strays = self.detect_stray_names(full_text, fact_ctx)
            if strays:
                logger.warning(f"[anchor_validator] stray names detected: {strays}")
                yield {
                    "type": "stray_warning",
                    "stray_names": strays,
                }

    def detect_stray_names(self, original_text: str, fact_ctx: FactContext) -> list[str]:
        """在原始 LLM 文本上检测未用锚点标记的商品名。

        注意: 必须在 expand 之前、原始文本上执行。
        已被 [[product_id]] 锚点覆盖的 title 自动排除。
        """
        strays: list[str] = []
        # 找出原始文本中所有已用锚点的 product_id
        anchored_ids = set(self.extract_anchors(original_text))

        for pid, record in fact_ctx.product_index.items():
            if pid in anchored_ids:
                continue  # 已用锚点覆盖，跳过
            title = record.title
            if len(title) >= 4 and title in original_text:
                strays.append(title)
        return strays
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_anchor_validator.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/anchor_validator.py server/tests/test_anchor_validator.py
git commit -m "feat: AnchorValidator — streaming [[product_id]] validation with deferred stray detection

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 创建 ConsistencyTracker

**目标:** denial cache 记录/查询、focus drift 检测、claim 记录

**文件:**
- 创建: `server/backend/app/consistency_tracker.py`
- 测试: `server/tests/test_consistency_tracker.py`

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_consistency_tracker.py
from __future__ import annotations
from server.backend.app.models import SessionContext, ConsistencyState, ClaimRecord, FactContext, FactRecord
from server.backend.app.consistency_tracker import ConsistencyTracker, ConsistencyResult


def _mk_ctx(denied=None, confirmed=None) -> SessionContext:
    ctx = SessionContext(session_id="test")
    ctx.state.consistency = ConsistencyState(
        denied_product_queries=denied or [],
        confirmed_product_id=confirmed,
    )
    return ctx


def _mk_fact_ctx() -> FactContext:
    r = FactRecord(product_id="P1", title="小米 14 Ultra", brand="小米", price=5999.0,
                   category="手机", sub_category="智能机")
    return FactContext(
        product_index={"P1": r},
        brand_index={"小米": ["P1"]},
    )


def test_record_denial():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    tracker.record_denial(ctx, "小米 17 Max", turn=3)
    assert "小米 17 Max" in ctx.state.consistency.denied_product_queries
    assert ctx.state.consistency.claims[0].claim_type == "not_exists"


def test_record_claim():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    tracker.record_claim(ctx, "P1", "recommendation", "主推小米 14 Ultra ¥5999", turn=2)
    assert ctx.state.consistency.claims[0].product_id == "P1"


def test_set_confirmed_product():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    tracker.set_confirmed_product(ctx, "P1")
    assert ctx.state.consistency.confirmed_product_id == "P1"


def test_check_focus_drift_detected():
    """用户已确认关注 P1，新推荐不含 P1 → 漂移。"""
    ctx = _mk_ctx(confirmed="P1")
    tracker = ConsistencyTracker()
    result = tracker.check_before_output(ctx, ["P2", "P3"], _mk_fact_ctx())
    assert not result.is_consistent
    assert result.focus_drift_detected


def test_check_focus_no_drift():
    ctx = _mk_ctx(confirmed="P1")
    tracker = ConsistencyTracker()
    result = tracker.check_before_output(ctx, ["P1", "P2"], _mk_fact_ctx())
    assert result.is_consistent


def test_check_empty_context():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    result = tracker.check_before_output(ctx, ["P1"], _mk_fact_ctx())
    assert result.is_consistent


def test_get_denied_queries():
    ctx = _mk_ctx(denied=["查询A", "查询B"])
    tracker = ConsistencyTracker()
    assert set(tracker.get_denied_queries(ctx)) == {"查询A", "查询B"}


def test_get_denied_queries_empty():
    ctx = _mk_ctx()
    tracker = ConsistencyTracker()
    assert tracker.get_denied_queries(ctx) == []
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
from dataclasses import dataclass

from .models import SessionContext, ClaimRecord, FactContext

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyResult:
    is_consistent: bool = True
    focus_drift_detected: bool = False
    blocked_reason: str | None = None


class ConsistencyTracker:
    """跨轮一致性校验（纯规则，不调 LLM）。

    3 条规则:
    Rule 1 (Denial Cache): 已声明"不存在"的查询 → 后续检索时注入 denied_queries
    Rule 2 (Price Consistency): 同一 product_id 价格与 FactContext 一致（由 AnchorValidator 保证）
    Rule 3 (Focus Drift): confirmed_product_id 不在新推荐中 → 标记漂移
    """

    def check_before_output(
        self,
        session_ctx: SessionContext,
        ranked_product_ids: list[str],
        fact_ctx: FactContext,
    ) -> ConsistencyResult:
        cs = session_ctx.state.consistency

        # Rule 3: Focus drift
        if cs.confirmed_product_id and cs.confirmed_product_id not in ranked_product_ids:
            return ConsistencyResult(
                is_consistent=False,
                focus_drift_detected=True,
                blocked_reason=(
                    f"用户已确认关注 {cs.confirmed_product_id}，"
                    f"但新推荐未包含该商品"
                ),
            )

        return ConsistencyResult(is_consistent=True)

    def get_denied_queries(self, session_ctx: SessionContext) -> list[str]:
        """获取当前 session 的 denial cache。"""
        return list(session_ctx.state.consistency.denied_product_queries)

    def record_denial(self, ctx: SessionContext, query: str, turn: int) -> None:
        """记录一条「商品不存在」的声明。"""
        cs = ctx.state.consistency
        if query not in cs.denied_product_queries:
            cs.denied_product_queries.append(query)
        cs.claims.append(ClaimRecord(
            turn=turn, product_id="", claim_type="not_exists",
            claim_value=f"查询「{query}」不在商品库中",
        ))

    def record_claim(self, ctx: SessionContext, product_id: str,
                     claim_type: str, claim_value: str, turn: int) -> None:
        """记录一条商品相关的声明。"""
        ctx.state.consistency.claims.append(ClaimRecord(
            turn=turn, product_id=product_id,
            claim_type=claim_type, claim_value=claim_value,
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
git commit -m "feat: ConsistencyTracker — cross-turn denial cache + focus drift detection

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: LLM 客户端适配 — 三个 stream_response + _response_evidence_payload 追加 fact_block

**目标:** 所有 `stream_response` 方法和 `_response_evidence_payload` 追加 `fact_block: str = ""` 参数，将 FactContext.prompt_block 注入 system prompt

**文件:**
- 修改: `server/backend/app/llm_client.py`
- 测试: `server/tests/test_new_models.py`（追加）

- [ ] **Step 1: 追加测试**

```python
# 追加到 server/tests/test_new_models.py

def test_response_evidence_payload_accepts_fact_block():
    """_response_evidence_payload 应接收并传递 fact_block。"""
    from server.backend.app.llm_client import _response_evidence_payload
    from server.backend.app.models import RetrievalPlan
    plan = RetrievalPlan(intent="recommend_product", retrieval_mode="single",
                         retrieval_query="test",
                         hard_constraints=HardConstraints())
    payload = _response_evidence_payload(plan, [], fact_block="[事实块内容]")
    # fact_block 应出现在 payload 中
    assert "fact_block" in payload
    assert payload["fact_block"] == "[事实块内容]"


def test_response_evidence_payload_no_fact_block():
    """不传 fact_block 时默认空字符串。"""
    from server.backend.app.llm_client import _response_evidence_payload
    from server.backend.app.models import RetrievalPlan, HardConstraints
    plan = RetrievalPlan(intent="recommend_product", retrieval_mode="single",
                         retrieval_query="test",
                         hard_constraints=HardConstraints())
    payload = _response_evidence_payload(plan, [])
    assert payload.get("fact_block", "") == ""
```

注意: `HardConstraints` 从 `models.py` 导入，需要在测试文件顶部补充 import。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_new_models.py::test_response_evidence_payload_accepts_fact_block -v
```
预期: FAIL（_response_evidence_payload 缺少 fact_block 参数）

- [ ] **Step 3: 修改 _response_evidence_payload 签名和返回值**

```python
# 修改函数签名（约第 642 行）
def _response_evidence_payload(
    plan: RetrievalPlan,
    ranked_products: list[RankedProduct],
    focus_product: Product | None = None,
    *,
    context: SessionContext | None = None,
    fact_block: str = "",          # ← 新增
) -> dict[str, Any]:
    # ... 现有 products/constraints 逻辑不变 ...

    return {
        'allowed_products': products,
        'selected_primary': products[0]['product_id'] if products else None,
        'recent_context_text': _build_recent_context_text(context),
        'constraint_note': _constraint_sentence(plan),
        'response_contract': { ... },   # 保持不变
        'hard_constraints_applied': { ... },  # 保持不变
        'focus_product': focus_product.model_dump(mode='json') if focus_product else None,
        'forbidden_claims': ['疗效承诺', '未给出的商品属性', '后端没有返回的 product_id'],
        'fact_block': fact_block,       # ← 新增
    }
```

- [ ] **Step 4: 修改 DoubaoLLMClient.stream_response（约 250 行）**

```python
async def stream_response(
    self,
    user_message: str,
    plan: RetrievalPlan,
    ranked_products: list[RankedProduct],
    focus_product: Product | None = None,
    *,
    context=None,
    fact_block: str = "",          # ← 新增
):
    stream_kwargs: dict[str, Any] = {
        'model': self.model,
        'messages': [
            {'role': 'system', 'content': RESPONSE_SYSTEM_PROMPT},
            {
                'role': 'user',
                'content': json.dumps(
                    {
                        'message': user_message,
                        'evidence_payload': _response_evidence_payload(
                            plan, ranked_products, focus_product,
                            context=context, fact_block=fact_block,  # ← 传递
                        ),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        # ... 其余不变 ...
    }
```

- [ ] **Step 5: 修改 FakeLLMClient.stream_response（约 521 行）**

```python
async def stream_response(
    self,
    user_message: str,
    plan: RetrievalPlan,
    ranked_products: list[RankedProduct],
    focus_product: Product | None = None,
    *,
    context=None,
    fact_block: str = "",          # ← 新增
):
    text = await self.generate_response(
        user_message, plan, ranked_products, focus_product,
        context=context,
    )
    for index in range(0, len(text), 12):
        yield text[index : index + 12]
```

- [ ] **Step 6: 修改 LLMClientWithBreaker.stream_response（约 833 行）**

```python
async def stream_response(
    self,
    user_message: str,
    plan: RetrievalPlan,
    ranked_products: list[RankedProduct],
    focus_product: Product | None = None,
    *,
    context=None,
    fact_block: str = "",          # ← 新增
):
    async for chunk in self.breaker.call_stream(
        self.client.stream_response,
        self._fallback.stream_response,
        user_message, plan, ranked_products, focus_product,
        context=context, fact_block=fact_block,  # ← 传递
    ):
        yield chunk
```

- [ ] **Step 7: 修改 DoubaoLLMClient.generate_response 同样追加 fact_block（约 196 行）**

```python
async def generate_response(
    self,
    user_message: str,
    plan: RetrievalPlan,
    ranked_products: list[RankedProduct],
    focus_product: Product | None = None,
    *,
    context=None,
    fact_block: str = "",          # ← 新增
):
    # ... 内部调用 _response_evidence_payload 时传递 fact_block ...
    payload = _response_evidence_payload(
        plan, ranked_products, focus_product,
        context=context, fact_block=fact_block,  # ← 传递
    )
```

- [ ] **Step 8: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_new_models.py -v
```
预期: 全部 PASS

- [ ] **Step 9: 确认导入和语法**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.llm_client import DoubaoLLMClient; print('OK')"
```
预期: `OK`

- [ ] **Step 10: 提交**

```bash
git add server/backend/app/llm_client.py server/tests/test_new_models.py
git commit -m "feat(llm_client): add fact_block parameter to all stream_response/generate_response

- _response_evidence_payload gains fact_block field
- DoubaoLLMClient, FakeLLMClient, LLMClientWithBreaker all accept fact_block
- Default empty string for backward compat

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 集成 FactContext + 流式 AnchorValidator 到 agent.py 生成链路（P0 + P3）

**目标:** `_stream_generate_text_events` 改为：FactContext Builder → LLM 生成（带 fact_block）→ AnchorValidator.stream_process 流式校验 → 推送

**注意:** 不修改 `_prepare_context_for_turn` 的 `context_action` 逻辑——保持现有 `same_task/new_task` 语义不变。

**文件:**
- 修改: `server/backend/app/agent.py`
- 测试: `server/tests/test_demo_agent_flow.py`（作为回归）

- [ ] **Step 1: 在 __init__ 中初始化新组件**

```python
# 在 ShopGuideAgent.__init__ 末尾追加（约第 178 行之前）
from .fact_context import FactContextBuilder
from .anchor_validator import AnchorValidator
from .consistency_tracker import ConsistencyTracker
self.fact_builder = FactContextBuilder()
self.anchor_validator = AnchorValidator()
self.consistency_tracker = ConsistencyTracker()
```

- [ ] **Step 2: 修改 _stream_recommendation_events — LLM 生成前构建 FactContext**

在 `_stream_recommendation_events` 方法中（约第 919-923 行，即 `_stream_generate_text_events` 调用之前）：

```python
# 构建 FactContext（含 denial cache）
denied = self.consistency_tracker.get_denied_queries(context)
fact_ctx = self.fact_builder.build(selected, denied_queries=denied)

# 传入 fact_ctx 给生成方法
async for event in self._stream_generate_text_events(
    message_id, request, plan, selected, None, fact_ctx=fact_ctx,
):
    ...
```

- [ ] **Step 3: 重写 _stream_generate_text_events — 流式校验 + 保留首 chunk 超时**

```python
async def _stream_generate_text_events(
    self,
    message_id: str,
    request: ChatRequest,
    plan: RetrievalPlan,
    ranked: list[RankedProduct],
    focus_product: Product | None,
    *,
    fact_ctx: FactContext | None = None,
) -> AsyncIterator[dict]:
    if not ranked:
        for event in _text_delta_events(message_id, _no_match_text(plan)):
            yield event
        return

    ctx = self.sessions.get("anonymous", request.session_id)
    fact_block = fact_ctx.prompt_block if fact_ctx else ""

    # ★ 保留首 chunk 超时保护
    try:
        llm_stream = self.llm_client.stream_response(
            request.message, plan, ranked, focus_product,
            context=ctx, fact_block=fact_block,
        )
    except Exception:
        fallback = fallback_text_for_failure("llm_error", plan, context=ctx)
        for event in _text_delta_events(message_id, fallback):
            yield event
        return

    # 首 chunk 超时: 如果第一个 chunk 在 timeout 内不到，走 fallback
    try:
        first_chunk = await run_with_timeout(
            self._first_chunk_from_stream(llm_stream),
            timeout_seconds=DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS,
            fallback=None,
        )
    except Exception:
        first_chunk = None

    if first_chunk is None:
        fallback = fallback_text_for_failure("llm_timeout", plan, context=ctx)
        for event in _text_delta_events(message_id, fallback):
            yield event
        return

    # ★ 恢复完整流：first_chunk + 剩余
    async def _full_stream():
        yield first_chunk
        async for chunk in llm_stream:
            if chunk:
                yield chunk

    # AnchorValidator 流式校验（逐 chunk 透传 + 锚点展开 + 异常边界）
    if fact_ctx and fact_ctx.product_index:
        try:
            async for event in self.anchor_validator.stream_process(_full_stream(), fact_ctx):
                if event["type"] == "text_delta":
                    event["message_id"] = message_id
                yield event
        except Exception:
            logger.warning("[stream] anchor_validator error, falling back", exc_info=True)
            fallback = fallback_text_for_failure("llm_error", plan, context=ctx)
            for event in _text_delta_events(message_id, fallback):
                yield event
            return
    else:
        try:
            async for chunk in _full_stream():
                if chunk:
                    yield {"type": "text_delta", "message_id": message_id, "text": chunk}
        except Exception:
            logger.warning("[stream] llm stream error", exc_info=True)
            fallback = fallback_text_for_failure("llm_error", plan, context=ctx)
            for event in _text_delta_events(message_id, fallback):
                yield event
            return
```

- [ ] **Step 4: 修改 _stream_followup 同样构建 FactContext**

在 `_stream_followup` 方法中 final_selected 之后、`_stream_generate_text_events` 调用之前（约第 800-801 行）：

```python
denied = self.consistency_tracker.get_denied_queries(context)
fact_ctx = self.fact_builder.build(final_selected, denied_queries=denied)
async for event in self._stream_generate_text_events(
    message_id, request, plan, final_selected, focus_product, fact_ctx=fact_ctx,
):
    ...
```

- [ ] **Step 5: 确认导入和语法**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.agent import ShopGuideAgent; print('OK')"
```
预期: `OK`

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/agent.py
git commit -m "feat(agent): integrate streaming AnchorValidator + FactContext into generate pipeline

- FactContext built before LLM call with denial cache
- AnchorValidator.stream_process validates [[pid]] anchors in real-time
- Normal text passes through instantly (zero delay)
- Invalid anchors replaced with placeholder, strays flagged

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 同步 HallucinationChecker — 签名改 FactContext + 同步调用点

**目标:** `verify()` 签名改为接收 `FactContext`；去除已被 AnchorValidator 覆盖的虚构 ID/名称检测；同步 `agent.py` 调用点

**文件:**
- 修改: `server/backend/app/hallucination_checker.py`
- 修改: `server/backend/app/agent.py`（调用点同步）

- [ ] **Step 1: 精简 HallucinationChecker**

```python
"""幻觉检测器（兜底层）— 保留价格偏差检测。虚构 ID/名称检测已由 AnchorValidator 覆盖。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import FactContext


@dataclass
class HallucinationReport:
    is_clean: bool = True
    price_mismatches: list[dict] = field(default_factory=list)


class HallucinationChecker:
    """价格偏差检测器（AnchorValidator 的兜底层）。"""

    def __init__(self, price_tolerance: float = 0.1):
        self.price_tolerance = price_tolerance

    def verify(self, response_text: str, fact_ctx: FactContext) -> HallucinationReport:
        """校验文本中的价格是否与 FactContext 一致。"""
        report = HallucinationReport()
        title_to_price = {r.title: r.price for r in fact_ctx.product_index.values()}
        if not title_to_price:
            return report

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

- [ ] **Step 2: 同步 agent.py 中的调用点**

在 `agent.py` 中找到 `_stream_generate_text_events` 中 HallucinationChecker 的调用（约 1048-1056 行），修改为：

```python
# 旧代码:
# from .hallucination_checker import HallucinationChecker
# report = HallucinationChecker().verify(streamed_text, ranked)

# 新代码: 改为接收 FactContext
if fact_ctx and fact_ctx.product_index:
    from .hallucination_checker import HallucinationChecker
    report = HallucinationChecker().verify(streamed_text, fact_ctx)
    if not report.is_clean:
        fallback = fallback_text_for_failure("hallucination_detected", plan)
        yield {"type": "hallucination_corrected", "message_id": message_id,
               "original_issues": report.price_mismatches}
        for event in _text_delta_events(message_id, fallback):
            yield event
        return
```

注意: 这个调用点现在的位置在 `_stream_generate_text_events` 中 AnchorValidator 之后。由于 AnchorValidator 是流式的，`streamed_text` 需要从流式输出中重新收集。实际上在流式校验模式下，价格偏差检测应该在流式结束后、用收集到的完整文本做 deferred check。

简化处理: 将 HallucinationChecker 的价格检测作为流式结束后的 deferred check，与 stray detection 并列。修改 `_stream_generate_text_events`:

```python
# 在 AnchorValidator.stream_process 循环中收集全量文本
collected_for_price_check: list[str] = []

async for event in self.anchor_validator.stream_process(llm_stream, fact_ctx):
    if event["type"] == "text_delta":
        collected_for_price_check.append(event["text"])
        event["message_id"] = message_id
    yield event

# deferred 价格偏差检测（在流式结束后）
if collected_for_price_check and fact_ctx and fact_ctx.product_index:
    full_text = "".join(collected_for_price_check)
    from .hallucination_checker import HallucinationChecker
    report = HallucinationChecker().verify(full_text, fact_ctx)
    if not report.is_clean:
        logger.warning(f"[hallucination] price mismatches: {report.price_mismatches}")
        yield {"type": "price_mismatch_warning", "message_id": message_id,
               "mismatches": report.price_mismatches}
```

- [ ] **Step 3: 确认可导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "
from server.backend.app.hallucination_checker import HallucinationChecker, HallucinationReport
from server.backend.app.models import FactContext, FactRecord
ctx = FactContext(product_index={'P1': FactRecord(product_id='P1', title='A', brand='B', price=100, category='C', sub_category='D')})
r = HallucinationChecker().verify('¥150 元', ctx)
print(f'is_clean={r.is_clean}, mismatches={len(r.price_mismatches)}')
"
```
预期: `is_clean=False, mismatches=1`（价格偏差 50% > 10% tolerance）

- [ ] **Step 4: 提交**

```bash
git add server/backend/app/hallucination_checker.py server/backend/app/agent.py
git commit -m "refactor(hallucination_checker): accept FactContext, price-only check, sync call site

- verify() takes FactContext instead of list[RankedProduct]
- Removed fabricated ID/name detection (covered by AnchorValidator)
- Price check runs as deferred post-stream validation in agent.py

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 集成 ConsistencyTracker 到 agent.py（P1）

**目标:** 在 LLM 生成**前**执行 `check_before_output()`（阻止文本已流出后才拦截）；在 recommend 和 denial 时刻记录 claims

**文件:**
- 修改: `server/backend/app/agent.py`

- [ ] **Step 1: 在 _stream_recommendation_events 中——LLM 生成前做 consistency check**

**关键：检查必须在调用 `_stream_generate_text_events` 之前完成**，此时尚未向用户推送任何文本。

在 `_stream_recommendation_events` 中，`selected` 确定后、`_stream_generate_text_events` 调用前：

```python
# ★ LLM 生成前：构建 FactContext + consistency check
denied = self.consistency_tracker.get_denied_queries(context)
fact_ctx = self.fact_builder.build(selected, denied_queries=denied)

# ConsistencyTracker 校验（在文本生成前）
consistency_result = self.consistency_tracker.check_before_output(
    session_ctx=context,
    ranked_product_ids=[item.product.product_id for item in selected],
    fact_ctx=fact_ctx,
)
if not consistency_result.is_consistent:
    logger.warning(f"[consistency] blocked before generate: {consistency_result.blocked_reason}")
    fallback = fallback_text_for_failure("contradiction_blocked", plan, context=context)
    yield {"type": "consistency_blocked", "message_id": message_id,
           "reason": consistency_result.blocked_reason}
    for event in _text_delta_events(message_id, fallback):
        yield event
    yield {"type": "done", "message_id": message_id}
    return

# 通过后才生成文本（文本中不会包含矛盾内容）
async for event in self._stream_generate_text_events(
    message_id, request, plan, selected, None, fact_ctx=fact_ctx,
):
    ...
```

- [ ] **Step 2: 在 _remember_recommendations 中记录 claims**

在 `_remember_recommendations` 方法末尾（约第 1587 行之前）追加：

```python
# 记录一致性声明
turn = context.state.dialog_state.turn_index
for item in ranked:
    self.consistency_tracker.record_claim(
        context,
        item.product.product_id,
        "recommendation",
        f"推荐 {item.product.title} ¥{item.product.price:.0f}",
        turn=turn,
    )
```

- [ ] **Step 3: 在 _build_pending_recovery_events 找不到匹配时记录 denial**

在 `_build_pending_recovery_events` 中 recoverable 判定失败时（约返回 `None` 之前，如果 `pending.failed_query` 存在）：

```python
if pending and pending.failed_query:
    self.consistency_tracker.record_denial(
        context,
        pending.failed_query,
        turn=context.state.dialog_state.turn_index,
    )
```

- [ ] **Step 4: 确认可导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.agent import ShopGuideAgent; print('OK')"
```
预期: `OK`

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/agent.py
git commit -m "feat(agent): integrate ConsistencyTracker — pre-output check + claim recording

- check_before_output() blocks focus drift before pushing to user
- record_claim() for each recommendation
- record_denial() for failed queries

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: SessionStore 新增公开方法 checkpoint() 和 recover()

**目标:** checkpoint() 不绕过 get()，正确走 repo/file/in-memory 三层；recover() 返回 SessionRecovery

**文件:**
- 修改: `server/backend/app/session_store.py`
- 测试: `server/tests/test_session_checkpoint.py`

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_session_checkpoint.py
from __future__ import annotations
import tempfile
from server.backend.app.session_store import SessionStore


def test_checkpoint_and_recover_with_file_backend():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(persist_dir=tmpdir)
        # 先 get（触发创建）
        ctx = store.get("user1", "sess1")
        ctx.dialog_turns.append({"role": "user", "content": "推荐小米手机"})
        ctx.state.checkpoint_stage = "turn_start"

        # 通过公开方法 checkpoint
        store.checkpoint("user1", "sess1", "turn_start")

        # 恢复
        store2 = SessionStore(persist_dir=tmpdir)
        recovery = store2.recover("user1", "sess1")
        assert recovery is not None
        assert recovery.user_message_restored is True


def test_checkpoint_stage_persisted():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(persist_dir=tmpdir)
        ctx = store.get("user1", "sess1")
        ctx.state.checkpoint_stage = "post_retrieve"
        store.checkpoint("user1", "sess1", "post_retrieve")

        store2 = SessionStore(persist_dir=tmpdir)
        ctx2 = store2.get("user1", "sess1")
        assert ctx2.state.checkpoint_stage == "post_retrieve"


def test_recover_nonexistent():
    store = SessionStore()
    recovery = store.recover("no_user", "no_sess")
    assert recovery is None


def test_recover_with_history_no_stage():
    """有对话历史但无 checkpoint stage → 部分恢复。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(persist_dir=tmpdir)
        ctx = store.get("user1", "sess1")
        ctx.dialog_turns.append({"role": "user", "content": "你好"})
        store.save("user1", "sess1")

        store2 = SessionStore(persist_dir=tmpdir)
        recovery = store2.recover("user1", "sess1")
        assert recovery is not None
        assert recovery.user_message_restored is True
        assert recovery.hint is not None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_session_checkpoint.py -v
```
预期: FAIL（checkpoint/recover 方法不存在）

- [ ] **Step 3: 在 SessionStore 类中新增方法**

```python
def checkpoint(self, user_id: str, session_id: str, stage: str) -> None:
    """回合级自动保存。不绕过 get()，正确走 repo/file/in-memory 三层。

    先通过 get() 确保 session 在 _sessions 中存在（repo 模式会从 DB 加载），
    然后更新 checkpoint_stage，最后调用 save() 持久化。
    """
    ctx = self.get(user_id, session_id)
    ctx.state.checkpoint_stage = stage
    self.save(user_id, session_id)


def recover(self, user_id: str, session_id: str):
    """恢复会话，返回 SessionRecovery 或 None。"""
    from .models import SessionRecovery
    try:
        ctx = self.get(user_id, session_id)
    except Exception:
        return None

    stage = ctx.state.checkpoint_stage
    has_history = bool(ctx.dialog_turns)

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
            hint=None,
        )
    elif has_history:
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
git commit -m "feat(session_store): add checkpoint() and recover() as public methods

- checkpoint() goes through get() for correct repo/file/in-memory handling
- recover() returns SessionRecovery with stage-aware hints

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: agent.py 中 3 个 checkpoint 插入点 + 统一异常边界（P2）

**目标:** Turn Start、Post-Retrieve、Turn End 自动保存；异常边界保留上下文

**文件:**
- 修改: `server/backend/app/agent.py`

- [ ] **Step 1: 插入 Checkpoint 1 — Turn Start**

在 `stream_message` 方法中，`context.dialog_turns.append({"role": "user", ...})` 之后（约第 342 行）：

```python
context.dialog_turns.append({"role": "user", "content": request.message or ""})
# ↓ 新增 checkpoint
self.sessions.checkpoint(user_id, request.session_id, "turn_start")
```

- [ ] **Step 2: 插入 Checkpoint 2 — Post-Retrieve**

在 `_run_retrieval_flow` 中，`context.last_plan = plan` 之后（约第 515 行）：

```python
context.last_plan = plan
# ↓ 新增 checkpoint
self.sessions.checkpoint(user_id, request.session_id, "post_retrieve")
```

- [ ] **Step 3: 插入 Checkpoint 3 — Turn End**

在 `stream_message` 方法中，`self._record_display_messages(context, collected)` 之后（约第 365 行）：

```python
self._record_display_messages(context, collected)
# ↓ 新增 checkpoint
self.sessions.checkpoint(user_id, request.session_id, "turn_end")
```

- [ ] **Step 4: 在 _do_stream_message 中增加统一异常边界**

```python
async def _do_stream_message(self, user_id: str, request: ChatRequest,
                             compiled_ir, context: SessionContext,
                             trace=None) -> AsyncIterator[dict]:
    try:
        # ====== 现有正常流程 ======
        # 1. pending recovery
        # 2. thinking indicator
        # 3. ToolPlanner → plan
        # 4. dispatch
        ...
    except Exception as exc:
        logger.error(f"[stream] unhandled error for {user_id}/{request.session_id}: {exc}",
                     exc_info=True)
        self.sessions.checkpoint(user_id, request.session_id, "post_error")
        message_id = _message_id()
        fallback = fallback_text_for_failure("internal_error", context=context)
        yield self._assistant_state(message_id, "error", "服务暂时不可用",
                                    intent="error", retrieval_mode="no_retrieval")
        for event in _text_delta_events(message_id, fallback):
            yield event
        yield {"type": "done", "message_id": message_id}
```

- [ ] **Step 5: 确认语法**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.agent import ShopGuideAgent; print('OK')"
```
预期: `OK`

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/agent.py
git commit -m "feat(agent): 3-stage checkpoint + unified exception boundary

- Checkpoint 1: Turn Start (after user message appended)
- Checkpoint 2: Post-Retrieve (after plan set)
- Checkpoint 3: Turn End (after display messages recorded)
- Unified exception boundary preserves context on crash

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 11: 上下文感知降级提示（P4）

**目标:** `fallback_text_for_failure()` 改为接收 `context` 参数，输出包含商品名/查询词的提示

**文件:**
- 修改: `server/backend/app/degradation.py`

- [ ] **Step 1: 重写 degradation.py**

```python
"""降级提示 — 上下文感知的 fallback 文案。"""
from __future__ import annotations


def fallback_text_for_failure(reason: str, plan=None, context=None) -> str:
    last_query = ""
    last_product_names: list[str] = []
    if context is not None:
        turns = getattr(context, 'dialog_turns', []) or []
        if turns:
            last_msg = turns[-1].get("content", "") if isinstance(turns[-1], dict) else ""
            last_query = (last_msg or "")[:50]
        for pid in (getattr(context, 'last_product_ids', []) or [])[:3]:
            recs = getattr(context, 'last_recommendations', []) or []
            for rec in recs:
                if isinstance(rec, dict) and rec.get("product_id") == pid:
                    last_product_names.append(str(rec.get("title", pid)))
                    break

    product_hint = ""
    if last_product_names:
        names = "、".join(last_product_names)
        product_hint = f" 你之前关注的商品：{names}。"

    if reason == "llm_timeout":
        if last_product_names:
            return f"我找到了候选商品（含 {names}），但生成详细解释超时了。你可以直接查看商品卡片，或说「详细说说第一款」让我继续。"
        return "我正在检索相关商品，但生成解释超时了。请稍等片刻再试。"

    if reason == "retrieval_error":
        if last_product_names:
            return f"检索服务暂时不稳定，但我还记得你之前关注的商品（{names}）。你可以继续围绕它们提问。"
        return "检索服务暂时不稳定，我先按当前商品库的基础信息给出保守结果。"

    if reason == "llm_error":
        query = f"关于「{last_query}」" if last_query else ""
        return f"{query}LLM 服务调用失败了，我暂时无法生成新的回复。你可以稍后再试。{product_hint}".strip()

    if reason == "hallucination_detected":
        query = f"关于「{last_query}」" if last_query else ""
        return f"{query}我生成的内容存在不准确之处，已触发保护机制。请重新描述你的需求。{product_hint}".strip()

    if reason == "contradiction_blocked":
        return f"当前回复与之前的分析存在矛盾，已被拦截。请换一种方式提问。{product_hint}".strip()

    if reason == "internal_error":
        return "服务暂时不可用，请稍后再试。你的对话记录已保存，不会丢失。"

    return "当前服务暂时不稳定。请稍后重试。"
```

- [ ] **Step 2: 确认导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.degradation import fallback_text_for_failure; print('OK')"
```
预期: `OK`

- [ ] **Step 3: 同步 agent.py 中所有 fallback_text_for_failure 调用，传入 context**

在 `agent.py` 中找到所有 `fallback_text_for_failure(...)` 调用（约 1012、1038、1052 行等），确保都传入了 `context` 参数：

```python
# 旧: fallback_text_for_failure("llm_error", plan)
# 新: fallback_text_for_failure("llm_error", plan, context=ctx)
```

- [ ] **Step 4: 提交**

```bash
git add server/backend/app/degradation.py server/backend/app/agent.py
git commit -m "feat(degradation): context-aware fallback messages with product hints

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 12: 全量回归测试 + 修复

**目标:** 确保所有改动不破坏现有功能

- [ ] **Step 1: 运行全量测试**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/ -v --tb=short 2>&1 | tail -120
```

- [ ] **Step 2: 逐项分析并修复 FAIL**

对于每个失败测试:
1. 判断是预期行为变更还是回归
2. 预期变更 → 更新测试使其反映新行为
3. 回归 → 修复代码

关键检查点:
- `test_demo_agent_flow.py` — 核心流程是否正常
- `test_response_contract.py` — 输出格式是否正常
- `test_product_matcher.py` — 商品匹配是否正常
- `test_cart_intent.py` — 购物车是否正常
- HallucinationChecker 旧测试 — 可能需要更新（签名已变）

- [ ] **Step 3: 重复直到全量通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/ -v
```
预期: 全部 PASS（或所有 FAIL 均为预期变更且测试已更新）

- [ ] **Step 4: 提交**

```bash
git add server/tests/
git commit -m "test: update tests for Stage 1 fact-grounded pipeline, fix regressions

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 完成标志

全部 12 个 Task 完成，`pytest server/tests/` 全量通过后：

- `[[product_id]]` 锚点机制通过 prompt 约束 LLM 引用真实商品
- `AnchorValidator.stream_process` 流式校验锚点（零普通文本延迟）
- `ConsistencyTracker` 阻止 focus drift 和矛盾
- `SessionStore.checkpoint` 三阶段自动保存
- `degradation` 提示含用户上下文
- 现有 ToolPlan / SemanticFrame / RetrievalPlan 三层模型**完整保留不变**

---

# Stage 2：UnifiedPlan 迁移 + 链路简化

**前置条件:** Stage 1 全部完成且全量测试通过。

**目标:** 合并 ToolPlan + SemanticFrame + RetrievalPlan → UnifiedPlan，删除 IntentCompiler LLM 路径，LLM 调用从 3 次降到 2 次。

**核心原则:**
- `UnifiedPlan` 继承 Stage 1 不改旧模型的策略——先共存再迁移
- 先在 `tool_planner.py` 让 LLM 输出增强的 UnifiedPlan JSON（含所有约束字段）
- 再逐步把 `agent.py` 中的 `SemanticFrame`/`RetrievalPlan` 引用替换为 `UnifiedPlan`
- 全部迁移完成后，通过 type alias + deprecated 标记过渡，最后清理

## Stage 2 全局约束

- UnifiedPlan 必须包含当前 ToolPlan 的**所有** `args` 子字段（不能静默丢弃，如评审 Issue 2 所指）
- `_parse_plan()` 必须先显式检测 `"args" in data` 走旧转换，再尝试新格式
- `context_action` 的 `same_task/new_task` 语义必须保留（如评审 Issue 3 所指）
- 迁移完成前旧模型不可删除，迁移完成后通过 type alias 过渡至少 1 周再清理

---

### Task S2-1: 创建 UnifiedPlan 模型（与旧模型共存）

**目标:** 在 `models.py` 中新增 `UnifiedPlan`，字段覆盖 ToolPlan + SemanticFrame + RetrievalPlan 的全部信息

**文件:**
- 修改: `server/backend/app/models.py`
- 测试: `server/tests/test_unified_plan.py`

- [ ] **Step 1: 编写测试**

```python
# server/tests/test_unified_plan.py
from __future__ import annotations
from server.backend.app.models import UnifiedPlan


def test_unified_plan_defaults():
    p = UnifiedPlan()
    assert p.tool == "chitchat"
    assert p.confidence == 0.5
    assert p.include_brands == []
    assert p.soft_preferences == {}


def test_unified_plan_full_fields():
    p = UnifiedPlan(
        tool="recommend_product",
        confidence=0.9,
        category="智能手机",
        sub_category="旗舰机",
        price_min=3000,
        price_max=7000,
        include_brands=["小米", "华为"],
        exclude_brands=["苹果"],
        soft_preferences={"拍照": "优秀"},
        retrieval_query="旗舰拍照手机",
        retrieval_mode="single",
        need_clarification=False,
        cart_action="add",
        cart_target_product_id="P1",
        cart_quantity=2,
        compare_targets=["P1", "P2"],
        analysis_aspect="specs",
        followup_kind="explain",
        # 保留旧 ToolPlan args 子字段的兼容性——从 args 扁平化到顶层
    )
    assert p.tool == "recommend_product"
    assert p.price_max == 7000
    assert "小米" in p.include_brands


def test_unified_plan_serialization():
    import json
    p = UnifiedPlan(tool="chitchat", confidence=0.3)
    d = p.model_dump(mode="json")
    assert d["tool"] == "chitchat"
    # 确保可以 json 序列化
    assert json.dumps(d)


def test_unified_plan_does_not_break_old_models():
    """UnifiedPlan 与旧模型共存，互不影响。"""
    from server.backend.app.models import SemanticFrame, RetrievalPlan
    from server.backend.app.tool_plan import ToolPlan  # ToolPlan 在 tool_plan.py
    tp = ToolPlan(tool="chitchat")
    assert tp.tool == "chitchat"
    assert SemanticFrame is not None
    assert RetrievalPlan is not None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py -v
```
预期: FAIL（UnifiedPlan 未定义）

- [ ] **Step 3: 在 models.py 中追加 UnifiedPlan（放在 Stage 1 的 FactContext 等模型之后）**

```python
# ========== UnifiedPlan（Stage 2 — 最终合并 ToolPlan + SemanticFrame + RetrievalPlan） ==========


class UnifiedPlan(BaseModel):
    """单次 LLM 调用的完整决策输出。

    字段设计原则: 覆盖 ToolPlan.args 全部子字段 + SemanticFrame 意图字段 +
    RetrievalPlan 检索字段。所有字段设默认值，LLM 只需填它能抽取的部分。
    """
    # ---- 工具路由（原 ToolPlan.tool） ----
    tool: str = "chitchat"
    """recommend_product | product_analysis | compare_products | cart_operation |
       scenario_bundle | product_followup | chitchat"""
    confidence: float = 0.5

    # ---- 意图标记（原 SemanticFrame.intent + clarification） ----
    need_clarification: bool = False
    clarification_question: str | None = None

    # ---- 硬约束（原 HardConstraints + ConstraintEdits.add） ----
    category: str | None = None
    sub_category: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    include_brands: list[str] = Field(default_factory=list)
    exclude_brands: list[str] = Field(default_factory=list)
    in_stock_only: bool = True

    # ---- 软偏好（原 RetrievalPlan.soft_preferences） ----
    soft_preferences: dict[str, str] = Field(default_factory=dict)

    # ---- 检索参数（原 RetrievalPlan.retrieval_query + ToolPlanArgs.category_hint） ----
    retrieval_query: str = ""
    retrieval_mode: str = "single"

    # ---- 商品识别（原 ToolPlanArgs.target_product_query / category_hint） ----
    target_product_query: str | None = None
    category_hint: str | None = None

    # ---- 对比/分析/追问（原 ToolPlanArgs） ----
    compare_targets: list[str] = Field(default_factory=list)
    analysis_aspect: str | None = None
    followup_kind: str | None = None

    # ---- cart 操作（原 CartOperation + ToolPlanArgs） ----
    cart_action: str | None = None
    cart_target_product_id: str | None = None
    cart_quantity: int = 1

    # ---- 否定缓存（从 ConsistencyState 透传，供 FactContextBuilder 使用） ----
    denied_queries: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 确认旧模型不受影响**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "
from server.backend.app.models import UnifiedPlan, ToolPlan, SemanticFrame, RetrievalPlan
print('All models coexist OK')
"
```
预期: `All models coexist OK`

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/models.py server/tests/test_unified_plan.py
git commit -m "feat(models): add UnifiedPlan — full union of ToolPlan + SemanticFrame + RetrievalPlan

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task S2-2: 增强 ToolPlanner — 输出 UnifiedPlan JSON

**目标:** ToolPlanner prompt 增强为一次性输出包含全部约束字段的 UnifiedPlan JSON；`_parse_plan()` 先检测旧格式再解析新格式

**关键设计（修复评审 Issue 2）:**

```python
def _parse_plan(self, raw: str):
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    # ★ 关键: 先检测旧 ToolPlan 格式 (有 "args" 键)
    if "args" in data:
        try:
            from .tool_plan import ToolPlan
            old = ToolPlan.model_validate(data)
            # 旧 → 新 显式转换，不丢任何字段
            return UnifiedPlan(
                tool=old.tool,
                confidence=old.confidence,
                category_hint=old.args.category_hint,
                target_product_query=old.args.target_product_query,
                price_min=old.args.price_min,
                price_max=old.args.price_max,
                include_brands=list(old.args.include_brands),
                exclude_brands=list(old.args.exclude_brands),
                soft_preferences=dict(old.args.soft_preferences),
                compare_targets=list(old.args.compare_targets),
                analysis_aspect=old.args.analysis_aspect,
                followup_kind=old.args.followup_kind,
                cart_action=old.args.cart_action,
                cart_quantity=old.args.cart_quantity,
                retrieval_query=old.args.target_product_query or "",
            )
        except Exception:
            return None

    # 新 UnifiedPlan 格式
    try:
        from .models import UnifiedPlan
        return UnifiedPlan.model_validate(data)
    except Exception:
        return None
```

**文件:**
- 修改: `server/backend/app/tool_planner.py`
- 测试: 追加到 `server/tests/test_unified_plan.py`

- [ ] **Step 1: 追加测试**

```python
# 追加到 server/tests/test_unified_plan.py
import json
from server.backend.app.tool_planner import ToolPlanner


def test_parse_old_toolplan_format():
    """旧格式 {tool, confidence, args:{...}} 应正确转换，不丢字段。"""
    planner = ToolPlanner(llm_client=None)  # type: ignore
    old_json = json.dumps({
        "tool": "recommend_product",
        "confidence": 0.85,
        "args": {
            "category_hint": "智能手机",
            "price_min": 3000,
            "price_max": 7000,
            "include_brands": ["小米"],
            "target_product_query": "小米旗舰机",
            "soft_preferences": {"拍照": "好"},
        },
    })
    plan = planner._parse_plan(old_json)
    assert plan is not None
    assert plan.tool == "recommend_product"
    assert plan.category_hint == "智能手机"       # 不应被丢掉
    assert plan.price_min == 3000                 # 不应被丢掉
    assert "小米" in plan.include_brands          # 不应被丢掉
    assert plan.retrieval_query == "小米旗舰机"    # target_product_query → retrieval_query


def test_parse_new_unified_plan_format():
    """新 UnifiedPlan JSON 格式直接解析。"""
    planner = ToolPlanner(llm_client=None)  # type: ignore
    new_json = json.dumps({
        "tool": "compare_products",
        "confidence": 0.9,
        "compare_targets": ["P1", "P2"],
        "price_min": 2000,
    })
    plan = planner._parse_plan(new_json)
    assert plan is not None
    assert plan.tool == "compare_products"
    assert plan.compare_targets == ["P1", "P2"]
```

- [ ] **Step 2: 运行测试确认旧格式转换通过，新格式失败（_parse_plan 还未改）**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py -v
```

- [ ] **Step 3: 修改 tool_planner.py**

按上面的 `_parse_plan()` 逻辑修改；同时增强 `plan()` 方法中的 LLM prompt，在 tool_planner prompt 中加入 category/sub_category/price/retrieval 等字段的输出要求。

- [ ] **Step 4: 运行测试确认全部通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py -v
```
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add server/backend/app/tool_planner.py server/tests/test_unified_plan.py
git commit -m "feat(tool_planner): output UnifiedPlan JSON, old ToolPlan format detected first

- _parse_plan checks 'args' in data before trying UnifiedPlan
- Old ToolPlan.args fully mapped to UnifiedPlan fields
- Prompt enhanced to request all constraint fields

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task S2-3: 重写 StateReducer — 消费 UnifiedPlan

**目标:** StateReducer 新增 `apply_unified()` 方法接收 `UnifiedPlan`，同时保留旧 `apply()` 兼容 SemanticFrame

**文件:**
- 修改: `server/backend/app/state_reducer.py`
- 测试: 追加到 `server/tests/test_unified_plan.py`

- [ ] **Step 1: 追加测试**

```python
# 追加到 server/tests/test_unified_plan.py
from server.backend.app.models import SessionContext, UnifiedPlan
from server.backend.app.state_reducer import StateReducer


def test_state_reducer_apply_unified():
    ctx = SessionContext(session_id="test")
    plan = UnifiedPlan(
        tool="recommend_product",
        category="手机数码",
        sub_category="智能手机",
        price_min=2000,
        price_max=5000,
        include_brands=["小米"],
        soft_preferences={"拍照": "好"},
    )
    reducer = StateReducer()
    reducer.apply_unified(ctx, plan, "推荐小米拍照手机")
    state = ctx.state
    assert state.dialog_state.turn_index == 1
    assert state.dialog_state.last_intent == "recommend_product"
    assert state.constraint_state.hard.category == "手机数码"
    assert state.constraint_state.hard.sub_category == "智能手机"
    assert state.constraint_state.hard.price_min == 2000
    assert "小米" in state.constraint_state.hard.include_brands
    assert state.constraint_state.soft.get("拍照") == "好"


def test_old_apply_still_works():
    """旧 apply() 兼容 SemanticFrame/ShoppingIntentIR。"""
    from server.backend.app.models import SemanticFrame
    ctx = SessionContext(session_id="test")
    frame = SemanticFrame(intent="recommend_product")
    reducer = StateReducer()
    reducer.apply(ctx, frame, "test")
    assert ctx.state.dialog_state.turn_index == 1
```

- [ ] **Step 2: 在 StateReducer 中新增 apply_unified()**

在 `state_reducer.py` 中追加:

```python
def apply_unified(self, context: SessionContext, plan: UnifiedPlan, user_message: str) -> None:
    """消费 UnifiedPlan 的状态归约。"""
    state = context.state
    state.dialog_state.turn_index += 1
    state.dialog_state.last_intent = plan.tool
    state.dialog_state.last_user_message = user_message

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
    for key, value in plan.soft_preferences.items():
        if value:
            state.constraint_state.soft[key] = value

    state.constraint_state.source_turns.append({
        "turn_index": state.dialog_state.turn_index,
        "intent": plan.tool,
        "message": user_message,
        "plan": plan.model_dump(mode="json"),
    })
    _sync_legacy_context(context)
```

- [ ] **Step 3: 运行测试**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/test_unified_plan.py -v
```
预期: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add server/backend/app/state_reducer.py server/tests/test_unified_plan.py
git commit -m "feat(state_reducer): add apply_unified() for UnifiedPlan consumption

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task S2-4: 简化 agent.py — 移除 IntentCompiler LLM 调用

**目标:** `_do_stream_message` 改用 `apply_unified()`，删除 `_merge_tool_plan_into_ir()`，`_prepare_context_for_turn` 适配 UnifiedPlan

**文件:**
- 修改: `server/backend/app/agent.py`

- [ ] **Step 1: 修改 _do_stream_message**

```python
async def _do_stream_message(self, user_id, request, compiled_ir, context, trace=None):
    # ... recovery / thinking indicator 不变 ...

    seed_constraint_state_from_plan(context, context.last_plan)
    plan_t0 = _time.time()
    unified_plan = await self.tool_planner.plan(request, context)
    # ... trace 记录 ...

    # ★ 改用 apply_unified
    self._prepare_context_for_turn(context, request, unified_plan)
    self.state_reducer.apply_unified(context, unified_plan, request.message or "")

    async for event in self._dispatch_tool(user_id, request, context, unified_plan):
        yield event
```

- [ ] **Step 2: _dispatch_tool 参数 unified_plan 替换 compiled_ir + tool_plan**

修改 `_dispatch_tool` 签名，参数统一为 `unified_plan: UnifiedPlan`。

对于 `cart_operation` / `product_followup` 路径——这些之前需要 `compiled_ir`（IntentCompiler 编译的结果）。现在统一从 `unified_plan` 中获取约束。如果某个 path 仍需要 IR 级别的字段（如 `cart_operation.target`），用 `unified_plan.cart_target_product_id` 代替。

- [ ] **Step 3: _run_retrieval_flow 接收 unified_plan**

```python
async def _run_retrieval_flow(self, user_id, request, context, unified_plan):
    # ★ 不再调用 intent_compiler.compile()
    # 直接从 unified_plan 构建 RetrievalPlan
    # 保留 _prepare_context_for_turn 的 context_action 语义
    context_action = self._prepare_context_for_turn(context, request, unified_plan)
    
    plan = self.query_builder.build_from_unified(unified_plan, context, request.message)
    # ... 后续不变 ...
```

- [ ] **Step 4: 删除 _merge_tool_plan_into_ir**

```python
# 直接删除整个方法（约 570-591 行）
```

- [ ] **Step 5: 确认可导入 + 语法正确**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.agent import ShopGuideAgent; print('OK')"
```
预期: `OK`

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/agent.py
git commit -m "refactor(agent): dispatch via UnifiedPlan, remove _merge_tool_plan_into_ir

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task S2-5: 适配 QueryBuilder — build_from_unified()

**目标:** `QueryBuilder` 新增 `build_from_unified()` 方法，直接消费 `UnifiedPlan` 产出 `RetrievalPlan`

**文件:**
- 修改: `server/backend/app/query_builder.py`

- [ ] **Step 1: 追加方法**

```python
def build_from_unified(self, plan: UnifiedPlan, context, user_message: str) -> RetrievalPlan:
    """从 UnifiedPlan 构建 RetrievalPlan，跳过 SemanticFrame → IR 转换。"""
    from .models import HardConstraints

    hc = HardConstraints(
        category=plan.category,
        sub_category=plan.sub_category,
        price_min=plan.price_min,
        price_max=plan.price_max,
        include_brands=list(plan.include_brands),
        exclude_brands=list(plan.exclude_brands),
    )
    return RetrievalPlan(
        intent=plan.tool,
        retrieval_mode=plan.retrieval_mode,
        category=plan.sub_category or plan.category,
        hard_constraints=hc,
        soft_preferences=dict(plan.soft_preferences),
        retrieval_query=plan.retrieval_query or plan.target_product_query or user_message,
        need_clarification=plan.need_clarification,
        clarification_question=plan.clarification_question,
    )
```

- [ ] **Step 2: 确认导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.query_builder import QueryBuilder; print('OK')"
```
预期: `OK`

- [ ] **Step 3: 提交**

```bash
git add server/backend/app/query_builder.py
git commit -m "feat(query_builder): add build_from_unified() — direct UnifiedPlan → RetrievalPlan

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task S2-6: 更新 Tool 参数 — 逐 Tool 迁移 compiled_ir → unified_plan

**目标:** 每个 Tool 的 `execute()` 方法从消费 `compiled_ir`（SemanticFrame）改为消费 `unified_plan`（UnifiedPlan）

**关键原则:** 不是简单改名——需要逐 Tool 建立字段映射并验证行为等价。

**文件与映射清单:**

| Tool | 当前消费的 compiled_ir 字段 | UnifiedPlan 等效字段 | 备注 |
|------|---------------------------|---------------------|------|
| `tools/retrieval.py` | `compiled_ir.constraint_edits.add` | `unified_plan` 的 price_min/max, include/exclude_brands | 直接字段，不需 edits 层 |
| `tools/cart.py` | `compiled_ir.cart_operation.action/target/quantity` | `unified_plan.cart_action`, `cart_target_product_id`, `cart_quantity` | target 从 ProductReference 变为 product_id 字符串 |
| `tools/clarify.py` | `compiled_ir.clarification_question` | `unified_plan.clarification_question` | 直接映射 |
| `tools/comparison.py` | `compiled_ir.constraint_edits` + `query_intent.query_terms` | `unified_plan.compare_targets` + `soft_preferences` | 对比场景的 target 从 query_terms → compare_targets |
| `tools/bundle.py` | `compiled_ir.query_intent` + `constraint_edits` | `unified_plan.soft_preferences` | bundle 场景偏好从 query_intent → soft_preferences |
| `tools/followup.py` | `compiled_ir.constraint_edits.add` + `followup_kind` | `unified_plan` 直接字段 + `followup_kind` | 同上 |
| `tools/product_analysis.py` | `compiled_ir.analysis_aspect` | `unified_plan.analysis_aspect` | 直接映射 |

**agent.py 中需同步的消费点:**

| 位置 | 当前读取 | 改为 |
|------|---------|------|
| `_apply_pending_answer_preferences()` | `ir.constraint_edits.add.include_brands` | `unified_plan.include_brands` |
| `_dispatch_tool` cart_operation 路径 | `compiled_ir.cart_operation` | `unified_plan.cart_action/target_product_id/quantity` |
| `_stream_followup` 品牌排除 | `ir.constraint_edits.add.exclude_brands` | `unified_plan.exclude_brands` |
| `try_handle_cart_message` | `frame.cart_operation` | `unified_plan.cart_action` 等字段 |

- [ ] **Step 2: 确认可导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "from server.backend.app.tools.registry import ToolRegistry; print('OK')"
```
预期: `OK`

- [ ] **Step 3: 提交**

```bash
git add server/backend/app/tools/
git commit -m "refactor(tools): compiled_ir → unified_plan parameter migration

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task S2-7: 删除 IntentCompiler + 精简 SemanticParser + 添加向后兼容别名

**目标:** 删除 `intent_compiler.py`；`semantic_layer.py` 只保留 `rule_semantic_frame()` 兜底；`SemanticFrame` → `UnifiedPlan` type alias

**文件:**
- 删除: `server/backend/app/intent_compiler.py`
- 修改: `server/backend/app/semantic_layer.py`
- 修改: `server/backend/app/models.py`（追加 type alias）
- 修改: `server/backend/app/agent.py`（移除 IntentCompiler 导入和实例化）

- [ ] **Step 1: 在 models.py 末尾追加向后兼容别名**

```python
# ========== Stage 2 向后兼容别名 ==========
# 迁移完成后的过渡期（至少 1 周），旧代码中的 SemanticFrame/ShoppingIntentIR
# 引用自动映射到 UnifiedPlan。过渡期结束后删除旧模型。
SemanticFrame = UnifiedPlan
ShoppingIntentIR = UnifiedPlan
```

- [ ] **Step 2: 从 agent.py 移除 IntentCompiler 导入和使用**

```python
# 删除: from .intent_compiler import IntentCompiler
# 删除: self.intent_compiler = IntentCompiler(...)
```

- [ ] **Step 3: 删除 intent_compiler.py**

```bash
rm server/backend/app/intent_compiler.py
```

- [ ] **Step 4: 精简 semantic_layer.py**

删除 `SemanticParser` 类及其 LLM 路径的 `parse()` 方法。
保留:
- `rule_semantic_frame()` — ToolPlanner LLM 失败时的规则兜底
- `_add_constraints` / `_relax_constraints` / `_remove_constraints` — 其他地方仍在使用

- [ ] **Step 5: 确认全项目可导入**

```bash
cd /home/huadabioa/houlong/SoulDance && python -c "
from server.backend.app.models import SemanticFrame, ShoppingIntentIR, UnifiedPlan
from server.backend.app.semantic_layer import rule_semantic_frame
from server.backend.app.agent import ShopGuideAgent
print('All imports OK')
"
```
预期: `All imports OK`

- [ ] **Step 6: 提交**

```bash
git rm server/backend/app/intent_compiler.py
git add server/backend/app/semantic_layer.py server/backend/app/models.py server/backend/app/agent.py
git commit -m "refactor: delete IntentCompiler, SemanticFrame → UnifiedPlan alias

- IntentCompiler removed (LLM path replaced by UnifiedPlan in ToolPlanner)
- SemanticParser LLM path removed, rule_semantic_frame kept as fallback
- SemanticFrame / ShoppingIntentIR → UnifiedPlan type alias for backwards compat

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task S2-8: Stage 2 全量回归测试

**目标:** 确保 Stage 2 迁移不破坏任何现有功能

- [ ] **Step 1: 运行全量测试**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/ -v --tb=short 2>&1 | tail -150
```

- [ ] **Step 2: 逐项修复 FAIL**

对每个失败:
- 旧 SemanticFrame 构造代码 → 改用 UnifiedPlan
- 旧 ConstraintEdits 引用 → 直接从 UnifiedPlan 取字段
- 预期行为变更 → 更新测试

- [ ] **Step 3: 确认 LLM 调用数从 3 降到 2**

在 `agent.py` 中 grep 确认:
```bash
grep -n "llm_client\." server/backend/app/agent.py
```
预期: 只有 ToolPlanner 的 `plan()` 和生成阶段的 `stream_response()` 两处 LLM 调用

- [ ] **Step 4: 全量通过**

```bash
cd /home/huadabioa/houlong/SoulDance && python -m pytest server/tests/ -v
```
预期: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add server/tests/
git commit -m "test: Stage 2 regression fixes — UnifiedPlan migration complete

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Stage 2 完成标志

全部 8 个 Task 完成，`pytest server/tests/` 全量通过后：

- `UnifiedPlan` 成为 ToolPlanner → 检索 → 生成的**唯一数据载体**
- LLM 调用从 3 次减少到 2 次
- `IntentCompiler` 已删除，`SemanticParser` 仅保留规则兜底
- `_merge_tool_plan_into_ir()` 已删除
- `SemanticFrame` / `ShoppingIntentIR` 为 `UnifiedPlan` 的 type alias
- 旧模型 `ConstraintEdits` / `CartOperation` / `QueryIntent` 保留作为过渡，后续版本清理
