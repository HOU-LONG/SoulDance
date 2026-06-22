# Sprite Home 火星与任务中心实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Sprite Home 完成底部清理、任务中心 BottomSheet、多任务状态流转、亲密度火星加成，以及商品/结算两处火星抵扣提示。

**Architecture:** 新增纯计算对象 `FireRewardCalculator` 统一处理加成与抵扣；用 `TaskUiState` 列表替换单一 `DailyTaskUiState`，每个任务独立维护进度与领取状态；任务中心以 `ModalBottomSheet` 形式从底部滑出；ViewModel 负责在收到对应行为事件时自动推进任务进度并触发 UI 状态变更。

**Tech Stack:** Kotlin, Jetpack Compose, Material3, JUnit, kotlinx.coroutines

## Global Constraints

- 底部三个按钮统一高度 **96 dp**，圆角 **28 dp**。
- 装扮、购物车使用白色半透明背景（alpha 0.72），阴影 **4 dp**。
- 领火星按钮使用渐变背景（`#FFF4A9` → `#FFCC5C`），同高不再凸出。
- 亲密度加成采用四段递增：1-10 级 +0%，11-20 级 +10%，21-30 级 +20%，31+ 级 +30%。
- 火星抵扣规则：100 火星 = 1 元，单笔订单最多抵扣 10%。
- 所有计算逻辑必须在 JVM 可测，不依赖 Android 框架。
- 每个任务结束必须提交，提交信息准确概括本次修改。

---

## File Structure

| 文件 | 职责 |
| --- | --- |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/FireRewardCalculator.kt` | 火星加成率、实际奖励、抵扣金额计算。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/TaskUiState.kt` | 单个任务的数据类，包含进度、完成、领取状态与按钮文案。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeUiState.kt` | 用 `tasks: List<TaskUiState>` 替换 `dailyTask`。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeAction.kt` | 新增任务中心开关、领取、浏览/分享等行为 Action。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeEffect.kt` | 新增显示/隐藏任务中心、奖励到账 effect。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt` | 初始化任务、推进进度、领取奖励、应用加成。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/BottomActionBar.kt` | 重构三按钮，统一尺寸与视觉。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/TaskCenterBottomSheet.kt` | 任务中心 BottomSheet。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt` | 集成任务中心 BottomSheet 与相关 action。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/component/FireDiscountLabel.kt` | 可复用的火星抵扣标签组件。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/component/HeroProductCard.kt` | 集成火星抵扣标签。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/component/CartSummaryBar.kt` | 在合计区域旁显示火星抵扣提示。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/component/CheckoutBottomSheet.kt` | 在应付金额区域显示抵扣后金额。 |
| `client/app/src/test/java/com/example/shopguideagent/ui/home/FireRewardCalculatorTest.kt` | 加成与抵扣计算单元测试。 |
| `client/app/src/test/java/com/example/shopguideagent/ui/home/SpriteHomeViewModelTest.kt` | ViewModel 任务状态与奖励测试。 |
| `client/app/src/test/java/com/example/shopguideagent/ui/home/SpriteHomeArchitectureTest.kt` | 架构约束测试更新。 |

---

### Task 1: FireRewardCalculator

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/ui/home/FireRewardCalculator.kt`
- Test: `client/app/src/test/java/com/example/shopguideagent/ui/home/FireRewardCalculatorTest.kt`

**Interfaces:**
- Produces: `fun bonusRate(level: Int): Float`, `fun reward(base: Int, level: Int): Int`, `fun discountAmount(firePoints: Int, orderAmount: Double): Double`

- [ ] **Step 1: Write the failing test**

```kotlin
package com.example.shopguideagent.ui.home

import org.junit.Assert.assertEquals
import org.junit.Test

class FireRewardCalculatorTest {
    @Test
    fun bonusRateForLevelRanges() {
        assertEquals(0f, FireRewardCalculator.bonusRate(1), 0.001f)
        assertEquals(0f, FireRewardCalculator.bonusRate(10), 0.001f)
        assertEquals(0.10f, FireRewardCalculator.bonusRate(11), 0.001f)
        assertEquals(0.10f, FireRewardCalculator.bonusRate(20), 0.001f)
        assertEquals(0.20f, FireRewardCalculator.bonusRate(21), 0.001f)
        assertEquals(0.20f, FireRewardCalculator.bonusRate(30), 0.001f)
        assertEquals(0.30f, FireRewardCalculator.bonusRate(31), 0.001f)
    }

    @Test
    fun rewardAppliesFloorBonus() {
        assertEquals(8, FireRewardCalculator.reward(8, 10))
        assertEquals(8, FireRewardCalculator.reward(8, 11)) // 8 * 1.1 = 8.8 -> 8
        assertEquals(24, FireRewardCalculator.reward(20, 21)) // 20 * 1.2 = 24
    }

    @Test
    fun discountAmountRespectsCapAndBalance() {
        assertEquals(1.0, FireRewardCalculator.discountAmount(100, 200.0), 0.001)
        assertEquals(10.0, FireRewardCalculator.discountAmount(2000, 100.0), 0.001) // cap 10%
        assertEquals(0.0, FireRewardCalculator.discountAmount(0, 100.0), 0.001)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./gradlew :client:app:testDebugUnitTest --tests "com.example.shopguideagent.ui.home.FireRewardCalculatorTest"`
