---
title: "ShopGuide Agent 完整实施方案与 Android 执行手册"
author: "项目组内部对齐文档"
date: "2026-05-24"
mainfont: "Noto Sans CJK SC"
CJKmainfont: "Noto Sans CJK SC"
monofont: "DejaVu Sans Mono"
geometry: margin=2cm
fontsize: 10pt
toc: true
toc-depth: 3
numbersections: true
colorlinks: true
header-includes:
  - \usepackage{fvextra}
  - \DefineVerbatimEnvironment{Highlighting}{Verbatim}{breaklines,commandchars=\\\{\}}
  - \usepackage{longtable}
  - \usepackage{booktabs}
---

# 项目一句话定位

**ShopGuide Agent 是一个面向电商导购场景的 Android 原生 AI Agent 客户端与 RAG 后端系统。它不是商品搜索引擎，而是低压力、以商品为锚点、能理解用户购买动机并支持多轮修正的智能导购系统。**

最重要的产品体验：

```text
用户说出自然需求
  -> 系统理解其背后的购买动机、情绪压力和风险偏好
  -> 后端用 LLM 生成结构化检索计划
  -> 程序执行硬约束过滤、RAG 检索和分层排序
  -> 系统主推一个具体商品，而不是甩出一堆结果
  -> Android 端实时显示文字和商品卡片
  -> 用户点开商品卡片后，不跳转页面，而是浮出详情 BottomSheet
  -> 用户可在商品详情浮层底部继续追问或修正需求
  -> 后端绑定 focus_product_id，围绕当前商品上下文重新检索
  -> 返回更符合进一步需求的替代商品
  -> 商品可加入购物车、改数量、模拟下单
```

# 为什么不能做成普通 RAG 商品搜索

普通做法：

```text
用户输入：推荐防晒霜
系统输出：10 个防晒霜商品卡片
```

这本质上只是把“输入关键词搜索”换成了“自然语言搜索”，用户仍然要自己比较、排除、纠结和决策，导购价值不明显。

本项目应该做：

```text
用户输入：推荐防晒霜，但不要含酒精，也不要日系品牌
系统输出：
  1. 先解释理解到的真实意图：成分安全、来源可控、降低踩雷风险
  2. 明确说明已排除含酒精和日系品牌
  3. 主推一个最适合的具体商品
  4. 提供低成本修正入口：更便宜、更清爽、更适合户外、不要这个品牌
```

这才体现“导购”：系统替用户做初步决策，并且允许用户轻松修正。

# 总体架构

```text
Android App
  - ChatScreen
  - MessageBubble
  - ProductCard
  - ProductDetailBottomSheet
  - ProductFocusInputBar
  - BundleSection
  - CartScreen
  - VoiceInputManager
  - StreamingAudioPlayer
  - RealtimeWebSocketClient
        |
        | WebSocket / REST
        v
FastAPI Backend
  - Realtime Chat API
  - Query Understanding LLM
  - Retrieval Plan Generator
  - Constraint Validator
  - Hard Filter
  - Hybrid Retriever
  - Tiered Ranker
  - Controlled Multi-hop Executor
  - Product Focus Handler
  - Cart Service
  - TTS Stream Service
  - Eval Logger
        |
        v
Data Layer
  - SQLite 商品结构化表
  - Vector DB 商品知识库
  - Session Profile
  - Cart / Order mock tables
  - Static image assets
```

# 两阶段 LLM 架构

LLM 不应该直接决定最终商品。更稳的方式是“两阶段 LLM + 确定性检索控制”。

## 第一阶段 LLM：理解用户并生成检索计划

输入：用户自然语言、session 状态、当前商品 focus 状态。

输出：结构化 JSON。

示例：

```json
{
  "intent": "recommend_product",
  "query_type": "single_category_recommendation",
  "category": "防晒霜",
  "hard_constraints": {
    "category": "防晒霜",
    "exclude_ingredients": ["酒精", "乙醇"],
    "exclude_brand_regions": ["日本"],
    "in_stock_only": true
  },
  "soft_preferences": {
    "texture": "清爽",
    "scene": "通勤"
  },
  "retrieval_query": "清爽 通勤 防晒霜 不含酒精 非日系",
  "need_clarification": false
}
```

