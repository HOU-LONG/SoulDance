# Android 实现规格说明

## 开发目标

Android 端要实现的是一个“低压力 AI 导购客户端”，不是普通电商搜索页。

最小闭环：

```text
文字输入 -> AI 流式回复 -> 主推商品卡片 -> 商品详情浮层 -> 商品级追问 -> 替代商品 -> 加入购物车 -> 改数量 -> 模拟下单
```

## 关键组件

### ChatScreen

负责承载聊天主流程。

状态来源：`ChatViewModel.uiState`。

包含：

```text
TopBar
LazyColumn
MessageBubble
ProductCard / ProductCarousel
BundleSection
ChatInputBar
ProductDetailBottomSheet
```

### ProductCard

展示主推商品和备选商品。

必须支持：

```text
1. 图片加载失败 fallback
2. role=primary 时更突出
3. role=alternative 时弱化显示
4. 点击打开 ProductDetailBottomSheet
5. 加入购物车按钮
```

### ProductDetailBottomSheet

这是核心差异化交互。

必须支持：

```text
1. 商品详情
2. 为什么推荐给你
3. Quick Actions
4. 商品级输入框
5. focus_text_delta 流式显示
6. replacement_product 渲染
7. 加入购物车
```

### BundleSection

展示场景化组合推荐。

必须支持：

```text
1. 分组显示
2. 每个 group 内显示商品
3. bundle_item 到来后渐进式插入
4. 一键加入购物车
5. 只加入某一组
```

## StateFlow 结构

### ChatUiState

```kotlin
data class ChatUiState(
    val isConnected: Boolean = false,
    val isSending: Boolean = false,
    val messages: List<ChatMessageUiModel> = emptyList(),
    val cartBadgeCount: Int = 0,
    val focus: ProductFocusUiState = ProductFocusUiState(),
    val errorMessage: String? = null
)
```

### ChatMessageUiModel

```kotlin
data class ChatMessageUiModel(
    val id: String,
    val role: MessageRole,
    val text: String = "",
    val isStreaming: Boolean = false,
    val expectedProductCount: Int = 0,
    val products: List<ProductUiModel> = emptyList(),
    val bundle: BundleUiModel? = null
)
```

## 事件处理原则

```text
text_delta -> 更新消息 text
products_start -> 创建商品 skeleton 区域
product_item -> 插入或替换商品卡片
bundle_start -> 创建组合方案区域
bundle_item -> 插入对应分组
focus_text_delta -> 更新 BottomSheet 内文案
replacement_product -> 在 BottomSheet 内追加替代商品
cart_update -> 更新 badge
error -> Snackbar
```

## 性能注意

```text
1. LazyColumn 使用稳定 key。
2. 不要每个 token 都强制滚动。
3. 图片使用 Coil 缓存。
4. BottomSheet 内状态不要触发整个 ChatScreen 重组。
5. AudioTrack 和 SpeechRecognizer 必须释放。
```
