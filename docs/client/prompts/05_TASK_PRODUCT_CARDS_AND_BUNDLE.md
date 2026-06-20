# Task 05：实现主推商品卡片流式渲染与场景组合方案展示

## 目标

让 Android 端支持主推商品实时渲染，以及“三亚度假”等组合方案分组展示。

注意：本项目不强调一次给很多搜索结果，而是强调“主推 1 个产品 + 少量备选”。

## 需要创建/修改文件

```text
data/model/Product.kt
data/model/BundleModels.kt
data/model/ChatMessage.kt
data/model/RealtimeEvent.kt
ui/component/ProductCard.kt
ui/component/ProductSkeletonCard.kt
ui/component/ProductCarousel.kt
ui/component/BundleSection.kt
ui/component/BundleGroupCard.kt
vm/ChatViewModel.kt
```

## 商品 UI 模型

```kotlin
data class ProductUiModel(
    val productId: String,
    val name: String,
    val price: Double,
    val imageUrl: String? = null,
    val tags: List<String> = emptyList(),
    val reason: String? = null,
    val rating: Double? = null,
    val stock: Int? = null,
    val isPrimary: Boolean = false
)
```

## 推荐展示策略

```text
1. primary_product：重点展示 1 个主推商品。
2. alternatives：可横向展示 1-2 个备选，但弱化视觉权重。
3. 不要一次性平铺 8-10 个商品。
4. 如果用户不满意，引导其在商品详情浮层继续追问。
```

## 商品流式事件

### products_start

```json
{
  "type": "products_start",
  "message_id": "assistant_001",
  "layout": "primary_plus_alternatives",
  "expected_count": 3,
  "title": "我先帮你主推这一款"
}
```

行为：显示 skeleton 商品区域。

### product_item

```json
{
  "type": "product_item",
  "message_id": "assistant_001",
  "index": 0,
  "role": "primary",
  "product": {
    "product_id": "sku_001",
    "name": "清爽控油氨基酸洗面奶",
    "price": 79.0,
    "main_image_url": "https://example.com/sku_001.jpg",
    "tags": ["油皮", "控油", "温和"],
    "reason": "适合油皮，价格在预算内"
  }
}
```

行为：

```text
1. role=primary 的商品用更大卡片展示。
2. role=alternative 的商品用较小卡片展示。
3. 卡片点击后在 Task 09 打开 ProductDetailBottomSheet。
```

### products_done

```json
{
  "type": "products_done",
  "message_id": "assistant_001"
}
```

## 场景组合方案事件

### bundle_start

```json
{
  "type": "bundle_start",
  "message_id": "assistant_001",
  "bundle_id": "bundle_001",
  "scenario": "三亚度假",
  "title": "三亚度假组合方案",
  "groups": ["防晒护理", "穿搭", "出行配件"]
}
```

### bundle_item

```json
{
  "type": "bundle_item",
  "message_id": "assistant_001",
  "bundle_id": "bundle_001",
  "group": "防晒护理",
  "slot": "防晒霜",
  "index": 0,
  "product": {
    "product_id": "sku_101",
    "name": "高倍清爽防晒乳",
    "price": 129,
    "tags": ["SPF50", "清爽", "防水"],
    "reason": "适合三亚强紫外线和海边活动"
  }
}
```

### bundle_done

```json
{
  "type": "bundle_done",
  "message_id": "assistant_001",
  "bundle_id": "bundle_001",
  "actions": ["一键加入购物车", "只加入防晒护理", "换成更便宜的"]
}
```

## 验收标准

```text
1. products_start 后 skeleton 出现。
2. product_item 到来后主推卡片突出显示。
3. 备选卡片可横向滑动。
4. bundle_start 后能显示组合方案分组。
5. bundle_item 能插入对应分组。
6. bundle_done 后 quick action 出现。
7. ./gradlew :app:assembleDebug 通过。
```
