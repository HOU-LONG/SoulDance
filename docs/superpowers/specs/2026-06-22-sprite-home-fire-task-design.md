# Sprite Home 火星与任务中心设计文档

## 1. 背景与目标

当前 Sprite Home 已完成精灵空间的重设计，但底部操作区仍显厚重，且"领火星"与亲密度、购物抵扣之间的协调逻辑尚未完整呈现。本文档定义：

1. 清理底部视觉残留，统一按钮风格；
2. 把"领火星"入口扩展为可滑出的任务中心 BottomSheet；
3. 建立"任务完成 → 奖励可领取 → 火星到账"的自动状态流转；
4. 把火星明确为购物抵扣金，并根据亲密度等级对火星收益进行加成。

## 2. 范围

**在范围内：**
- `BottomActionBar` 视觉重构（统一三按钮尺寸、圆角、阴影）。
- 新增 `TaskCenterBottomSheet` Composable。
- `SpriteHomeUiState` / `SpriteHomeViewModel` 中任务列表、领取、加成、抵扣相关状态与逻辑。
- 商品卡片与结算页两处火星抵扣提示（仅 UI 展示与计算，不涉及真实支付扣减）。
- 亲密度等级分段加成表（四段递增）。
- 对应单元测试与架构测试更新。

**不在范围内：**
- 真实支付通道改造。
- 后端任务配置接口（本次用本地固定任务表 + 可扩展结构）。
- 全量成就体系与社交分享链路（保留入口与占位回调）。

## 3. 设计方案

### 3.1 底部操作区清理

采用 visual companion 中确认的方案 A：

- 三个按钮统一高度 **96 dp**，圆角 **28 dp**；
- 装扮、购物车使用统一的白色半透明背景（alpha 0.72），边框 1 dp，阴影 4 dp；
- 领火星按钮使用渐变背景（`#FFF4A9` → `#FFCC5C`），同高但视觉重心通过颜色和图标大小区分；
- 三个按钮权重保持 `1 : 1.45 : 1`，但不再凸出高度；
- 图标尺寸统一 32 dp，文字使用 `titleMedium`；
- 火星余额显示在领火星按钮内，格式 `⭐ 886`。

### 3.2 任务中心 BottomSheet

点击"领火星"后从底部滑出 `TaskCenterBottomSheet`：

- 标题："任务中心" + 当前火星余额；
- 任务列表：5 类固定任务卡片；
- 每张卡片显示任务名、进度描述、火星奖励、右侧状态按钮；
- 底部提示条："亲密度越高，任务奖励加成越高 · 当前加成 +X%"；
- 点击空白处或拖拽关闭。

#### 任务定义（MVP）

| 任务 ID | 名称 | 条件 | 基础奖励（火星） | 刷新周期 |
| --- | --- | --- | --- | --- |
| `daily_guide_chat` | 每日导购对话 | 完成 1 次智能导购对话 | 8 | 每日 |
| `add_to_cart` | 添加心仪商品 | 加购 1 件商品 | 20 | 每日 |
| `browse_recommendations` | 浏览今日推荐 | 查看 3 个推荐商品 | 10 | 每日 |
| `share_good_product` | 分享好物 | 分享 1 次 | 15 | 每日 |
| `daily_login` | 每日登录 | 进入 Sprite Home | 5 | 每日 |

### 3.3 任务状态流转

每个任务独立维护状态：

```
未开始  →  进行中  →  已完成（可领取）  →  已领取
```

- **进行中**：用户已部分完成，按钮显示"去完成"；
- **已完成**：达成条件后自动切换为"领取"，视觉高亮；
- **已领取**：领取后火星到账，按钮置灰显示"已完成"。

领取动作由 ViewModel 处理：计算实际奖励（基础奖励 × 亲密度加成），更新 `userProfile.firePoints`，并将任务标记为已领取。

### 3.4 亲密度等级分段加成

采用用户确认的四段递增：

| 等级区间 | 加成比例 |
| --- | --- |
| 1 - 10 | +0% |
| 11 - 20 | +10% |
| 21 - 30 | +20% |
| 31+ | +30% |

加成公式：

```
实际火星奖励 = floor(基础奖励 × (1 + 加成比例))
```

加成同时作用于任务奖励和加购奖励，以体现"亲密度越高，获得火星越多"。

### 3.5 火星作为购物抵扣金

#### 抵扣规则

- 兑换比例：**100 火星 = 1 元**；
- 抵扣上限：单笔订单最多抵扣订单金额的 **10%**；
- 可用抵扣额 = min(用户火星余额 / 100, 订单金额 × 10%)。

#### 展示位置

1. **商品卡片 / 详情**：在价格附近显示"可用火星抵扣 ¥X"；
2. **购物车 / 结算页**：显示"可用 X 火星抵扣 ¥Y"，并提供勾选/开关（仅 UI，默认开启）。

抵扣金额仅在 UI 层计算，不影响当前购物链路中的价格数据模型；后续支付改造可消费该字段。

## 4. 数据模型变更

### 4.1 `TaskUiState`