## 中间程序层：校验、过滤、检索、排序

程序层必须负责：

```text
1. JSON Schema 校验
2. 字段白名单校验
3. 类目标准化
4. 成分同义词扩展
5. 品牌地区映射
6. hard constraint 硬过滤
7. RAG 检索
8. 分层排序
9. 返回真实候选商品
```

## 第二阶段 LLM：基于真实候选商品生成解释

第二阶段 LLM 只能基于后端返回的候选商品解释推荐原因，不能编造商品、价格、库存、功效。

# 检索与排序：硬过滤 + 分层排序

原先的线性加权公式不适合作为正式排序逻辑：

```text
final_score =
  0.45 * semantic_score
+ 0.25 * attribute_match_score
+ 0.15 * personalization_score
+ 0.10 * price_score
+ 0.05 * popularity_score
- hard_constraint_penalty
```

问题：

```text
1. 各分数尺度不一致。
2. 权重没有数据学习或评估支撑。
3. 硬约束不应该扣分，而应该直接过滤。
4. 个性化不能覆盖用户明确约束。
5. 不同类目排序逻辑不同。
```

推荐正式方案：

```text
Hard Filter
  -> Eligibility Tier
  -> In-tier Ranking
  -> Grounded Explanation
```

## Hard Filter

以下条件必须直接过滤：

```text
1. 类目不符
2. 价格超过硬预算
3. 缺货
4. 包含用户排除成分
5. 品牌地区被排除
6. 用户明确说不要的标签/品牌/属性
```

## Eligibility Tier

```text
Tier 1：完全满足用户显式需求和主要偏好。
Tier 2：满足核心需求，但部分软偏好弱匹配。
Tier 3：兜底候选，需要明确说明不完全匹配原因。
```

## In-tier Ranking

同一层级内再按以下优先级排序：

```text
1. 属性覆盖度
2. 场景匹配度
3. 语义相关性
4. 个性化匹配度
5. 价格友好度
6. 评分/热度
```

# 反选/排除约束

典型输入：

```text
推荐防晒霜，但我不要含酒精的，也不要日系品牌
```

解析为：

```json
{
  "intent": "recommend_product",
  "category": "防晒霜",
  "hard_constraints": {
    "exclude_ingredients": ["酒精", "乙醇"],
    "exclude_brand_regions": ["日本"]
  }
}
```

核心原则：

```text
1. “不要、不含、除了、排除、不想要”必须解析为否定约束。
2. 否定约束进入 LLM 生成解释前必须被程序执行。
3. must_not 是硬过滤，不是扣分。
4. 被排除商品不得进入候选集，更不能出现在商品卡片中。
```

# 受控多跳 RAG

本项目需要考虑多跳，但不做开放式无限多跳 Agent。

推荐定义为：

```text
受控多跳 RAG / 计划式检索
```

## 需要多跳的场景

| 场景 | 多跳方式 |
|---|---|
| 单品推荐 | 单跳检索即可 |
| 反选约束 | 约束解析 + 硬过滤，不算复杂多跳 |
| 商品对比 | session lookup -> product detail -> 对比解释 |
| 场景组合 | scenario -> slot decomposition -> parallel retrieval |
| 商品级追问 | focus_product lookup -> constraints merge -> replacement retrieval |
| 购物车指代 | last_product_ids/cart_items -> product_id -> cart update |

## 场景组合示例

用户：

```text
下周去三亚度假，帮我搭配一套从防晒到穿搭的方案
```

LLM 输出：

```json
{
  "intent": "scenario_bundle_recommendation",
  "retrieval_mode": "decompose_parallel",
  "scenario": "三亚度假",
  "scene_tags": ["海边", "高温", "强紫外线", "轻便", "度假"],
  "bundle_slots": [
    {
      "slot": "防晒霜",
      "category": "防晒霜",
      "retrieval_query": "三亚 海边 高倍 清爽 防水 防晒霜"
    },
    {
      "slot": "晒后修复",
      "category": "晒后修复",
      "retrieval_query": "晒后修复 舒缓 补水 芦荟"
    },
    {
      "slot": "遮阳帽",
      "category": "遮阳帽",
      "retrieval_query": "海边旅行 防晒 宽檐 轻便 遮阳帽"
    }
  ]
}
```