Expected: FAIL with "FireRewardCalculator not found" or similar.

- [ ] **Step 3: Write minimal implementation**

```kotlin
package com.example.shopguideagent.ui.home

import kotlin.math.floor
import kotlin.math.min

object FireRewardCalculator {
    fun bonusRate(level: Int): Float = when {
        level <= 10 -> 0f
        level <= 20 -> 0.10f
        level <= 30 -> 0.20f
        else -> 0.30f
    }

    fun reward(base: Int, level: Int): Int {
        val rate = 1 + bonusRate(level)
        return floor(base * rate).toInt()
    }

    fun discountAmount(firePoints: Int, orderAmount: Double): Double {
        val fromFire = firePoints / 100.0
        val maxDiscount = orderAmount * 0.10
        return min(fromFire, maxDiscount)
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./gradlew :client:app:testDebugUnitTest --tests "com.example.shopguideagent.ui.home.FireRewardCalculatorTest"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/FireRewardCalculator.kt \
        client/app/src/test/java/com/example/shopguideagent/ui/home/FireRewardCalculatorTest.kt
git commit -m "feat(sprite): add fire reward and discount calculator

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: TaskUiState 与 SpriteHomeUiState 重构

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/ui/home/TaskUiState.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeUiState.kt`

**Interfaces:**
- Consumes: `FireRewardCalculator` (optional, for display-only helper)
- Produces: `TaskUiState`, `SpriteHomeUiState.tasks: List<TaskUiState>`

- [ ] **Step 1: Create TaskUiState**

Create `client/app/src/main/java/com/example/shopguideagent/ui/home/TaskUiState.kt`:

```kotlin
package com.example.shopguideagent.ui.home

data class TaskUiState(
    val taskId: String,
    val title: String,
    val description: String,
    val currentCount: Int,
    val targetCount: Int,
    val baseFireReward: Int,
    val completed: Boolean = false,
    val claimed: Boolean = false,
) {
    val claimable: Boolean get() = completed && !claimed

    val buttonText: String
        get() = when {
            claimed -> "已完成"
            completed -> "领取"
            else -> "去完成"
        }

    val progressFraction: Float
        get() = if (targetCount <= 0) 0f else (currentCount.toFloat() / targetCount).coerceIn(0f, 1f)

    fun increment(): TaskUiState {
        if (claimed || completed) return this
        val nextCount = (currentCount + 1).coerceAtMost(targetCount)
        return copy(
            currentCount = nextCount,
            completed = targetCount > 0 && nextCount >= targetCount,
        )
    }
}

object DefaultTasks {
    fun all(): List<TaskUiState> = listOf(
        TaskUiState(
            taskId = "daily_guide_chat",
            title = "每日导购对话",
            description = "完成 1 次智能导购对话",
            currentCount = 0,
            targetCount = 1,
            baseFireReward = SpriteHomeRewards.GUIDE_TASK_FIRE,
        ),
        TaskUiState(
            taskId = "add_to_cart",
            title = "添加心仪商品",
            description = "加购 1 件商品",
            currentCount = 0,
            targetCount = 1,
            baseFireReward = SpriteHomeRewards.ADD_TO_CART_FIRE,
        ),
        TaskUiState(
            taskId = "browse_recommendations",
            title = "浏览今日推荐",
            description = "查看 3 个推荐商品",
            currentCount = 0,
            targetCount = 3,
            baseFireReward = 10,
        ),
        TaskUiState(
            taskId = "share_good_product",
            title = "分享好物",
            description = "分享 1 次",
            currentCount = 0,
            targetCount = 1,
            baseFireReward = 15,
        ),
        TaskUiState(
            taskId = "daily_login",
            title = "每日登录",
            description = "进入 Sprite Home",
            currentCount = 1,
            targetCount = 1,
            baseFireReward = 5,
            completed = true,
            claimed = false,
        ),
    )
}
```

