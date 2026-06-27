package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ChatExperiencePhase
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.data.model.ProductUiModel

enum class AvatarState {
    IDLE,
    LISTENING,
    THINKING,
    SEARCHING,
    PRESENTING,
    CELEBRATING,
    LEVEL_UP,
    ERROR,
}

data class AvatarAppearance(
    val baseAvatarId: String = "default_avatar",
    val outfitId: String = "default_outfit",
    val accessoryId: String? = "default_accessory",
    val propId: String? = "shopping_bag",
    val backgroundId: String = "warm_room",
)

data class UserProfileUiState(
    val displayName: String = "Guest",
    val avatarUrl: String? = null,
    val partnerAvatarUrl: String? = null,
    val firePoints: Int = 700,
    val identityTitle: String = "默认火花",
    val identityLevel: String = "V2",
)

data class SpiritProgressUiState(
    val spiritName: String = "灵舞",
    val level: Int = 22,
    val currentIntimacy: Int = 215,
    val requiredIntimacy: Int = 2000,
    val intimacyLabel: String = "亲密度",
    val subtitle: String = "我的专属智能购物小助手",
) {
    val progressFraction: Float
        get() = if (requiredIntimacy <= 0) 0f else (currentIntimacy.toFloat() / requiredIntimacy).coerceIn(0f, 1f)
}

data class SpeechBubbleUiState(
    val text: String = "",
    val visible: Boolean = text.isNotBlank(),
    val style: SpeechBubbleStyle = SpeechBubbleStyle.NORMAL,
)

enum class SpeechBubbleStyle {
    NORMAL,
    LISTENING,
    SEARCHING,
    SUCCESS,
    ERROR,
}

data class DailyTaskUiState(
    val taskId: String = "daily_guide_chat",
    val title: String = "每日任务",
    val description: String = "完成1次智能导购对话",
    val currentCount: Int = 0,
    val targetCount: Int = 1,
    val rewardFirePoints: Int = SpriteHomeRewards.GUIDE_TASK_FIRE,
    val completed: Boolean = false,
    val claimed: Boolean = false,
) {
    val progressFraction: Float
        get() = if (targetCount <= 0) 0f else (currentCount.toFloat() / targetCount).coerceIn(0f, 1f)

    val buttonText: String
        get() = when {
            claimed -> "已完成"
            completed -> "领取"
            else -> "去完成"
        }
}

data class ProductPresentationUiState(
    val primaryProduct: ProductUiModel? = null,
    val alternatives: List<ProductUiModel> = emptyList(),
    val expectedCount: Int = 0,
    val receivedCount: Int = 0,
    val completed: Boolean = false,
)

data class AvatarStageUiState(
    val avatarState: AvatarState,
    val appearance: AvatarAppearance,
    val speechBubble: SpeechBubbleUiState,
    val presentingProduct: ProductUiModel?,
    val animationSequence: Long,
)

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
) {
    val displayedAvatarState: AvatarState
        get() = transientAvatarState ?: baseAvatarState

    val avatarState: AvatarState
        get() = displayedAvatarState

    val latestProduct: ProductUiModel?
        get() = presentingProduct

    fun toAvatarStageUiState(): AvatarStageUiState = AvatarStageUiState(
        avatarState = displayedAvatarState,
        appearance = appearance,
        speechBubble = speechBubble,
        presentingProduct = presentingProduct,
        animationSequence = animationSequence,
    )
}

object SpriteHomeRewards {
    const val ADD_TO_CART_FIRE = 20
    const val ADD_TO_CART_INTIMACY = 20
    const val GUIDE_TASK_FIRE = 8
    const val GUIDE_TASK_INTIMACY = 10
}

object SpriteHomeStateMapper {
    @JvmStatic
    fun baseAvatarStateFromChatState(state: ChatUiState): AvatarState = when {
        state.phase == ChatExperiencePhase.Error || !state.errorMessage.isNullOrBlank() -> AvatarState.IDLE
        state.phase == ChatExperiencePhase.RecommendationLoading -> AvatarState.SEARCHING
        state.phase == ChatExperiencePhase.AssistantThinking -> AvatarState.THINKING
        state.phase == ChatExperiencePhase.UserSending -> AvatarState.THINKING
        state.isSending -> AvatarState.THINKING
        latestProduct(state) != null -> AvatarState.PRESENTING
        else -> AvatarState.IDLE
    }

    @JvmStatic
    fun transientAvatarStateFromChatState(state: ChatUiState): AvatarState? = when {
        state.phase == ChatExperiencePhase.Error || !state.errorMessage.isNullOrBlank() -> AvatarState.ERROR
        else -> null
    }

    @JvmStatic
    fun avatarStateFromChatState(state: ChatUiState): AvatarState =
        transientAvatarStateFromChatState(state) ?: baseAvatarStateFromChatState(state)

    @JvmStatic
    fun latestProduct(state: ChatUiState): ProductUiModel? = state.messages
        .asReversed()
        .firstNotNullOfOrNull { message ->
            message.products.firstOrNull { it.isPrimary } ?: message.products.firstOrNull()
        }

    fun speechFor(state: AvatarState, product: ProductUiModel? = null): SpeechBubbleUiState = when (state) {
        AvatarState.IDLE -> SpeechBubbleUiState()
        AvatarState.LISTENING -> SpeechBubbleUiState("我在听，说说你想买什么", style = SpeechBubbleStyle.LISTENING)
        AvatarState.THINKING -> SpeechBubbleUiState("让我想想，正在帮你挑", style = SpeechBubbleStyle.SEARCHING)
        AvatarState.SEARCHING -> SpeechBubbleUiState("正在找好物", style = SpeechBubbleStyle.SEARCHING)
        AvatarState.PRESENTING -> SpeechBubbleUiState(product?.let { "推荐 ${it.name}" } ?: "找到合适好物")
        AvatarState.CELEBRATING -> SpeechBubbleUiState("加购成功，亲密度提升", style = SpeechBubbleStyle.SUCCESS)
        AvatarState.LEVEL_UP -> SpeechBubbleUiState("等级提升啦", style = SpeechBubbleStyle.SUCCESS)
        AvatarState.ERROR -> SpeechBubbleUiState("刚才没听清，我们再试一次", style = SpeechBubbleStyle.ERROR)
    }
}