后端对每个 slot 并行检索，最后组合成 bundle。

# 低压力交互设计

## 文本层：先理解用户，再推荐

AI 回复结构：

```text
1. 我理解你的核心在意点是……
2. 所以我会优先排除/优先满足……
3. 这款更适合作为首选，因为……
4. 如果你想要更便宜/更清爽/更户外，我可以继续换。
```

避免：

```text
以下是搜索结果。
为你找到 10 个商品。
请你自己比较。
```

## 商品层：主推 1 个产品

推荐展示策略：

```text
主推商品：1 个，最大视觉权重。
备选商品：1-2 个，弱化展示。
继续调整入口：更便宜、更清爽、更适合户外、不要这个品牌。
```

# 以商品为锚点的多轮导购

这是本项目最重要的差异化设计。

## 核心思想

```text
普通 RAG：用户问 -> 检索 -> 给很多结果 -> 用户自己筛。
本项目：用户问 -> 系统主推商品 -> 用户围绕商品修正 -> 系统基于当前商品上下文换更合适的。
```

## 前端流程

```text
用户看到主推商品卡片
  -> 点击卡片
  -> ProductDetailBottomSheet 浮起
  -> 用户查看“为什么推荐给你”
  -> 用户在底部输入：这个有点贵，有没有100以内的？
  -> Android 发送 product_followup + focus_product_id
  -> 后端在保留原始约束基础上更新 price_max=100
  -> 返回 focus_text_delta 和 replacement_product
  -> 浮层内显示替代商品
```

## 为什么可以避免上下文污染

后端维护两层上下文：

```json
{
  "session_id": "demo_session_001",
  "global_profile": {
    "skin_type": "油皮",
    "budget_max": 150,
    "excluded_ingredients": ["酒精"],
    "excluded_brand_regions": ["日本"]
  },
  "active_focus": {
    "focus_type": "product",
    "product_id": "sku_101",
    "product_name": "高倍清爽防晒乳",
    "local_constraints": {
      "need_cheaper": true,
      "price_max": 100,
      "prefer_texture": "更清爽"
    },
    "followup_history": [
      "这个有点贵，换个100以内的"
    ]
  }
}
```

普通输入框消息走 `user_message`，商品详情浮层输入框消息走 `product_followup`。这样不同商品、不同类目的多轮对话不容易互相污染。

# Android 端详细实现

## Android 端职责

```text
1. 聊天主界面
2. 文字输入
3. 语音输入 ASR
4. WebSocket 流式通信
5. AI 文字逐字渲染
6. 主推商品卡片实时渲染
7. 商品详情 BottomSheet
8. 商品级追问输入框
9. 替代商品渲染
10. 场景组合方案分组展示
11. TTS 音频流播放
12. 购物车增删改查
13. 商品数量编辑
14. 模拟下单确认
```

## 推荐参考项目

| 项目 | 借鉴点 |
|---|---|
| Now in Android | Compose、现代工程结构、Design System、UDF、Repository |
| Android Compose Samples / Jetchat | 聊天消息、输入栏、Compose UI 组织 |
| Android Architecture Samples | ViewModel per screen、Repository、Flow、Navigation Compose |
| Sunflower | 详情页、图片与内容布局、Material 风格 |
| Pokedex Compose | 卡片、详情页、图片加载、动效 |
| AndroidX Media / UAMP | 音频播放生命周期设计 |

注意：只借鉴结构和写法，不直接照搬整个项目。

## Android 模块结构

```text
config/                    配置与 session
data/model/                UI 与协议模型
data/remote/               WebSocket 和 REST client
data/local/                session 本地存储
vm/                         ViewModel
ui/screen/                  页面
ui/component/               组件
voice/                      SpeechRecognizer 封装
audio/                      AudioTrack 封装
navigation/                 Compose Navigation
```