```kotlin
data class TaskUiState(
    val taskId: String,
    val title: String,
    val description: String,
    val currentCount: Int,
    val targetCount: Int,
    val baseFireReward: Int,
    val completed: Boolean,
    val claimed: Boolean,
) {
    val claimable: Boolean get() = completed && !claimed
    val buttonText: String
        get() = when {
            claimed -> "已完成"
            completed -> "领取"
            else -> "去完成"
        }
}
```

### 4.2 `SpriteHomeUiState`

- 将原 `dailyTask: DailyTaskUiState` 替换为 `tasks: List<TaskUiState>`；
- 保留 `earnedStars`（火星余额）在 `userProfile.firePoints` 中；
- 保留 `spiritProgress` 用于加成计算。

### 4.3 `SpriteHomeAction` 新增

```kotlin
object TaskCenterOpened : SpriteHomeAction
object TaskCenterClosed : SpriteHomeAction
data class TaskClaimed(val taskId: String) : SpriteHomeAction
object ProductViewedForTask : SpriteHomeAction
object ProductShared : SpriteHomeAction
```

### 4.4 `SpriteHomeEffect` 新增

```kotlin
object ShowTaskCenter : SpriteHomeEffect
object HideTaskCenter : SpriteHomeEffect
data class ShowClaimedReward(val taskId: String, val firePoints: Int) : SpriteHomeEffect
object NavigateToShare : SpriteHomeEffect  // 占位
```

## 5. UI 组件

### 5.1 `BottomActionBar` 重构

- 提取通用 `HomeActionButton`；
- `EarnFireButton` 继承同一基础样式，仅替换背景和图标；
- 统一高度与阴影。

### 5.2 新增 `TaskCenterBottomSheet`

- 使用 Compose Material3 `ModalBottomSheet`；
- 内部使用 `LazyColumn` 渲染任务列表；
- 每个任务项使用 `TaskListItem`；
- 底部固定提示条 `IntimacyBonusFooter`。

### 5.3 新增 `FireDiscountLabel`

- 可复用组件，接收 `firePoints` 与 `orderAmount`，输出抵扣文案；
- 小尺寸标签，用于商品卡片；
- 大尺寸行，用于结算页。

## 6. 数据流

```
用户行为（对话/加购/浏览/分享/登录）
        ↓
ViewModel.onAction / onRealtimeEvent / onCartOperationEvent
        ↓
更新对应任务进度（currentCount）
        ↓
若 currentCount ≥ targetCount → completed = true，claimable = true
        ↓
UI 自动变为"领取"状态
        ↓
用户点击领取 → ViewModel 计算加成后火星 → 更新 firePoints → 标记 claimed
        ↓
发送 ShowClaimedReward effect，触发 toast/动效
```

加成计算统一由 `FireRewardCalculator` 负责：

```kotlin
object FireRewardCalculator {
    fun bonusRate(level: Int): Float = when {
        level <= 10 -> 0f
        level <= 20 -> 0.10f
        level <= 30 -> 0.20f
        else -> 0.30f
    }

    fun reward(base: Int, level: Int): Int =
        (base * (1 + bonusRate(level))).toInt()

    fun discountAmount(firePoints: Int, orderAmount: Double): Double {
        val fromFire = firePoints / 100.0
        val maxDiscount = orderAmount * 0.10
        return min(fromFire, maxDiscount)
    }
}
```

## 7. 测试策略

### 7.1 单元测试

- `FireRewardCalculatorTest`：验证各等级加成、折扣计算、边界值；
- `SpriteHomeViewModelTest`：
  - 任务完成后 claimable 为 true；
  - 领取后火星正确增加且应用加成；
  - 已领取任务不可重复领取；
  - 加购奖励应用亲密度加成；
- `TaskCenterStateTest`：验证任务状态机转换。

### 7.2 架构测试

- 确保 `SpriteHomeUiState` 不再暴露 `dailyTask` 单一字段；
- 确保抵扣计算不依赖 Android 框架，可在 JVM 测试；
- 确保 BottomSheet 关闭后状态清理。

### 7.3 UI 测试

- 点击"领火星"弹出 BottomSheet；
- 任务完成后按钮文案从"去完成"变为"领取"；
- 领取后变为"已完成"。

## 8. 未解决问题

1. 任务刷新时间是否以自然日 0 点为准？（建议：自然日 0 点刷新，本次用应用启动时重置模拟）。
2. 分享任务的完成判定是否依赖外部回调？（建议：本次用占位 effect，后续接入分享 SDK）。
3. 结算页抵扣开关是否需要在 `ChatUiState` 中持久化选中状态？（建议：本次仅 UI 展示，状态存在结算页局部）。

## 9. 验收标准

- [ ] 底部三个按钮视觉统一，无凸出、无厚重阴影；
- [ ] 点击"领火星"弹出 BottomSheet，展示 5 个任务；
- [ ] 完成任务后对应任务按钮自动变为"领取"；
- [ ] 领取后火星余额增加，加成比例正确；
- [ ] 商品卡片与结算页正确显示火星抵扣金额；
- [ ] 所有新增/修改测试通过。