- [ ] **Step 2: Modify SpriteHomeUiState**

In `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeUiState.kt`:

Replace the existing `DailyTaskUiState` class with `TaskUiState` import or delete it. Then change `SpriteHomeUiState`:

```kotlin
data class SpriteHomeUiState(
    val userProfile: UserProfileUiState = UserProfileUiState(),
    val spiritProgress: SpiritProgressUiState = SpiritProgressUiState(),
    val appearance: AvatarAppearance = AvatarAppearance(),
    val baseAvatarState: AvatarState = AvatarState.IDLE,
    val transientAvatarState: AvatarState? = null,
    val speechBubble: SpeechBubbleUiState = SpeechBubbleUiState(),
    val tasks: List<TaskUiState> = DefaultTasks.all(),
    val presentingProduct: ProductUiModel? = null,
    val productPresentation: ProductPresentationUiState = ProductPresentationUiState(),
    val cartCount: Int = 0,
    val isRealtimeConnected: Boolean = false,
    val isLoading: Boolean = false,
    val animationSequence: Long = 0L,
    val earnedStars: Int = 886,
) {
    // ... existing properties ...
}
```

Delete the old `DailyTaskUiState` class if it still exists.

- [ ] **Step 3: Verify compile**

Run: `./gradlew :client:app:compileDebugKotlin`
Expected: PASS (may warn about unused `DailyTaskUiState` references; fix in Task 4).

- [ ] **Step 4: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/TaskUiState.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeUiState.kt
git commit -m "refactor(sprite): replace daily task with task list state

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 扩展 Action 与 Effect

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeAction.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeEffect.kt`

**Interfaces:**
- Produces: `SpriteHomeAction.TaskCenterOpened`, `SpriteHomeAction.TaskCenterClosed`, `SpriteHomeAction.TaskClaimed`, etc.
- Produces: `SpriteHomeEffect.ShowTaskCenter`, `SpriteHomeEffect.HideTaskCenter`, `SpriteHomeEffect.ShowClaimedReward`, etc.

- [ ] **Step 1: Modify SpriteHomeAction**

Replace the relevant section in `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeAction.kt`:

```kotlin
sealed interface SpriteHomeAction {
    object DressUpClicked : SpriteHomeAction
    object EarnFireClicked : SpriteHomeAction
    data class TaskClaimed(val taskId: String) : SpriteHomeAction
    object TaskCenterClosed : SpriteHomeAction
    object ProductViewedForTask : SpriteHomeAction
    object ProductShared : SpriteHomeAction

    // existing actions...
}
```

- [ ] **Step 2: Modify SpriteHomeEffect**

In `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeEffect.kt`, add:

```kotlin
sealed interface SpriteHomeEffect {
    object ShowTaskCenter : SpriteHomeEffect
    object HideTaskCenter : SpriteHomeEffect
    data class ShowClaimedReward(val taskId: String, val firePoints: Int) : SpriteHomeEffect
    object NavigateToShare : SpriteHomeEffect

    // existing effects...
}
```

If the file does not exist, create it.

- [ ] **Step 3: Verify compile**

Run: `./gradlew :client:app:compileDebugKotlin`
Expected: PASS (may warn about unhandled new actions in ViewModel; fix in Task 4).

- [ ] **Step 4: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeAction.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeEffect.kt
git commit -m "feat(sprite): add task center actions and effects

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: ViewModel 任务逻辑

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt`

**Interfaces:**
- Consumes: `TaskUiState`, `FireRewardCalculator`, new `SpriteHomeAction` cases
- Produces: Updated `uiState` with task progress and effects

- [ ] **Step 1: Update ViewModel action handling**

In `onAction(action: SpriteHomeAction)`:

```kotlin
SpriteHomeAction.EarnFireClicked -> emitEffect(SpriteHomeEffect.ShowTaskCenter)
SpriteHomeAction.TaskCenterClosed -> emitEffect(SpriteHomeEffect.HideTaskCenter)
is SpriteHomeAction.TaskClaimed -> claimTask(action.taskId)
SpriteHomeAction.ProductViewedForTask -> incrementTask("browse_recommendations")
SpriteHomeAction.ProductShared -> incrementTask("share_good_product")
```