## ChatScreen

组件：

```text
TopBar：标题、购物车 badge
LazyColumn：消息流
MessageBubble：用户/AI 气泡
ProductCard：主推商品
BundleSection：组合方案
ChatInputBar：普通输入栏
ProductDetailBottomSheet：商品详情浮层
```

## ProductDetailBottomSheet

结构：

```text
商品大图
商品名/价格/标签
为什么推荐给你
关键属性
不适合谁
加入购物车
Quick Actions
针对这款商品继续问的输入框
替代商品区域
```

# WebSocket 协议

## user_message

```json
{
  "type": "user_message",
  "session_id": "demo_session_001",
  "message": "推荐防晒霜，但不要含酒精，也不要日系品牌",
  "input_type": "text",
  "tts_enabled": true
}
```

## text_delta

```json
{
  "type": "text_delta",
  "message_id": "assistant_001",
  "text": "我理解你更在意的是"
}
```

## products_start

```json
{
  "type": "products_start",
  "message_id": "assistant_001",
  "layout": "primary_plus_alternatives",
  "expected_count": 3,
  "title": "我先帮你主推这一款"
}
```

## product_item

```json
{
  "type": "product_item",
  "message_id": "assistant_001",
  "index": 0,
  "role": "primary",
  "product": {
    "product_id": "sku_101",
    "name": "清爽通勤防晒乳",
    "price": 129,
    "tags": ["不含酒精", "清爽", "通勤"],
    "reason": "符合你对成分和品牌来源的要求"
  }
}
```

## product_followup

Android 发给后端：

```json
{
  "type": "product_followup",
  "session_id": "demo_session_001",
  "focus_product_id": "sku_101",
  "message": "这个有点贵，有没有100以内的？",
  "tts_enabled": true
}
```

## focus_text_delta

```json
{
  "type": "focus_text_delta",
  "focus_product_id": "sku_101",
  "text": "你主要是不太满意价格，所以我保留原来的排除条件，再把预算压到100以内重新筛选。"
}
```

## replacement_product

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

## bundle_start / bundle_item / bundle_done

用于三亚度假等场景组合方案。

# 购物车设计

购物车必须支持：

```text
1. 加入商品
2. 加入整套 bundle
3. 删除商品
4. 修改数量
5. 全选/取消选择
6. 合计金额
7. 模拟下单
```

# 语音输入与 TTS

ASR 使用 Android `SpeechRecognizer`。

TTS 不在客户端调用第三方 API。客户端只接收后端推来的 `audio_delta`，用 `AudioTrack` 播放 PCM。

# 端到端评测

必须评测：

```text
1. 意图识别准确率
2. 否定约束违反率
3. 主推商品约束满足率
4. 商品级追问正确率
5. 替代商品约束继承正确率
6. 场景组合 slot 覆盖率
7. 购物车操作准确率
8. first token latency
9. first product card latency
10. first audio latency
```

# 三周计划

## Week 1：跑通 Android 主流程

```text
Day 1：创建 Compose 工程和基础结构
Day 2：ChatScreen + MessageBubble + ChatInputBar
Day 3：Mock 流式文本
Day 4：ProductCard + Skeleton
Day 5：WebSocket text_delta
Day 6：products_start / product_item
Day 7：真机 Demo 普通推荐
```

## Week 2：完成差异化体验

```text
Day 8：购物车页面
Day 9：购物车 CRUD
Day 10：ProductDetailBottomSheet
Day 11：product_followup 协议
Day 12：replacement_product 渲染
Day 13：ASR
Day 14：TTS AudioTrack
```

## Week 3：评测与打磨

```text
Day 15：三亚 bundle 展示
Day 16：反选约束 Demo
Day 17：UI 动效和错误处理
Day 18：端到端评测
Day 19：录屏和文档
Day 20：答辩彩排
Day 21：最终修 bug
```

# 两人分工

## 后端/RAG 同学

