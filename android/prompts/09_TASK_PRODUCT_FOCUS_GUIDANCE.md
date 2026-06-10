# Task 09：实现以商品为锚点的详情浮层与多轮导购

## 目标

实现本项目最重要的交互亮点：用户点击商品卡片后，不跳转离开聊天流，而是在当前页面浮出商品详情 BottomSheet。用户可以在详情浮层底部继续围绕当前商品追问或修正需求，Android 将该消息作为 `product_followup` 发送给后端。

## 核心产品原则

```text
1. 不把商品详情做成外部跳转。
2. 不让用户每次重新描述完整需求。
3. 用户围绕当前商品追问时，必须绑定 focus_product_id。
4. 后端基于当前商品上下文和原始约束重新生成检索计划。
5. 前端在同一浮层内展示解释和替代商品。
```

## 需要创建/修改文件

```text
data/model/FocusModels.kt
data/model/RealtimeEvent.kt
ui/component/ProductDetailBottomSheet.kt
ui/component/ProductFocusInputBar.kt
ui/component/ReplacementProductCard.kt
ui/component/ProductCard.kt
vm/ProductFocusViewModel.kt
vm/ChatViewModel.kt
ui/screen/ChatScreen.kt
```

## UI：ProductDetailBottomSheet

结构：

```text
顶部：
  商品大图
  商品名
  价格
  标签

中部：
  为什么推荐给你
  - 符合你说的“不含酒精”
  - 非日系品牌
  - 适合油皮日常通勤

关键属性：
  类目
  适合人群
  不含/排除项
  质地
  价格

操作：
  [加入购物车]
  [换个更便宜的]
  [换个更清爽的]
  [不要这个品牌]

底部：
  针对这款商品继续问...
  输入框 + 发送按钮
```

## Focus 状态模型

```kotlin
data class ProductFocusUiState(
    val isOpen: Boolean = false,
    val focusProduct: ProductUiModel? = null,
    val focusText: String = "",
    val isStreaming: Boolean = false,
    val replacementProducts: List<ProductUiModel> = emptyList(),
    val quickActions: List<String> = listOf(
        "换个更便宜的",
        "换个更清爽的",
        "不要这个品牌",
        "更适合户外"
    ),
    val errorMessage: String? = null
)
```

## Android -> 后端：product_followup

```json
{
  "type": "product_followup",
  "session_id": "demo_session_001",
  "focus_product_id": "sku_101",
  "message": "这个有点贵，有没有100以内的？",
  "tts_enabled": true
}
```

## 后端 -> Android：focus_text_delta

```json
{
  "type": "focus_text_delta",
  "focus_product_id": "sku_101",
  "text": "你主要是不太满意价格，所以我保留“不含酒精、非日系品牌”的要求，再把预算压到100以内重新筛选。"
}
```

## 后端 -> Android：replacement_product

```json
{
  "type": "replacement_product",
  "focus_product_id": "sku_101",
  "reason": "更便宜，但仍满足不含酒精和非日系品牌",
  "product": {
    "product_id": "sku_118",
    "name": "清爽通勤防晒乳",
    "price": 89,
    "tags": ["不含酒精", "清爽", "通勤"],
    "reason": "价格低于100，且保留原有排除约束"
  }
}
```

## 后端 -> Android：focus_done

```json
{
  "type": "focus_done",
  "focus_product_id": "sku_101"
}
```

## Quick Actions

Quick Action 点击后直接发送 product_followup：

```text
换个更便宜的 -> 这个有点贵，有没有更便宜的？
换个更清爽的 -> 有没有质地更清爽、不油腻的？
不要这个品牌 -> 不想要这个品牌，换一个类似但不同品牌的。
更适合户外 -> 有没有更适合户外暴晒或海边使用的？
```

## 上下文隔离要求

```text
1. 从商品详情浮层发出的消息必须携带 focus_product_id。
2. 如果用户关闭浮层，再从普通输入框提问，则走 user_message，不携带 focus_product_id。
3. 后端返回 replacement_product 时，前端在浮层内展示，不污染普通聊天列表。
4. 用户点击替代商品，可以把 focusProduct 切换为新商品。
```

## 验收标准

```text
1. 点击 ProductCard 打开 ProductDetailBottomSheet。
2. BottomSheet 展示商品图、价格、标签、推荐理由。
3. BottomSheet 底部有输入框。
4. 输入后发送 product_followup，携带 focus_product_id。
5. 能接收 focus_text_delta 并在浮层内流式显示。
6. 能接收 replacement_product 并展示替代商品卡片。
7. Quick Actions 可发送对应追问。
8. 关闭浮层后回到聊天主页面，不丢失聊天状态。
9. ./gradlew :app:assembleDebug 通过。
```

## 不要做

```text
1. 不要把商品详情做成外部网页。
2. 不要强制新开完整页面。
3. 不要让 product_followup 不带 product_id。
4. 不要在 Android 端自行编造替代推荐。
```
