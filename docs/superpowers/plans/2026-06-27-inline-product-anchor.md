# Inline Product Anchor — 聊天消息内嵌商品锚点重构

## 设计原则（最高优先级）

```
┌──────────────────────────────────────────────────────────────────┐
│  前端所有 AI 消息中的商品呈现，统一为：                            │
│  [[商品名#product_id]] 可点击锚点 +                               │
│  点击展开 ProductDetailSheet（ModalBottomSheet）                  │
│                                                                  │
│  适用范围：推荐、对比、Bundle、追问——全覆盖。                      │
│  不再使用独立的 ProductCarousel / HeroProductCard                 │
│  / AlternativeProductCarousel 插入消息流。                       │
└──────────────────────────────────────────────────────────────────┘
```

无论后端走的是推荐、对比、还是 Bundle 场景组合，只要消息中出现商品名，前端就必须以锚点渲染，点击统一走 `ProductDetailSheet`。

---

## Context

当前 APP 中，AI 推荐的商品以独立大卡片（`HeroProductCard` + `AlternativeProductCarousel`）插入消息流，与文本段落分离，视觉上厚重、破坏对话阅读节奏。需要参照豆包 AI 的嵌入方式，改为文本内可点击锚点 + 局部展开的交互形态。

**涉及端：** 后端（在文本中产出 `[[name#id]]` 锚点标记）+ 前端（事件接收 + 解析 + 渲染 + `ProductDetailSheet` 交互）

**目标平台：** 纯 Android（`com.example.shopguideagent`），不涉及桌面端。

---

### 现状关键事实（实现前必读，避免踩坑）

**三种流程的文本来源不同，锚点实施策略也不同：**

| 流程 | 文本来源 | 文本/商品时序 | 锚点怎么来 | 代码入口 |
|------|---------|-------------|-----------|---------|
| **推荐** | LLM 流式生成 | text_delta **全部结束后**才发 products_start / product_item（串行） | 通过 `response.txt` prompt 让 LLM 输出 `[[name#id]]` | `_stream_recommendation_events` / `_stream_generate_text_events` (agent.py:730-744) |
| **对比** | 服务端模板拼接 (`compose_markdown_sections`) | 文本事件在前，comparison_result 在后 | **直接在模板中写** `[[name#id]]` | `agent.py:_build_comparison_events` (line 1026) |
| **Bundle** | intro 服务端模板拼接；商品通过 `bundle_item` 事件发送 | intro text → bundle_start → bundle_item × N → bundle_done | intro 模板注入锚点 + 前端 `BundleGroupCard` 商品名改为锚点 | `agent.py:_build_bundle_events` (line 1111) |

**关键事实：**

1. 推荐流程：回复正文由 **LLM 流式生成**（`_text_delta_events` 逐 chunk 吐 `text_delta`），商品数据由后端**独立生成** `product_item` 事件。text 和 product 是**先后串行**关系——先全部 text_delta 结束，再 products_start → product_item × N → products_done。锚点**只能由 LLM 自己输出**，后端无法事后注入或改写已 yield 的 text chunk。

2. 对比流程：文本是服务端 `compose_markdown_sections` 拼接的，**后端可以直接把 `[[name#id]]` 写进模板**。但 `comparison_result` 事件当前**前端完全未处理**（`RealtimeEvent` 无对应类型 → WebSocket 解析落入 `Unknown` 被丢弃），需新增前端事件类型与 ViewModel 处理。

3. Bundle 流程：intro 文本是服务端模板拼接的；商品通过 `bundle_item` 事件下发。前端 `ChatViewModel` 当前只调了 `appendAssistantProduct`，**从未构建 `BundleUiModel`**→ `message.bundle` 始终为 `null` → `InlineBundleSection` 是死代码。需补齐 Bundle 模型构建。

4. `llm_client.py` 的 `_response_evidence_payload` 中构建的 `allowed_products` 每个 entry 已含 `product_id` 与 `title`，LLM 拿得到这两个字段。

5. 当前 `response.txt` 输出结构化 Markdown 五段（**理解/结论/主推/备选/下一步**），且已明确"不要输出 JSON"。锚点指令必须**嵌进现有合同的具体段落**。

6. 前端 `ChatMessageUiModel` 已有 `products: List<ProductUiModel>`，ViewModel 在 `product_item` 时 `products = msg.products + product` 逐步填充。锚点点击时按 `productId` 在此列表中查找即可，不新增并行 map。

7. 历史文本的 `recent_context_text` 构建在 **`llm_client.py:488`** 的 `_build_recent_context_text` 函数中。

---

## 后端改动

### B1. 推荐流程 — response.txt 注入锚点指令（核心，推荐锚点的唯一来源）