```text
LLM 检索计划生成
constraint validator
hard filter
RAG 检索
分层排序
受控多跳
product_focus_handler
购物车服务
TTS stream
评测脚本
```

## Android 同学

```text
Compose 工程
ChatScreen
ProductCard
ProductDetailBottomSheet
product_followup
BundleSection
CartScreen
SpeechRecognizer
AudioTrack
WebSocket client
Demo 录屏
```

# 答辩亮点

```text
1. 不是普通搜索，而是低压力导购。
2. 不甩一堆结果，而是主推一个具体产品。
3. 支持反选约束，否定条件进入硬过滤。
4. 支持受控多跳 RAG。
5. 支持三亚度假等场景组合推荐。
6. 支持以商品为锚点的多轮追问。
7. 支持商品详情浮层内替代商品推荐。
8. 支持文字、卡片、TTS 多通道流式体验。
9. 支持购物车完整闭环。
10. 有端到端评测框架。
```

# 参考资料

- Android 官方 Compose Samples / Jetchat：https://github.com/android/compose-samples
- Android 官方 Now in Android：https://github.com/android/nowinandroid
- Android Architecture Samples：https://github.com/android/architecture-samples
- Jetpack Compose UDF 文档：https://developer.android.com/develop/ui/compose/architecture
- SpeechRecognizer API：https://developer.android.com/reference/android/speech/SpeechRecognizer
- AudioTrack API：https://developer.android.com/reference/android/media/AudioTrack
- OpenAI Codex CLI：https://developers.openai.com/codex/cli
- OpenAI Codex AGENTS.md 指南：https://developers.openai.com/codex/guides/agents-md

# Android UI 详细规范

## 视觉基调

本项目需要避免“工程 Demo 感”，但也不能做成过度花哨的电商活动页。推荐风格：

```text
轻商务
圆润
清爽
有 AI 感
有电商可信度
减少用户决策压力
```

## 页面布局

### ChatScreen

```text
SafeArea / WindowInsets
  TopBar：64dp 左右
  MessageList：LazyColumn，占据主体区域
  ChatInputBar：底部固定，支持键盘避让
  ProductDetailBottomSheet：覆盖在 ChatScreen 上，不离开聊天流
```

### TopBar

```text
左侧：AI 助手头像或简洁图标
中间：智能导购助手 / 懂你需求的购物助手
右侧：购物车图标 + badge
```

### ChatInputBar

```text
左：麦克风按钮
中：输入框，占主宽度
右：发送按钮
```

输入框 placeholder：

```text
说说你想买什么，比如“油皮防晒，不要酒精”
```

## 气泡设计

### 用户气泡

```text
对齐：右侧
背景：主色
文字：白色
圆角：20dp
内边距：12dp horizontal / 10dp vertical
最大宽度：屏幕 78%
```

### AI 气泡

```text
对齐：左侧
背景：白色
文字：深灰
圆角：20dp
内边距：12dp horizontal / 10dp vertical
最大宽度：屏幕 84%
阴影：极轻
```

## 商品卡片设计

### 主推商品卡片

```text
宽度：屏幕宽度 - 32dp
高度：可自适应
圆角：24dp
背景：白色
图片：顶部 180-220dp
价格：醒目
标签：最多 3 个
按钮：加入购物车 / 查看详情
```

主推商品卡片必须比备选商品卡片更醒目，让用户明确系统已经替他做出了“主推荐”。

### 备选商品卡片

```text
宽度：220dp
圆角：20dp
图片：120dp
内容简化
```

备选商品是降噪设计，不是主要决策入口。

## ProductDetailBottomSheet 设计

### 高度策略

```text
初始高度：屏幕 70%-85%
可上拉全屏
可下滑关闭
不直接跳转页面
```

### 内容顺序

```text
1. 商品大图
2. 商品名
3. 价格
4. 核心标签
5. 为什么推荐给你
6. 与用户约束匹配的证据
7. 可能不适合的情况
8. 操作按钮
9. Quick Actions
10. 商品级追问输入框
11. 替代商品响应区
```

## Quick Actions 文案

```text
换个更便宜的
换个更清爽的
不要这个品牌
更适合户外
更适合敏感肌
加入购物车
```