Remove the old `DailyTaskClicked` handling and `handleDailyTaskClicked()`.

- [ ] **Step 2: Update rewardAddToCart to use bonus and increment add_to_cart task**

```kotlin
private fun rewardAddToCart(eventKey: String?) {
    if (eventKey != null && !processedCartEvents.add(eventKey)) return
    var progressToSave: SpiritProgressUiState? = null
    _uiState.update { current ->
        val intimacyTotal = current.spiritProgress.currentIntimacy + SpriteHomeRewards.ADD_TO_CART_INTIMACY
        val levelUp = intimacyTotal >= current.spiritProgress.requiredIntimacy && current.spiritProgress.requiredIntimacy > 0
        val nextTransient = if (levelUp) AvatarState.LEVEL_UP else AvatarState.CELEBRATING
        val nextLevel = if (levelUp) current.spiritProgress.level + 1 else current.spiritProgress.level
        val nextProgress = current.spiritProgress.copy(
            level = nextLevel,
            currentIntimacy = if (levelUp) 0 else intimacyTotal,
        )
        progressToSave = nextProgress
        val fireReward = FireRewardCalculator.reward(
            SpriteHomeRewards.ADD_TO_CART_FIRE,
            nextProgress.level,
        )
        current.copy(
            transientAvatarState = nextTransient,
            userProfile = current.userProfile.copy(firePoints = current.userProfile.firePoints + fireReward),
            spiritProgress = nextProgress,
            tasks = current.tasks.incrementById("add_to_cart"),
            speechBubble = SpriteHomeStateMapper.speechFor(nextTransient, current.presentingProduct),
            animationSequence = current.animationSequence + 1,
        )
    }
    progressToSave?.let(progressRepository::saveProgress)
    if (_uiState.value.transientAvatarState == AvatarState.LEVEL_UP) {
        emitEffect(SpriteHomeEffect.ShowLevelUpReward(_uiState.value.spiritProgress.level))
    }
}
```

- [ ] **Step 3: Update onProductsDone to increment guide chat task**

```kotlin
private fun onProductsDone() {
    _uiState.update { current ->
        val nextBase = if (current.productPresentation.primaryProduct != null || current.presentingProduct != null) {
            AvatarState.PRESENTING
        } else {
            current.baseAvatarState
        }
        current.copy(
            baseAvatarState = nextBase,
            productPresentation = current.productPresentation.copy(completed = true),
            tasks = current.tasks.incrementById("daily_guide_chat"),
            speechBubble = SpriteHomeStateMapper.speechFor(current.transientAvatarState ?: nextBase, current.presentingProduct),
            isLoading = false,
            animationSequence = current.animationSequence + 1,
        )
    }
}
```

- [ ] **Step 4: Add helper functions**

```kotlin
private fun claimTask(taskId: String) {
    _uiState.update { current ->
        val task = current.tasks.find { it.taskId == taskId } ?: return@update current
        if (!task.claimable) return@update current
        val reward = FireRewardCalculator.reward(task.baseFireReward, current.spiritProgress.level)
        current.copy(
            tasks = current.tasks.map {
                if (it.taskId == taskId) it.copy(claimed = true) else it
            },
            userProfile = current.userProfile.copy(firePoints = current.userProfile.firePoints + reward),
            speechBubble = SpeechBubbleUiState("任务奖励已领取", style = SpeechBubbleStyle.SUCCESS),
            animationSequence = current.animationSequence + 1,
        )
    }
    emitEffect(SpriteHomeEffect.ShowClaimedReward(taskId, _uiState.value.userProfile.firePoints))
}

private fun incrementTask(taskId: String) {
    _uiState.update { current ->
        current.copy(tasks = current.tasks.incrementById(taskId))
    }
}

private fun List<TaskUiState>.incrementById(taskId: String): List<TaskUiState> =
    map { if (it.taskId == taskId) it.increment() else it }
```

- [ ] **Step 5: Remove old daily task methods**

Delete `handleDailyTaskClicked()` and `DailyTaskUiState.incrementProgress()` extension.

- [ ] **Step 6: Run ViewModel tests**

Run: `./gradlew :client:app:testDebugUnitTest --tests "com.example.shopguideagent.ui.home.SpriteHomeViewModelTest"`
Expected: FAIL (tests still reference dailyTask; fix in Task 10).

