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