点击 quick action 不需要用户再输入，直接发送 product_followup。

# Android 数据模型详细定义

## ProductUiModel

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
    val isPrimary: Boolean = false,
    val brand: String? = null,
    val category: String? = null,
    val attributes: Map<String, String> = emptyMap()
)
```

## BundleUiModel

```kotlin
data class BundleUiModel(
    val bundleId: String,
    val scenario: String,
    val title: String,
    val groups: List<BundleGroupUiModel> = emptyList(),
    val quickActions: List<String> = emptyList(),
    val isStreaming: Boolean = true
)

data class BundleGroupUiModel(
    val groupName: String,
    val slots: List<BundleSlotUiModel> = emptyList()
)

data class BundleSlotUiModel(
    val slot: String,
    val product: ProductUiModel?,
    val isLoading: Boolean = true
)
```

## ProductFocusUiState

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

# Android ViewModel 职责拆分

## ChatViewModel

负责：

```text
1. 管理 ChatUiState
2. 建立和关闭 WebSocket
3. 发送 user_message
4. 处理 text_delta/products/bundle/audio/cart_update/error
5. 打开商品详情 focus
6. 协调 StreamingAudioPlayer
```

不要负责：

```text
1. 复杂购物车状态
2. 具体 SpeechRecognizer 生命周期
3. 复杂商品详情本地业务
```

## ProductFocusViewModel

负责：

```text
1. ProductDetailBottomSheet 状态
2. 发送 product_followup
3. 处理 focus_text_delta
4. 处理 replacement_product
5. Quick Actions 映射
6. 替代商品点击后切换 focus
```

## CartViewModel

负责：

```text
1. 加购
2. 删除
3. 数量编辑
4. 全选
5. 合计金额
6. 模拟下单
```

# 后端模块详细拆解

## QueryUnderstandingService

输入：

```text
user_message
session_profile
active_focus 可选
```

输出：

```text
intent
category
hard_constraints
soft_preferences
retrieval_query
need_clarification
retrieval_mode
```

## ConstraintValidator

必须做：

```text
1. JSON Schema 校验
2. 字段白名单
3. 类目标准化
4. 品牌映射
5. 成分同义词扩展
6. 价格区间标准化
7. 与商品库字段对齐
```

## RetrievalExecutor

执行模式：

```text
single：单品检索
state_then_detail：商品对比 / 指代解析
decompose_parallel：场景组合 slot 并行检索
product_focus_replacement：围绕当前商品替代检索
cart_action：购物车动作
```

## Ranker

排序流程：

```text
1. Hard Filter
2. Eligibility Tier
3. In-tier Ranking
4. Primary selection
5. Alternative selection
```

## GroundedGenerator

只做：

```text
1. 根据真实商品生成推荐理由
2. 根据被满足约束生成解释
3. 根据未满足软偏好生成谨慎说明
4. 生成低压力 quick action 文案
```

禁止：

```text
1. 编造商品属性
2. 编造库存
3. 编造价格
4. 编造成分
5. 编造品牌来源
```

# LLM 检索计划 Prompt 模板

```text
你是电商导购系统中的 Query Understanding 模块。
你的任务不是直接推荐商品，而是把用户输入解析成可执行检索计划 JSON。

必须遵守：
1. 用户明确说“不要、不含、排除、不能、有无”等否定条件时，写入 hard_constraints.must_not。
2. 预算、类目、库存、排除成分、排除品牌地区属于 hard constraint。
3. 场景、质地、风格、偏好属于 soft_preferences，除非用户明确说“必须”。
4. 如果用户是在商品详情里追问，会提供 focus_product_id，你必须生成 product_focus_replacement 计划。
5. 不要输出自然语言解释，只输出 JSON。

输出字段：
intent, retrieval_mode, category, hard_constraints, soft_preferences, retrieval_query, bundle_slots, focus_product_id, need_clarification。
```

# LLM 解释生成 Prompt 模板

```text
你是一个专业、克制、亲和的电商导购助手。
你只能基于后端提供的真实候选商品信息回答。
不要编造商品属性、价格、库存、品牌来源或成分。