**文件:** `server/backend/app/prompts/v1/response.txt`

改写现有 **主推：** 和 **备选：** 两段的合同措辞，要求在提到商品时用锚点包裹商品名：

```
**主推：** 主推一个商品：只介绍 selected_primary 对应的第一个 allowed_products 商品，
提到商品名时必须用 [[商品title#product_id]] 格式包裹，title 与 product_id 取自 allowed_products。
**备选：** 如果有其它 allowed_products，用一句话说明备选差异，同样用 [[商品title#product_id]] 包裹商品名；没有备选就省略这一段。
```

约束补充（追加到"不要编造商品属性"那一行附近）：

```
锚点中的 title 和 product_id 必须逐字取自 allowed_products，不得编造或改写。
锚点只出现在正文 Markdown 段落中，不要放在代码块中。
```

> 注意：不要提"不要在 JSON 中输出锚点"——现有合同已禁止输出 JSON，重复提及反而可能唤起 LLM 的 JSON 输出倾向。
> 
> **实施提示：** `response.txt` 共 21 行。实际改动精确区间为第 10 行「**主推：**」和第 12 行「**备选：**」的合同措辞，以及第 20 行「不要编造商品属性」附近的约束补充。实施前建议先 git diff 当前版本确认行号未漂移。

**验证要求：** 改写后需在至少 3 个不同商品类目（如食品、电子、日化）的推荐场景下验证 LLM 锚点输出格式一致性，确认 `[[title#id]]` 中的 title 和 id 与 `allowed_products` 逐字匹配。

**覆盖范围：** 追问（follow-up）场景复用同一份 `response.txt` 合同，LLM 按相同锚点指令输出，无需独立 prompt 文件改动。若追问有独立 prompt 路径，需同步更新对应文件的锚点指令。

### B1b. 对比流程 — 服务端模板注入锚点

**文件:** `server/backend/app/agent.py` — `_build_comparison_events` (line 1026)

对比文案是服务端 `compose_markdown_sections` 拼接的，**不经过 LLM**。直接在模板中注入锚点。

原始（line 1086-1095）：
```python
text = compose_markdown_sections([
    ("理解", understanding),
    ("结论", f"如果只选一款，我更建议「{winner.title}」，因为{result.overall_reason}。"),
    ("下一步", "你可以继续说更便宜、换品牌，或直接围绕胜出款追问。"),
])
```

改为：

```python
# 提取为 agent.py 模块级函数（B1b 和 B1c 共用），放在文件顶部 import 之后
def _anchor(product: Product) -> str:
    """构建锚点标记。若商品 title 含 # 则降级为纯文本书名号，避免前端解析错误。"""
    if not product:
        return "（商品信息缺失）"
    title = product.title.replace("#", "＃")  # 全角替换，避免与锚点分隔符冲突
    return f"[[{title}#{product.product_id}]]"

text = compose_markdown_sections(
    [
        ("理解", understanding),
        (
            "结论",
            # 保留 winner 为 None 的防护（当 result.overall_winner 的 id 不在 product_map 中时）
            f"如果只选一款，我更建议 {_anchor(winner) if winner else _anchor(products[0])}，因为{result.overall_reason or '综合对比'}。"
            + (
                f" 备选 {_anchor(products[1])}。"
                if len(products) >= 2 and winner and winner.product_id != products[1].product_id
                else ""
            ),
        ),
        ("下一步", "你可以继续说更便宜、换品牌，或直接围绕胜出款追问。"),
    ]
)
```

**注意：**
- `_anchor` 提取为 `agent.py` **模块级函数**（非局部定义），B1b 和 B1c 共用。`winner` 为 None 时降级为提示文本
- `winner != products[1]` 改为 `winner.product_id != products[1].product_id`，用 ID 比较而非对象引用；同时增加 `winner` 非空检查
- 保留 `result.overall_reason or '综合对比'` 的 fallback
- 对比流程的商品数据由 `comparison_result` 事件下发，**需前端新增事件处理**（见 F2.5）
- ⚠️ `comparison_result` 的 JSON 字段名：`comparison_item()`（`comparison_presenter.py:7-25`）返回扁平 dict（`product_id/name/brand/price/key_points/dimension_values/risk_flags` 在顶层），前端解析前需通过日志/抓包确认 WebSocket 序列化后的实际 JSON key（camelCase vs snake_case），尤其是 `overall_winner` / `overall_reason` 字段名

### B1c. Bundle 流程 — intro 模板注入锚点

**文件:** `server/backend/app/agent.py` — `_build_bundle_events` (line 1111)

当前 intro 在**商品检索之前**生成（line 1121-1127），不含具体商品名。改造策略：

