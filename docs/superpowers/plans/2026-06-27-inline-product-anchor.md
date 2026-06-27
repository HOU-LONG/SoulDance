# Inline Product Anchor — 聊天消息内嵌商品锚点重构

## Context

当前 APP 中，AI 推荐的商品以独立大卡片（`HeroProductCard` + `AlternativeProductCarousel`）插入消息流，与文本段落分离，视觉上厚重、破坏对话阅读节奏。需要参照豆包 AI 的嵌入方式，改为文本内可点击锚点 + 局部展开的交互形态。

**涉及端：** 后端（文本生成）+ 前端（渲染 + 交互）

---

## 后端改动

### B1. Response Prompt 注入商品标记指令

**文件:** `server/backend/app/prompts/v1/response.txt`

在回答合同中追加规则：

```
当推荐商品时，在正文中用 [[商品名称#product_id]] 格式标记每个推荐的商品。
主推和备选都必须使用此格式。不要输出 JSON 格式的商品数据。
```

### B2. 后端 event 协议扩展

**文件:** `server/backend/app/agent.py`

不改变现有 `product_item` 事件流（保持向后兼容），但在 `text_delta` / response 文本中确保 `[[name#id]]` 标记与 `product_item` 事件一一对应。

做法：在 `_stream_recommendation_events` 中，生成 text 时将 `selected` 产品的 title 和 product_id 注入为标记格式。改造 `_product_card` 的 title 注入点。

### B3. 历史上下文压缩

**文件:** `server/backend/app/agent.py` — `_build_recent_context_text`

在构建发送给 LLM 的历史上下文时，如果对话中包含 `[[name#id]]` 标记，替换为 `[商品:id]` 纯文本形式，去掉商品名和图片等冗余信息。

---

## 前端改动

### F1. 文本解析器 — MarkdownTextFormatter

**文件:** `client/app/src/main/java/com/example/shopguideagent/ui/component/MarkdownTextFormatter.kt`

新增 `parseProductAnchors(text: String): AnnotatedString`：

- 正则匹配 `\[\[(.+?)#(.+?)\]\]` → 提取 `name` 和 `productId`
- 替换为可点击的 `AnnotatedString` span：
  - `pushStringAnnotation(tag = "product_anchor", annotation = productId)`
  - `withStyle(SpanStyle(color = BrandPrimary, textDecoration = TextDecoration.Underline))`
- 点击时触发回调，传入 `productId`

### F2. 消息数据模型扩展

**文件:** `client/app/src/main/java/com/example/shopguideagent/data/model/ChatMessage.kt`

`ChatMessageUiModel` 新增：

```kotlin
val productAnchors: Map<String, ProductUiModel> = emptyMap()
// key = productId in text markers, value = resolved ProductUiModel
```

ViewModel 在处理 `product_item` 事件时同步填充此 map。

### F3. 锚点渲染 — AiMessageBlock 改造

**文件:** `client/app/src/main/java/com/example/shopguideagent/ui/component/AiMessageBlock.kt`

- 保留文本气泡（`AiMessageText`），但将 `renderMarkdownText` 替换为支持 `ClickableText` 的版本
- 文本中检测到 `product_anchor` annotation 时，渲染为品牌色 + 下划线文字
- 点击 → 触发 `onProductAnchorTap(productId)`
- 不再在文本下方渲染 `ProductCarousel`（移除独立卡片区域）

### F4. 商品详情展开面板

**新建文件:** `client/app/src/main/java/com/example/shopguideagent/ui/component/ProductDetailSheet.kt`

移动端用 `ModalBottomSheet`（Material3），桌面端可选 `DropdownMenu` 或内联展开。

内容：
- 商品大图（`AsyncImage`，按需加载）
- 完整标题
- 价格 `¥XX.XX`
- 评分 + 核心卖点
- 操作按钮：`[加入购物车]` `[问更多]` `[关闭]`

互斥规则：`ChatViewModel` 维护 `expandedProductId: String?` 状态，同时仅展开一个。

### F5. 加购与"问更多"交互

**文件:** `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`

- `onAddToCart(productId)` → 调用已有 cart API
- `onAskMore(productId)` → 将 `focus_product_id` 注入下一条用户消息的 context，自动聚焦输入框
- 面板展开期间用户发送新消息 → 自动收起面板

### F6. 历史上下文压缩（前端）

**文件:** `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`

在 `ChatMessageUiModel` 新增 `compressedText` 字段——发送给 AI 时使用压缩版（`[商品:id]`），渲染时使用完整版（`[[name#id]]`）。

---

## 边界处理

| 场景 | 行为 |
|------|------|
| 同消息多锚点 | 各自独立可点击，互不干扰 |
| 商品 ID 无效 | 锚点降级为普通文本，Toast "商品信息暂不可用" |
| 面板展开时发新消息 | 自动收起面板，不阻断对话 |
| 键盘操作 | ESC 关闭面板，Tab 在按钮间切换 |
| 历史消息 | 只存储 `[商品:id]` 标记，图片/价格按需异步获取 |

---

## 交付物

1. 后端：response.txt prompt 更新 + agent.py 文本标记生成 + 历史压缩
2. 前端：MarkdownTextFormatter 解析器 + AiMessageBlock 改造 + ProductDetailSheet 组件
3. 前端：ChatViewModel 交互逻辑（展开/加购/问更多）
4. 前端：历史上下文压缩逻辑

## 验证

```bash
# 后端
cd server && ../env/venv_shopguide_backend/bin/python -m pytest -q

# 前端
cd client && ./gradlew :app:testDebugUnitTest :app:assembleDebug
```

手动验收：发送推荐请求 → 文本中出现 `[[商品名#product_id]]` 蓝色可点击文字 → 点击弹出底部 Sheet → 加购 / 问更多均可操作 → 面板收起正常。