回答结构：
1. 用一句话说明你理解到的用户核心在意点。
2. 用一句话说明你如何筛选，例如排除了哪些风险。
3. 明确主推商品。
4. 解释 2-3 条为什么适合。
5. 给出低成本修正入口，例如更便宜、更清爽、更适合户外。

语气：专业、自然、克制。
避免：亲爱的、宝宝、绝对、闭眼入。
```

# 详细后端伪代码

```python
async def handle_user_message(payload):
    session = load_session(payload.session_id)
    plan = await llm_generate_plan(payload.message, session)
    plan = validate_and_normalize_plan(plan)

    if plan.intent == "cart_action":
        return await handle_cart_action(plan, session)

    if plan.retrieval_mode == "single":
        candidates = retrieve_single(plan)
    elif plan.retrieval_mode == "decompose_parallel":
        candidates = await retrieve_bundle_slots(plan)
    elif plan.retrieval_mode == "state_then_detail":
        candidates = retrieve_state_then_detail(plan, session)
    else:
        candidates = retrieve_single(plan)

    ranked = tiered_rank(candidates, plan)
    primary, alternatives = select_primary_and_alternatives(ranked)

    async for event in stream_grounded_response(plan, primary, alternatives):
        yield event
```

```python
async def handle_product_followup(payload):
    session = load_session(payload.session_id)
    focus = load_product_focus(payload.session_id, payload.focus_product_id)
    product = get_product(payload.focus_product_id)

    plan = await llm_generate_product_followup_plan(
        followup=payload.message,
        focus_product=product,
        origin_constraints=focus.origin_constraints,
        local_history=focus.followup_history,
    )
    plan = validate_and_normalize_plan(plan)

    candidates = retrieve_replacement_products(plan, exclude_product_id=product.id)
    ranked = tiered_rank(candidates, plan)
    replacement = select_best_replacement(ranked)

    yield focus_text_delta(...)
    yield replacement_product(...)
    yield focus_done(...)