1. **保留** `assistant_state` → intro 的渐进式文本流（避免用户面对静默等待）
2. 在 `bundle_item` 事件中的 `product` 字段已包含 title + product_id，**同时**在 intro 文本中注入锚点
3. 实现方式：将 intro 中的商品提及后置，在检索完成后追加一句含锚点的总结文本

具体地，在 `bundle_done` 前插入一行含锚点的总结 text_delta：

```python
# 在 bundle_item 循环后、bundle_done 前追加
# 注意：当前代码只维护了 used_product_ids: list[str]（agent.py:1137），不存在 used_products 变量。
# 通过 self.product_map 按 product_id 反查 Product 对象，复用 B1b 定义的模块级 _anchor() 函数
anchor_summary = "、".join(
    _anchor(self.product_map[pid])
    for pid in used_product_ids if pid in self.product_map
)
events.extend(_text_delta_events(message_id, f"已为以下商品生成组合：{anchor_summary}。"))
```

> 前端 BundleGroupCard 中商品名也会改为锚点（见 F7），与 intro 文本中的锚点一致。

### B2. 后端锚点校验与降级（分流程处理）

**文件:** `server/backend/app/agent.py`

不同流程的校验能力不同，需区别处理：

| 流程 | 文本下发方式 | 去标记降级可行？ | 校验策略 |
|------|------------|:---:|---------|
| 推荐 | 流式 `yield` chunk | ❌ chunk 发出后无法撤回 | 流结束后扫描完整文本（插入点：agent.py:735 `text = "".join(text_parts)` 之后、736 `yield {"type": "products_start", ...}` 之前）→ 非法 id 记 **warning 日志**；不修改已发送文本，前端在点击时通过 `message.products` 查找失败做 Toast 兜底 |
| 对比 | 一次性 `list[dict]` 返回 | ✅ | 在 `text` 传入 `_text_delta_events` **之前**扫描替换（插入点：agent.py:1086 之后、1105 之前） |
| Bundle | 一次性 `list[dict]` 返回 | ✅ | 在 `events` 列表构建完毕后、返回前，遍历所有 `type == "text_delta"` 的 event 做扫描替换（覆盖 intro 文本 + B1c 新增的锚点总结文本，而非仅 `bundle_intro`） |

**统一校验函数**（提取到 `agent.py` 模块级，避免三流程重复实现）：

```python
def _validate_and_sanitize_anchors(
    text: str, valid_ids: set[str], *, can_replace: bool
) -> tuple[str, list[str]]:
    """扫描 [[name#id]] 锚点，校验 id 合法性，返回 (处理后的文本, warning 列表)。
    - can_replace=True: 非法 id 去标记保留 name 纯文本（对比/Bundle 用）
    - can_replace=False: 非法 id 保留原样，仅收集 warning（推荐流程用）
    """
    ...
```

校验逻辑（统一）：
- 扫描正文中所有 `[[name#id]]` 标记（正则：`\[\[(.+?)#(.+?)\]\]`）
- 收集本轮下发的所有合法 product_id：
  - 推荐流程：来自 `selected: list[RankedProduct]` → `{item.product.product_id for item in selected}`
  - 对比流程：来自 `products: list[Product]` → `{p.product_id for p in products}`
  - Bundle 流程：来自 `used_product_ids: list[str]` → `set(used_product_ids)`
- id 不在合法集合内 → 对比/Bundle 流程：去标记保留 name 纯文本；推荐流程：保留原样记 warning 日志
- 该出现的商品在正文中**完全没有锚点** → 记 warning 日志

### B3. 历史上下文压缩

**文件:** `server/backend/app/llm_client.py` — `_build_recent_context_text`（约 line 488）

**注意：** 计划原稿引用的 `agent.py:1582` 是错误的——那里的 `_maybe_force_trim_context` 操作的是 payload 级的 `recent_context` 结构化对象（列表字段），不是 `recent_context_text` 文本字符串。

压缩逻辑应在 `llm_client.py` 中构建 `recent_context_text` 字符串时执行：将 `[[name#id]]` 正则替换为 `[商品:id]`，去掉商品名和锚点语法。

> 历史压缩**只在后端做一次**。`_build_recent_context_text` 已确认存在于 `llm_client.py:488`，B3 可直接实施，F6 无前端改动。

---

## 执行规则

前端所有 UI 组件实现前，必须加载以下 skills：

| Skill | 用途 | 适用文件 |
|-------|------|---------|
| **`material-3`** | Material Design 3 组件规范：`ModalBottomSheet`、`Surface`、`TextButton`、`Button`、`OutlinedButton` 的正确用法，tokens（`MaterialTheme.colorScheme`、`Typography`、`Shapes`）体系 | F3, F4, F7 |
| **`frontend-design`** | 视觉美学方向：字重层级、间距节奏、色彩系统、锚点点按反馈 | F1 (锚点 SpanStyle), F4 (Sheet 布局) |