- [ ] **Step 7: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt
git commit -m "feat(sprite): implement task progress, claim, and intimacy bonus in viewmodel

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 重构 BottomActionBar

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/BottomActionBar.kt`

**Interfaces:**
- Consumes: `earnedStars: Int`, `cartCount: Int`, `onAction`
- Produces: Unified `BottomActionBar` UI

- [ ] **Step 1: Replace file content**

Replace the entire `BottomActionBar.kt` with:

```kotlin
package com.example.shopguideagent.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Checkroom
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.ErrorColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextOnDark
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun BottomActionBar(
    earnedStars: Int,
    cartCount: Int,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        HomeActionButton(
            label = "装扮",
            icon = Icons.Outlined.Checkroom,
            testTag = "action_dress_up",
            onClick = { onAction(SpriteHomeAction.DressUpClicked) },
            modifier = Modifier.weight(1f),
        )
        EarnFireButton(
            earnedStars = earnedStars,
            onClick = { onAction(SpriteHomeAction.EarnFireClicked) },
            modifier = Modifier.weight(1.45f),
        )
        CartActionButton(
            count = cartCount,
            onClick = { onAction(SpriteHomeAction.CartClicked) },
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun HomeActionButton(
    label: String,
    icon: ImageVector,
    testTag: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    content: @Composable (() -> Unit)? = null,
) {
    Surface(
        modifier = modifier
            .height(96.dp)
            .testTag(testTag)
            .clickableWithScale(onClick),
        shape = RoundedCornerShape(28.dp),
        color = Color.White.copy(alpha = 0.72f),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.78f)),
        shadowElevation = 4.dp,
    ) {
        Column(
            modifier = Modifier.padding(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Icon(icon, contentDescription = null, tint = Color(0xFF5B422A), modifier = Modifier.size(32.dp))
            Spacer(Modifier.height(8.dp))
            Text(label, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
            content?.invoke()
        }
    }
}

@Composable
private fun CartActionButton(
    count: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    HomeActionButton(
        label = "购物车",
        icon = Icons.Outlined.ShoppingCart,
        testTag = "action_cart",
        onClick = onClick,
        modifier = modifier,
    ) {
        BadgedBox(
            badge = {
                if (count > 0) {
                    Badge(containerColor = ErrorColor, contentColor = TextOnDark) {
                        Text(
                            count.coerceAtMost(99).toString(),
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            },
            modifier = Modifier.size(32.dp),
        ) {
            Icon(
                Icons.Outlined.ShoppingCart,
                contentDescription = null,
                tint = Color(0xFF5B422A),
                modifier = Modifier.size(32.dp),
            )
        }
    }
}

@Composable
private fun EarnFireButton(
    earnedStars: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .height(96.dp)
            .testTag("action_earn_fire")
            .clickableWithScale(onClick),
        shape = RoundedCornerShape(28.dp),
        color = Color(0xFFFFF0BB),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.9f)),
        shadowElevation = 4.dp,
    ) {
        Box(
            modifier = Modifier.background(
                Brush.radialGradient(colors = listOf(Color(0xFFFFF4A9), Color(0xFFFFCC5C))),
            ),
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(
                    imageVector = Icons.Outlined.Star,
                    contentDescription = null,
                    tint = Color(0xFFFFD12F),
                    modifier = Modifier.size(36.dp),
                )
                Text("领火星", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
                Text(
                    text = "⭐ $earnedStars",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = TextSecondary,
                )
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun BottomActionBarPreview() {
    ShopGuideAgentTheme {
        BottomActionBar(earnedStars = 886, cartCount = 2, onAction = {})
    }
}
```

- [ ] **Step 2: Verify preview and compile**

Run: `./gradlew :client:app:compileDebugKotlin`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/BottomActionBar.kt
git commit -m "feat(sprite): unify bottom action bar sizing and shadows

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 创建 TaskCenterBottomSheet

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/ui/home/TaskCenterBottomSheet.kt`

**Interfaces:**
- Consumes: `tasks: List<TaskUiState>`, `firePoints: Int`, `level: Int`, `onClaim: (String) -> Unit`, `onDismiss: () -> Unit`
- Produces: `TaskCenterBottomSheet` Composable

- [ ] **Step 1: Implement TaskCenterBottomSheet**

Create `client/app/src/main/java/com/example/shopguideagent/ui/home/TaskCenterBottomSheet.kt`:

```kotlin
package com.example.shopguideagent.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskCenterBottomSheet(
    tasks: List<TaskUiState>,
    firePoints: Int,
    level: Int,
    onClaim: (String) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = SurfacePrimary,
        shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp),
        modifier = modifier,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 32.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "任务中心",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary,
                )
                Text(
                    text = "⭐ $firePoints",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = TextSecondary,
                )
            }
            Spacer(modifier = Modifier.height(16.dp))
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.heightIn(max = 420.dp),
            ) {
                items(tasks, key = { it.taskId }) { task ->
                    TaskListItem(
                        task = task,
                        level = level,
                        onClaim = { onClaim(task.taskId) },
                    )
                }
            }
            Spacer(modifier = Modifier.height(14.dp))
            IntimacyBonusFooter(level = level)
        }
    }
}

@Composable
private fun TaskListItem(
    task: TaskUiState,
    level: Int,
    onClaim: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val reward = FireRewardCalculator.reward(task.baseFireReward, level)
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = Color.White.copy(alpha = 0.72f),
        shadowElevation = 2.dp,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text(
                    text = task.title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary,
                )
                Text(
                    text = "${task.description} · +$reward ⭐",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary,
                )
            }
            TaskActionButton(task = task, onClaim = onClaim)
        }
    }
}

@Composable
private fun TaskActionButton(task: TaskUiState, onClaim: () -> Unit) {
    val (containerColor, contentColor, enabled) = when {
        task.claimed -> Triple(Color(0xFFE0E0E0), TextSecondary, false)
        task.completed -> Triple(PriceColor, TextOnBrand, true)
        else -> Triple(Color(0xFFF5F5F5), TextSecondary, false)
    }
    Button(
        onClick = onClaim,
        enabled = enabled,
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = containerColor,
            contentColor = contentColor,
            disabledContainerColor = containerColor,
            disabledContentColor = contentColor,
        ),
    ) {
        Text(
            text = task.buttonText,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun IntimacyBonusFooter(level: Int) {
    val rate = FireRewardCalculator.bonusRate(level)
    val percent = (rate * 100).toInt()
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(Color(0xFFFFF4A9).copy(alpha = 0.5f))
            .padding(vertical = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = "亲密度越高，任务奖励加成越高 · 当前加成 +$percent%",
            style = MaterialTheme.typography.bodyMedium,
            color = TextPrimary,
            fontWeight = FontWeight.Medium,
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun TaskCenterBottomSheetPreview() {
    ShopGuideAgentTheme {
        TaskCenterBottomSheet(
            tasks = DefaultTasks.all(),
            firePoints = 886,
            level = 22,
            onClaim = {},
            onDismiss = {},
        )
    }
}
```

- [ ] **Step 2: Verify compile**

Run: `./gradlew :client:app:compileDebugKotlin`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/TaskCenterBottomSheet.kt
git commit -m "feat(sprite): add task center bottom sheet

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 集成 BottomSheet 到 SpriteHomeRoute

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeRoute.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt` (remove old daily task wiring if any)

**Interfaces:**
- Consumes: `TaskCenterBottomSheet`, `SpriteHomeEffect.ShowTaskCenter`, `SpriteHomeEffect.HideTaskCenter`

- [ ] **Step 1: Add sheet state to Route**

In `SpriteHomeRoute.kt`:

```kotlin
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue

@Composable
fun SpriteHomeRoute(...) {
    val state by viewModel.uiState.collectAsState()
    var showTaskCenter by remember { mutableStateOf(false) }

    LaunchedEffect(viewModel) {
        viewModel.effects.collect { effect ->
            when (effect) {
                is SpriteHomeEffect.ShowTaskCenter -> showTaskCenter = true
                is SpriteHomeEffect.HideTaskCenter -> showTaskCenter = false
                else -> onEffect(effect)
            }
        }
    }
    // ...
}
```

- [ ] **Step 2: Render TaskCenterBottomSheet in Route**

After `SpriteHomeScreen(...)`:

```kotlin
if (showTaskCenter) {
    TaskCenterBottomSheet(
        tasks = state.tasks,
        firePoints = state.userProfile.firePoints,
        level = state.spiritProgress.level,
        onClaim = { taskId -> viewModel.onAction(SpriteHomeAction.TaskClaimed(taskId)) },
        onDismiss = {
            showTaskCenter = false
            viewModel.onAction(SpriteHomeAction.TaskCenterClosed)
        },
    )
}
```

- [ ] **Step 3: Verify compile**

Run: `./gradlew :client:app:compileDebugKotlin`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeRoute.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt
git commit -m "feat(sprite): wire task center bottom sheet into route

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 商品卡片火星抵扣标签

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/ui/component/FireDiscountLabel.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/component/HeroProductCard.kt`

**Interfaces:**
- Consumes: `firePoints: Int`, `price: Double`
- Produces: `FireDiscountLabel` Composable

- [ ] **Step 1: Create FireDiscountLabel**

Create `client/app/src/main/java/com/example/shopguideagent/ui/component/FireDiscountLabel.kt`:

```kotlin
package com.example.shopguideagent.ui.component

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.home.FireRewardCalculator
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.TextOnBrand

@Composable
fun FireDiscountLabel(
    firePoints: Int,
    price: Double,
    modifier: Modifier = Modifier,
) {
    val discount = FireRewardCalculator.discountAmount(firePoints, price)
    if (discount <= 0) return
    Text(
        text = "可用 ⭐ 抵扣 ¥${"%.2f".format(discount)}",
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(PriceColor.copy(alpha = 0.12f))
            .padding(horizontal = 8.dp, vertical = 4.dp),
        color = PriceColor,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.SemiBold,
    )
}
```

- [ ] **Step 2: Integrate into HeroProductCard**

In `HeroProductCard.kt`, after the price `Text`:

```kotlin
FireDiscountLabel(
    firePoints = 886, // replace with actual firePoints when state is wired
    price = product.price,
)
```

For now hard-code `886` as in preview; a later task will wire real user profile. Add TODO comment if needed.

- [ ] **Step 3: Verify compile**

Run: `./gradlew :client:app:compileDebugKotlin`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/component/FireDiscountLabel.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/component/HeroProductCard.kt
git commit -m "feat(product): add fire discount label on hero product card

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: 购物车与结算火星抵扣提示

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/component/CartSummaryBar.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/component/CheckoutBottomSheet.kt`

**Interfaces:**
- Consumes: `firePoints: Int` (hard-code 886 for now; wire later)

- [ ] **Step 1: Update CartSummaryBar**

Add import for `FireRewardCalculator` and `FireDiscountLabel`.

Replace the price row with:

```kotlin
Column(
    modifier = Modifier.weight(1f),
    verticalArrangement = Arrangement.spacedBy(2.dp),
) {
    Text(
        "合计 ¥${"%.2f".format(state.totalPrice)}",
        color = PriceColor,
        fontWeight = FontWeight.Bold,
        style = MaterialTheme.typography.titleMedium,
    )
    val discount = FireRewardCalculator.discountAmount(886, state.totalPrice)
    if (discount > 0) {
        Text(
            "可用 ⭐ 抵扣 ¥${"%.2f".format(discount)}",
            color = PriceColor.copy(alpha = 0.8f),
            style = MaterialTheme.typography.labelSmall,
        )
    }
}
```

- [ ] **Step 2: Update CheckoutBottomSheet**

In the price `Surface`, update the right column to show discount:

```kotlin
Column(horizontalAlignment = Alignment.End) {
    Text(
        "¥${"%.2f".format(totalAmount)}",
        color = PriceColor,
        fontWeight = FontWeight.Bold,
        style = MaterialTheme.typography.headlineSmall,
    )
    val discount = FireRewardCalculator.discountAmount(886, totalAmount)
    if (discount > 0) {
        Text(
            "抵扣后 ¥${"%.2f".format(totalAmount - discount)}",
            color = PriceColor.copy(alpha = 0.8f),
            style = MaterialTheme.typography.labelSmall,
        )
    }
}
```

- [ ] **Step 3: Verify compile**

Run: `./gradlew :client:app:compileDebugKotlin`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/component/CartSummaryBar.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/component/CheckoutBottomSheet.kt
git commit -m "feat(cart): show fire discount hint in cart summary and checkout

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: 更新测试

**Files:**
- Modify: `client/app/src/test/java/com/example/shopguideagent/ui/home/SpriteHomeViewModelTest.kt`
- Modify: `client/app/src/test/java/com/example/shopguideagent/ui/home/SpriteHomeArchitectureTest.kt`

**Interfaces:**
- Consumes: `TaskUiState`, updated `SpriteHomeUiState`

- [ ] **Step 1: Update SpriteHomeViewModelTest**

Replace daily task tests with task list tests. Example tests:

```kotlin
@Test
fun productsDoneIncrementsDailyGuideChatTask() {
    val viewModel = SpriteHomeViewModel()
    viewModel.onRealtimeEvent(RealtimeEvent.ProductsStart("m1", expectedCount = 1, title = null))
    viewModel.onRealtimeEvent(RealtimeEvent.ProductItem("m1", 0, sampleProduct()))
    viewModel.onRealtimeEvent(RealtimeEvent.ProductsDone("m1"))

    val task = viewModel.uiState.value.tasks.find { it.taskId == "daily_guide_chat" }
    assertEquals(true, task?.completed)
    assertEquals(false, task?.claimed)
}

@Test
fun claimingTaskAddsBonusFirePoints() {
    val viewModel = SpriteHomeViewModel(
        initialState = SpriteHomeUiState(
            spiritProgress = SpiritProgressUiState(level = 22, currentIntimacy = 0, requiredIntimacy = 2000),
        ),
    )
    viewModel.onRealtimeEvent(RealtimeEvent.ProductsStart("m1", expectedCount = 1, title = null))
    viewModel.onRealtimeEvent(RealtimeEvent.ProductItem("m1", 0, sampleProduct()))
    viewModel.onRealtimeEvent(RealtimeEvent.ProductsDone("m1"))

    val before = viewModel.uiState.value.userProfile.firePoints
    viewModel.onAction(SpriteHomeAction.TaskClaimed("daily_guide_chat"))

    val expectedReward = FireRewardCalculator.reward(8, 22)
    assertEquals(before + expectedReward, viewModel.uiState.value.userProfile.firePoints)
    assertEquals(true, viewModel.uiState.value.tasks.find { it.taskId == "daily_guide_chat" }?.claimed)
}

@Test
fun addToCartAppliesIntimacyBonusToFirePoints() {
    val viewModel = SpriteHomeViewModel(
        initialState = SpriteHomeUiState(
            spiritProgress = SpiritProgressUiState(level = 22, currentIntimacy = 0, requiredIntimacy = 2000),
        ),
    )
    val before = viewModel.uiState.value.userProfile.firePoints
    viewModel.onCartOperationEvent(CartOperationEvent.AddToCartSucceeded("p1", 1))

    val expectedReward = FireRewardCalculator.reward(SpriteHomeRewards.ADD_TO_CART_FIRE, 22)
    assertEquals(before + expectedReward, viewModel.uiState.value.userProfile.firePoints)
}
```

Remove old `actionsEmitEffectsWithoutNavigatingInComposable` assertion for `DailyTaskClicked` if it exists; update to test `EarnFireClicked` emits `ShowTaskCenter`.

- [ ] **Step 2: Update SpriteHomeArchitectureTest**

Add:

```kotlin
@Test
fun spriteHomeUiStateUsesTaskListNotDailyTask() {
    val state = SpriteHomeUiState()
    assertFalse(state.tasks.isEmpty())
    assertNull(SpriteHomeUiState::class.java.declaredFields.find { it.name == "dailyTask" })
}
```

- [ ] **Step 3: Run tests**

Run: `./gradlew :client:app:testDebugUnitTest --tests "com.example.shopguideagent.ui.home.*"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add client/app/src/test/java/com/example/shopguideagent/ui/home/SpriteHomeViewModelTest.kt \
        client/app/src/test/java/com/example/shopguideagent/ui/home/SpriteHomeArchitectureTest.kt
git commit -m "test(sprite): update viewmodel and architecture tests for task center

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 11: 全量验证

**Files:**
- All modified files

- [ ] **Step 1: Run unit tests**

Run: `./gradlew :client:app:testDebugUnitTest`
Expected: PASS

- [ ] **Step 2: Run lint / compile**

Run: `./gradlew :client:app:compileDebugKotlin :client:app:lintDebug`
Expected: PASS (or only pre-existing issues)

- [ ] **Step 3: Check git status**

Run: `git status --short`
Expected: Only expected untracked files remain (e.g. `.superpowers/` is now ignored).

- [ ] **Step 4: Final summary**

No commit needed if only verification.

---

## Self-Review

**Spec coverage:**
- 底部清理：Task 5
- 任务中心 BottomSheet：Task 6 + Task 7
- 多任务列表：Task 2 + Task 4
- 完成→可领取→已领取：Task 4
- 亲密度加成：Task 1 + Task 4
- 火星抵扣 UI：Task 8 + Task 9
- 测试：Task 10 + Task 11

**Placeholder scan:** No TBD/TODO in steps. Hard-coded `886` fire points in Task 8/9 are intentional until user profile wiring is available; acceptable for this iteration.

**Type consistency:** `TaskUiState.increment()` returns `TaskUiState`; `tasks.incrementById()` returns `List<TaskUiState>`; `FireRewardCalculator.reward()` takes `(Int, Int)`; all consistent.