```

# WebSocket 事件处理表

| 事件 | Android 位置 | 行为 |
|---|---|---|
| text_delta | ChatViewModel | 追加到 AI 气泡 |
| products_start | ChatViewModel | 显示商品 skeleton |
| product_item | ChatViewModel | 插入主推/备选商品卡片 |
| products_done | ChatViewModel | 停止商品 loading |
| bundle_start | ChatViewModel | 创建 BundleSection |
| bundle_item | ChatViewModel | 插入对应分组 |
| bundle_done | ChatViewModel | 显示 quick actions |
| focus_text_delta | ProductFocusViewModel | 追加到底部浮层解释 |
| replacement_product | ProductFocusViewModel | 显示替代商品 |
| focus_done | ProductFocusViewModel | 停止 focus loading |
| audio_delta | StreamingAudioPlayer | 入队播放 |
| cart_update | CartViewModel / ChatViewModel | 更新 badge |
| error | 当前 ViewModel | Snackbar |

# Mock 数据建议

## 防晒 mock 商品

```json
{
  "product_id": "sun_001",
  "name": "清爽通勤防晒乳 SPF50",
  "price": 129,
  "brand": "国产品牌A",
  "brand_region": "中国",
  "category": "防晒霜",
  "ingredients": ["水", "二氧化钛", "透明质酸"],
  "exclude_ingredients": ["酒精"],
  "tags": ["不含酒精", "清爽", "通勤", "SPF50"],
  "stock": 20
}
```

## 100 元以内替代商品

```json
{
  "product_id": "sun_002",
  "name": "轻薄日常防晒乳 SPF30",
  "price": 89,
  "brand": "国产品牌B",
  "brand_region": "中国",
  "category": "防晒霜",
  "ingredients": ["水", "氧化锌"],
  "tags": ["不含酒精", "轻薄", "通勤"],
  "stock": 15
}
```

# 风险清单与规避策略

| 风险 | 表现 | 规避 |
|---|---|---|
| 推荐像搜索 | 一次给很多卡片 | 主推 1 个，备选少量 |
| LLM 漏掉否定约束 | 推荐了含酒精商品 | must_not 硬过滤 |
| 上下文污染 | 防晒约束套到耳机 | product_followup 携带 focus_product_id |
| TTS 卡顿 | 音频断续 | 先缓存 200-500ms，失败降级 |
| Android 任务过大 | Codex 改崩项目 | 每次只执行一个 md |
| UI 不够好看 | 工程 demo 感 | 先 mock 精修卡片和 BottomSheet |
| 联调阻塞 | 后端没完 Android 做不了 | FastAPI mock server |

# Codex 任务执行总表

| 任务 | 目标 | 验收 |
|---|---|---|
| Task 02 | 工程骨架 | App 可启动 |
| Task 03 | 聊天 UI | mock 流式文本 |
| Task 04 | WebSocket | text_delta 通 |
| Task 05 | 商品卡片/bundle | 卡片逐张出现 |
| Task 06 | 购物车 | 增删改查 |
| Task 07 | ASR/TTS | 真机可用 |
| Task 09 | 商品 focus | BottomSheet + product_followup |
| Task 10 | Mock Server | 前端可独立演示 |
| Task 08 | 测试验收 | Demo 脚本跑通 |

# 最终 Demo 路线

## 路线 A：主推商品与低压力导购

```text
用户：推荐一款适合油皮的洗面奶，预算100以内
系统：先理解“控油、温和、预算”的动机
系统：主推一个商品
用户：点开商品详情
系统：显示为什么推荐
```

## 路线 B：反选约束

```text
用户：推荐防晒霜，但不要含酒精，也不要日系品牌
系统：说明已经排除含酒精和日系品牌
系统：主推非日系、不含酒精商品
```

## 路线 C：商品级追问

```text
用户：点开主推商品
用户：这个有点贵，有没有100以内的？
系统：解释保留原约束并降低预算
系统：返回替代商品
```

## 路线 D：场景组合

```text
用户：下周去三亚度假，帮我搭配一套从防晒到穿搭的方案
系统：分组展示防晒护理、穿搭、出行配件
系统：一键加入购物车
```

## 路线 E：语音和 TTS

```text
用户点击麦克风说需求
系统识别中文并发送
AI 文本流式输出，同时 TTS 播报
```

# 附录：给 Codex 的一次性开局 Prompt

```text
你是 Android Kotlin + Jetpack Compose 工程师。
请先阅读 AGENTS.md 和 prompts/PROMPT_INDEX.md。
当前项目目标是实现 ShopGuide Agent Android 原生客户端。

重要原则：
1. 不要一次性实现所有功能。
2. 每次只执行我指定的任务 md。
3. 每次完成后必须运行 ./gradlew :app:assembleDebug。
4. 商品推荐逻辑不写在 Android 端。
5. Android 端重点实现聊天流、商品卡片、商品详情 BottomSheet、product_followup、购物车、ASR、TTS。

请先只检查项目结构，告诉我是否满足执行 prompts/02_TASK_PROJECT_SCAFFOLD.md 的前置条件。
```

# 附录：给后端同学的对齐 Prompt

```text
你是 ShopGuide Agent 后端工程师。
请实现一个支持 Android 流式导购体验的 FastAPI 后端。

系统不是搜索引擎式商品列表，而是低压力导购：
1. LLM 先生成结构化 retrieval_plan。
2. 后端 validator 校验并标准化约束。
3. hard_constraints 必须硬过滤。
4. 排序使用 Hard Filter -> Eligibility Tier -> In-tier Ranking。
5. 默认返回一个主推商品和少量备选。
6. 支持 product_followup：消息必须绑定 focus_product_id。
7. product_followup 要继承原始约束，只更新局部不满意点。
8. WebSocket 必须支持 text_delta、products_start、product_item、products_done、focus_text_delta、replacement_product、bundle_start、bundle_item、bundle_done、audio_delta、cart_update、done、error。
9. 同时提供购物车 REST 接口。
10. 实现 mock 数据，保证 Android 可独立联调。
```
