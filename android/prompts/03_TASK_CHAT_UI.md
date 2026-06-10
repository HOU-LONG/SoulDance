# Task 03：实现低压力导购聊天主界面

## 目标

实现一个美观、稳定、低交互压力的 AI 导购聊天页面。

## 需要创建/修改文件

```text
ui/screen/ChatScreen.kt
ui/component/MessageBubble.kt
ui/component/TypingIndicator.kt
ui/component/ChatInputBar.kt
ui/component/CartBadge.kt
data/model/ChatMessage.kt
vm/ChatViewModel.kt
```

## 数据模型

```kotlin
enum class MessageRole {
    User,
    Assistant,
    System
}

data class ChatMessageUiModel(
    val id: String,
    val role: MessageRole,
    val text: String = "",
    val isStreaming: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis()
)
```

## 文字风格要求

AI 回复不应该像搜索引擎，而要先帮助用户降低决策压力。文字结构建议：

```text
1. 先复述并抽象用户背后的购买动机。
2. 说明系统会优先排除什么风险或满足什么条件。
3. 给出一个明确主推结论。
4. 告诉用户可以低成本修正，例如更便宜、更清爽、更适合户外。
```

示例：

```text
我理解你更在意的是“不刺激”和“来源可控”，所以我会先排除含酒精、日系品牌和不适合敏感肌的防晒。先给你主推这一款，如果你想要更便宜或更适合户外，我可以继续帮你换。
```

避免：

```text
亲爱的、宝宝、绝对适合你、闭眼入
```

## ChatViewModel

先用 mock 逻辑：

```text
1. 用户输入文字。
2. 点击发送。
3. 用户消息追加到列表。
4. 追加一条 mock assistant 消息。
5. mock assistant 消息用延迟模拟逐字输出。
```

## ChatScreen 布局

```text
顶部栏：
  标题：智能导购助手
  副标题：懂你需求的 AI 购物助手
  右侧：购物车图标 + badge

中间：
  LazyColumn 消息列表

底部：
  ChatInputBar
  输入框 + 麦克风按钮 + 发送按钮
```

## MessageBubble 样式

用户消息：

```text
右对齐
主色背景
白色文字
圆角 18-20dp
最大宽度 78%
```

AI 消息：

```text
左对齐
白色/浅灰背景
深色文字
圆角 18-20dp
最大宽度 82%
可带小 AI 图标
```

## 滚动策略

```text
1. 新消息出现时，如果用户在底部附近，则自动滚到底部。
2. 不要每个字符都强制滚动。
3. 用户上滑历史时，不要抢滚动。
```

## 验收标准

```text
1. App 显示完整聊天界面。
2. 用户可输入并发送文字。
3. 用户消息右侧显示。
4. AI mock 回复左侧流式显示。
5. UI 留白合理。
6. 购物车 badge 位置存在。
7. ./gradlew :app:assembleDebug 通过。
```