**加载规则：** 写第一行 Kotlin 代码前必须先 `Skill` 加载上述 skill。

---

## 前端改动

> **编号说明：** 前端章节按逻辑依赖排列——F0（Bundle 模型构建）逻辑上排最前，因其是 F7（Bundle 锚点化）的前置条件。F2.5（对比流程事件处理）插入在 F2 和 F3 之间因为其与 F2 共享 `products` 列表的前置关系。阅读顺序建议：F0 → F1 → F2 + F2.5 → F3 → F4 → F5 → F6 → F7。F2 非独立改动项，应视为 F3/F4/F5/F7 的共享设计前提。

### F1. MarkdownTextFormatter — 在行内解析阶段集成锚点解析（关键）

> **Skill: frontend-design** — 锚点视觉样式：品牌色、下划线。

**文件:** `client/app/src/main/java/com/example/shopguideagent/ui/component/MarkdownTextFormatter.kt`

**集成方案（必须照此实现）：** 不新增独立的 `parseProductAnchors` 纯函数，而是在 `appendMarkdownInline` 的 boolean-when 分支中，**在 `source[index] == '['` 分支之前**插入 `source.startsWith("[[", index)` 的检测逻辑（当前代码使用 `when { }` 条件式，不是 `when(c)`）：

```
when {
    source.startsWith("[[", index) -> {
        → 消费 `[[`，解析 `name#productId` 直到 `]]`
        → builder.pushStringAnnotation("product_anchor", productId)
        → builder.pushStyle(SpanStyle(color = anchorColor, textDecoration = TextDecoration.Underline))
        → builder.append(name)
        → builder.pop()
    }
    source[index] == '[' -> {
        // 现有 link 解析分支（appendMarkdownLink）
    }
    // 其他现有分支不变
}
```

**点击绑定方案：** 使用 `LinkAnnotation.Clickable(tag = productId, styles = TextLinkStyles(style = SpanStyle(...)), linkInteractionListener = { onAnchorClick(it.tag) })` 绑定点击，调用方使用普通 `Text` 显示 `AnnotatedString`（**不要用 `ClickableText`**，已 deprecated）。

此方案与 Compose Material3 BOM 2026.04.01 的推荐 API 一致，避免使用 deprecated 的 `ClickableText`。`renderMarkdownText` 新增 `onAnchorClick: (String) -> Unit` 参数，只有 AI 消息气泡需要传值，其他调用方（如商品 reason）使用默认值空 lambda 即可。**注意：`AnnotatedString.Builder` 上不存在 `withStyle` 方法，正确 API 是 `pushStyle`。注意 `pushStringAnnotation` 与 `ClickableText` 的组合在 Compose 1.8 下已被 deprecated，最终方案采用 `LinkAnnotation.Clickable`。**

**为什么必须这样做：** 现有的 `appendMarkdownLink`（`'['` 分支）遇到 `[[...]]` 中的第一个 `[` 时，会尝试解析 markdown link `[text](url)`，找不到 `](` 后回退为逐字追加 `[`，最终 `[[name#id]]` 被渲染为**整段纯文本**——锚点不可点击、标记符暴露给用户。必须在 markdown 解析器内部，在 `[` 的 link 逻辑之前拦截 `[[`。

**参数传递：** `anchorColor` 由调用方在 `@Composable` 内取值（`MaterialTheme.colorScheme.primary`），通过 `AnnotatedString.Builder` 的参数或外部变量传入 parser。`MaterialTheme.colorScheme` 只能在 `@Composable` 作用域取值，不要在 parser 内部直接引用。

**视觉约束：** 锚点与周围文本保持相同字号和行高，仅以颜色和半透明下划线区分。

### F2. 复用现有 `products` 列表

**文件:** `client/app/src/main/java/com/example/shopguideagent/data/model/ChatMessage.kt`

不新增字段。锚点点击时按 `productId` 在现有 `products` 列表中查找：

```kotlin
val anchorTarget: ProductUiModel? = message.products.firstOrNull { it.productId == tappedId }
```

需要确认对比流程和 Bundle 流程的商品也已进入 `products`（见 F0 和 F2.5）。

### F2.5. 新增对比流程事件处理（致命遗漏补齐）

**文件:**
- `client/app/src/main/java/com/example/shopguideagent/data/model/RealtimeEvent.kt`
- `client/app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt`
- `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`

当前 `RealtimeEvent` sealed class **没有** `ComparisonResult` 类型，后端下发的 `comparison_result` 事件在 WebSocket 解析中落入 `Unknown` 被丢弃——锚点 id 在 `products` 列表中永远查不到。

**三步改动：**

1. **RealtimeEvent.kt** — 新增类型：
```kotlin
data class ComparisonResult(
    val messageId: String,
    val items: List<ProductUiModel>,
    val winnerId: String?,
    val reason: String?,
) : RealtimeEvent()
```

2. **RealtimeChatWebSocketClient.kt** — `parseEvent` 中新增分支（在 `"done"` 或 `"error"` 之前）：
```kotlin
"comparison_result" -> {
    // 注意：后端 comparison_item() 返回扁平 dict（product_id/name/brand/price 在顶层），
    // 没有 "product" 子键，直接解析每个元素即可
    val items = json.optJSONArray("items")?.let { arr ->
        (0 until arr.length()).mapNotNull { i ->
            arr.optJSONObject(i)?.let { parseProduct(it) }
        }
    } ?: emptyList()
    RealtimeEvent.ComparisonResult(
        messageId = messageId,
        items = items,
        winnerId = json.optString("overall_winner", "").takeIf { it.isNotBlank() },
        reason = json.optString("overall_reason", "").takeIf { it.isNotBlank() },
    )
}
```

3. **ChatViewModel.kt** — `handleRealtimeEvent` 中新增分支：
```kotlin
is RealtimeEvent.ComparisonResult -> {
    event.items.forEach { product ->
        activeAssistantId?.let { appendAssistantProduct(it, product) }
    }
}
```

### F3. AiMessageBlock 改造 — 移除所有独立卡片

> **Skill: material-3** — `Surface`、文本链接的 Material3 兼容用法。

**文件:** `client/app/src/main/java/com/example/shopguideagent/ui/component/AiMessageBlock.kt`

- 回调签名变更：原 `onProductClick: (ProductUiModel) -> Unit` → 删除，新增 `onProductAnchorTap: (productId: String) -> Unit`
- 文本气泡（`AiMessageText`）：将 `renderMarkdownText` 替换为集成锚点解析的版本（见 F1）。在 Composable 内取 `MaterialTheme.colorScheme.primary` 传入 parser。
- **点击实现用 `Text` + `LinkAnnotation.Clickable`**（`ClickableText` 已 deprecated）。注意与当前代码中 `SelectionContainer`（AiMessageBlock.kt:83）的手势兼容性——`LinkAnnotation` 由 Compose 内部处理手势，通常与文本选择不冲突；若出现问题可考虑用 `BasicText` 替代 `Text`。
- **彻底移除 `ProductCarousel` 区域**（AiMessageBlock:56-67 整段 if），连带清理：
  - `expectedProductCount` 字段：从 `ChatMessageUiModel` 删除，同时清理 `ChatViewModel` 中所有 `updateExpectedCount` 调用（line 430/447）以及 `handleStreamInterrupted` 中的直接赋值 `expectedProductCount = message.products.size`（line 668），锚点方案用 `message.isStreaming && message.products.none { it.productId == anchorId }` 判断加载态
  - `products.isEmpty() && quickActions.isNotEmpty()` 的 `QuickActionChips` fallback 保留（与商品无关）
  - `bundle` 区块保留，但取消原来 `if (message.expectedProductCount > 0 || message.products.isNotEmpty())` 的门控——Bundle 始终由 `message.bundle` 非 null 驱动（见 F0）
- **时序态处理：** 推荐流程中文本**全部先于商品到达**——整条消息的所有锚点初始都处于"商品未到达"状态。点击应展示"正在加载商品信息..."占位，商品事件到达后自动刷新。只有流结束（`Done` 事件，`isStreaming` 变 `false`）后 id 仍不存在才按无效处理。**异常兜底：** 若后端永不发 `Done`（WebSocket 断开等），需在 `handleStreamInterrupted`（line 650）中设 `isStreaming = false` 避免锚点永久 loading。

### F4. ProductDetailSheet — 统一商品详情面板

> **Skills: material-3 + frontend-design** — `ModalBottomSheet` 用法 + 信息层级美学。

**新建文件:** `client/app/src/main/java/com/example/shopguideagent/ui/component/ProductDetailSheet.kt`

用 `ModalBottomSheet`（直接使用，**无需** `@OptIn(ExperimentalMaterial3Api::class)`——自 BOM 2024.02.00+ 已是 stable）。

这是**唯一的商品详情展开入口**，推荐/对比/Bundle/追问所有流程的商品点击都进这个 Sheet。

内容布局（自上而下）：
- **图区**：商品大图（`AsyncImage`，按需加载），16:9 裁切，圆角 `MaterialTheme.shapes.medium`。需包含 `placeholder`（灰色 shimmer/占位色块）和 `error`（默认商品图或图标）状态处理
- **标题区**：`Text` 使用 `MaterialTheme.typography.titleLarge`
- **价格 + 评分**：`¥XX.XX` 使用 `titleMedium` + `colorScheme.primary`，评分用小字 `bodySmall`
- **核心卖点**：`FlowRow` 标签，使用 `AssistChip`（Material3），**不用** `SuggestionChip`（已 `@Deprecated`）
- **操作按钮**：`[加入购物车]` — `Button` primary；`[问更多]` — `OutlinedButton`；`[关闭]` — `TextButton`。间距 12dp，底部安全区

互斥规则：`ChatViewModel` 维护 `expandedProductId: String?` 状态，同时仅展开一个商品。

> 这个 Sheet **取代**了原来 `ProductPresentationSheet` 中 `HeroProductCard` + `AlternativeProductCarousel` 的组合。

### F5. 加购与"问更多"交互

**文件:** `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`

- 新增 `expandedProductId: String?` 状态字段 + 更新方法。建议纳入 `ChatUiState` 以便 Composable 通过 `uiState` 观察（而非 ViewModel 私有字段 + 额外 `StateFlow`）
- `onAddToCart(productId)` → 调用已有 cart API
- `onAskMore(productId)` → 复用现有 `ProductFollowUpPayload`（ChatMessage.kt:48，已有 `focus_product_id` 字段）
- 面板展开期间用户发送新消息 → 自动收起面板：在 `sendMessageStreaming` 开头设置 `expandedProductId = null`

### F6. 历史压缩归后端

历史上下文由**后端**构建发给 LLM（`llm_client.py`），前端只发送用户原文。压缩已在 B3 后端完成（`_build_recent_context_text` 已确认存在于 `llm_client.py:488`，正则替换 `[[name#id]]` → `[商品:id]`）。

前端始终用完整 `[[name#id]]` 原文渲染。本步无前端代码改动。

### F0. 补齐 Bundle 模型构建（致命遗漏——无此步 Bundle 锚点全部死代码）

**文件:** `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`

当前 `BundleItem` handler（line 452-456）只调了 `appendAssistantProduct`，**从未构建 `BundleUiModel`**。`ChatMessageUiModel.bundle` 始终为 `null` → `InlineBundleSection` 永不渲染。

**需补齐的逻辑：**

> **前置依赖：** `ChatViewModel` 当前**不存在** `updateMessage` 方法。需先新增此辅助方法（仿照现有 `appendAssistantProduct` 中 `_uiState.update` 的内联模式提取）：

```kotlin
private fun updateMessage(messageId: String, transform: (ChatMessageUiModel) -> ChatMessageUiModel) {
    _uiState.update { current ->
        current.copy(messages = current.messages.map { msg ->
            if (msg.msgId == messageId) transform(msg) else msg
        })
    }
}
```

此方法同样适用于 F5 中 `expandedProductId` 的关联消息更新。**确认新增后再执行以下三步。**

> **注意：** 当前 `BundleStart` handler（line 446-451）还设置了 `phase = RecommendationLoading`——在删除 `updateExpectedCount` 调用时**应保留 phase 设置**，以维持加载态 UI 反馈。

1. **`BundleStart`** handler（line 446）中，为 `activeAssistantId` 对应的消息初始化 `BundleUiModel`：
```kotlin
is RealtimeEvent.BundleStart -> {
    activeAssistantId?.let { id ->
        updateMessage(id) { msg ->
            msg.copy(bundle = BundleUiModel(
                bundleId = event.messageId,
                scenario = "",
                title = event.title.orEmpty(),
                groups = emptyList(),
                actions = emptyList(),
                isStreaming = true,
            ))
        }
    }
}
```

2. **`BundleItem`** handler（line 452）中，追加 `BundleGroupUiModel` 到对应 group：
```kotlin
is RealtimeEvent.BundleItem -> {
    val groupName = event.group
    val enriched = enrichProduct(event.product)
    appendAssistantProduct(activeAssistantId!!, enriched)
    updateMessage(activeAssistantId!!) { msg ->
        val groups = msg.bundle?.groups?.toMutableList() ?: mutableListOf()
        val existingGroup = groups.indexOfFirst { it.name == groupName }
        val newItem = BundleItemUiModel(slot = event.group, product = enriched)
        if (existingGroup >= 0) {
            val old = groups[existingGroup]
            groups[existingGroup] = old.copy(items = old.items + newItem)
        } else {
            groups.add(BundleGroupUiModel(name = groupName, items = listOf(newItem)))
        }
        msg.copy(bundle = msg.bundle?.copy(groups = groups))
    }
}
```

3. **`BundleDone`** handler（line 458）中，标记 `isStreaming = false`：
```kotlin
is RealtimeEvent.BundleDone -> {
    activeAssistantId?.let { id ->
        updateMessage(id) { msg ->
            msg.copy(bundle = msg.bundle?.copy(isStreaming = false))
        }
    }
}
```

> ⚠️ `updateMessage` 辅助方法已在上方定义，F0 的三个 handler 和 F5 的 `expandedProductId` 更新均依赖此方法。

### F7. Bundle 组件改为锚点渲染

> **Skill: material-3** — 与整体锚点/Sheet 体系一致。

**文件:** `client/app/src/main/java/com/example/shopguideagent/ui/component/BundleGroupCard.kt`

当前渲染为 `Text("${item.slot}: ${item.product.name}")`（BundleGroupCard.kt:61）——整段纯文本。改为：

- **slot 前缀**（`"${item.slot}: "`）：保留为普通 `Text`
- **商品名**：用 `AnnotatedString` 构建，`pushLink(LinkAnnotation.Clickable(tag = item.product.productId, styles = TextLinkStyles(style = SpanStyle(color = primary, textDecoration = TextDecoration.Underline)), linkInteractionListener = { onProductAnchorTap(it.tag) }))`
- **点击绑定**：与 F1 方案一致——使用 `LinkAnnotation.Clickable` + 普通 `Text` 显示（`ClickableText` 已 deprecated）
- 保留"加购"按钮，但卡片视觉更轻量

**文件:** `client/app/src/main/java/com/example/shopguideagent/ui/component/BundleSection.kt` + `AiMessageBlock.kt` — `InlineBundleSection`

- `BundleSection` 签名新增 `onProductAnchorTap: (String) -> Unit` 参数，向下透传给 `BundleGroupCard`
- `InlineBundleSection` → `BundleSection` 链路传入此回调

---

## 边界处理

| 场景 | 行为 |
|------|------|
| 同消息多锚点 | 各自独立可点击，互不干扰 |
| 同消息多锚点指向同一 product_id | 每个锚点独立构建 `AnnotatedString` 注解，点击任一都会打开同一个 Sheet（正确行为，无需去重） |
| 锚点 id 对应商品**尚未到达**（流式时序） | 点击展示"加载中"占位。推荐流程中**所有**锚点初始都处于此状态（文本先全部结束、商品后到）；商品事件到达后自动填充，**不报错** |
| 流结束后 id 仍无效 | 对比/Bundle 流程：后端 B2 已去标记降级（见 B2）；推荐流程：文本已流式发送无法撤回，锚点保持可点击外观不变，点击时在 `message.products` 中查找失败 → Toast "商品信息暂不可用"（不降级视觉样式——已渲染的 Compose AnnotatedString 无法事后修改） |
| 流异常中断（WebSocket 断开），`isStreaming` 永不变 false | `handleStreamInterrupted`（line 650）中设 `isStreaming = false`，避免锚点永久显示 loading |
| LLM 输出锚点格式错误（缺少 `#`、多余空格、嵌套方括号） | 正则匹配失败 → 渲染为普通文本，不可点击 |
| LLM hallucination 出完全不在 `allowed_products` 中的 product_id（格式正确但 id 非法） | 推荐流程：锚点保持可点击 → 点击查 `message.products` 失败 → Toast "商品信息暂不可用"；后端 B2 记 warning 日志 |
| 商品名含 `#` 字符 | **后端硬处理**：B1b/B1c 的 `_anchor()` 函数在构建锚点前用全角 `＃` 替换 title 中的 `#`（`product.title.replace("#", "＃")`）。推荐流程由 B2 校验侧在扫描时对含 `#` 的 title 跳过锚点生成，降级为纯文本书名号《title》。前端正则 `\[\[(.+?)#(.+?)\]\]` 用 `lastIndexOf('#')` 辅助切分兜底 |
| 对比/Bundle 流程商品事件未到达前端 | 同"流结束后 id 仍无效"，但当前需先补齐 F2.5 / F0 的事件处理（否则永远"未到达"） |
| 对比流程 winner 锚点先于 `comparison_result` 事件到达 | 文本事件先于 comparison_result → 点击时 `message.products` 为空 → loading 态 → comparison_result 到达后自动填充（与推荐流程行为一致） |
| 面板展开时发新消息 | 自动收起面板（`expandedProductId = null`），不阻断对话 |
| 快速连续发送多条消息 | `sendMessageStreaming` 开头清 `expandedProductId`，无竞态 |
| 网络断连期间点击锚点 | WebSocket 断开后 `isStreaming` 变 false，`message.products` 可能不完整 → Toast "商品信息暂不可用"。不自动重连，用户需手动重试 |
| 历史消息中锚点点击 | 若 `message.products` 为空（历史消息商品数据未保留），Toast "历史消息暂不支持查看商品详情" |
| 追问响应中的锚点 | 与推荐消息处理一致：锚点 + Sheet，无特殊路径。**注意：** 追问响应的 `responseText`（`ProductFocusUiState.responseText`）需要确保也经过 `renderMarkdownText` 解析（而非某条不经过 parser 的渲染路径） |
| 屏幕旋转/配置变更 | `expandedProductId` 在 `ChatViewModel` 中跨配置变更存活；`ModalBottomSheet` 的展开状态在 recompose 后自动恢复（Compose 状态驱动） |
| Bundle intro 锚点总结与 BundleGroupCard 锚点指向同一批商品 | **有意共存**：intro 提供对话流中的自然提及，BundleGroupCard 提供结构化分组视图。两者不互斥，均走 ProductDetailSheet |

---

## 交付物

1. **后端：** `response.txt` 合同改写（B1）+ 对比/Bundle 模板锚点注入（B1b/B1c，含 `_anchor()` 模块级函数）+ 锚点校验降级（B2，含 `_validate_and_sanitize_anchors()` 统一函数）+ 历史压缩（B3，`llm_client.py:488` `_build_recent_context_text`）
2. **前端：** `MarkdownTextFormatter.kt` — 锚点内联解析（F1，在 `appendMarkdownInline` 的 boolean-when 中插入 `source.startsWith("[[", index)` 分支）
3. **前端：** `RealtimeEvent.kt`（新增 `ComparisonResult` 类型）+ `RealtimeChatWebSocketClient.kt`（新增 `"comparison_result"` 解析分支）+ `ChatViewModel.kt`（新增 `ComparisonResult` handler）（F2.5）
4. **前端：** `ChatViewModel.kt` — 新增 `updateMessage()` 辅助方法 + 补齐 `BundleItem` → `BundleUiModel` 构建（F0）
5. **前端：** `AiMessageBlock.kt` — 改造（F3，移除 carousel + 删除 `expectedProductCount` + 回调签名变更 + 时序态处理 + `Text(onClick)` 手势与 `SelectionContainer` 兼容性验证）
6. **前端：** `ProductDetailSheet.kt` — **新建**（F4，含 `AsyncImage` 的 placeholder/error 态）+ `ChatViewModel.kt` — 新增 `expandedProductId` 状态纳入 `ChatUiState`（F5）
7. **前端：** `BundleSection.kt` + `BundleGroupCard.kt` — 锚点化（F7，`LinkAnnotation.Clickable` + 普通 `Text` 与 F1/F3 统一，回调链贯通）
8. **前端清理：** 移除 AI 消息流中废弃的元素：
   - `AiMessageBlock.kt` 中的 `ProductCarousel` 调用（已完成）
   - `ui/component/ProductCarousel.kt` — 已从 AI 消息流移除且无外部引用，**已删除**
   - `ChatMessageUiModel.expectedProductCount` 字段 + `ChatViewModel.updateExpectedCount()` 方法 + 初始化/中断中的赋值 — **已删除**
   - ⚠️ `HeroProductCard.kt` / `AlternativeProductCarousel.kt` / `ProductPresentationSheet.kt` 仍在首页 `SpriteHomeScreen` 中独立使用（非 AI 消息流），本次保留

   > 注：原交付物中"删除 HeroProductCard / AlternativeProductCarousel / ProductPresentationSheet"的目标过于宽泛，实际只有 `ProductCarousel` 从 AI 消息流移除后可删除。

## 验证

```bash
# 后端（先确认 venv 路径存在）
ls ../env/venv_shopguide_backend/bin/python
cd server && ../env/venv_shopguide_backend/bin/python -m pytest -q

# 前端
cd client && ./gradlew :app:testDebugUnitTest :app:assembleDebug
```

**手动验收矩阵（覆盖全部流程）：**

| 流程 | 验收点 |
|------|--------|
| 推荐 | 发请求 → **主推/备选** 段落出现品牌色可点击锚点 → 点击弹出 Sheet（先 loading 后填充）→ 加购/问更多可操作 |
| 对比 | 发对比 → 结论段落两个商品名均可点击 → 点击任一弹 Sheet → 操作正常 |
| Bundle | 发场景组合 → intro + 分组内商品名为可点击锚点 → 点击弹 Sheet → 一键加购正常 |
| 追问 | 追问商品 → 响应中锚点与推荐一致 |
| 时序 | 流式输出中锚点先出现 → 点击 loading → 商品到后自动填充，不报错 |
| 格式错误 | LLM 输出 `[[nameid]]`（无 `#`）→ 渲染为普通文本 |
| 收起 | Sheet 展开时发新消息 → 自动关闭 |
