package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ChatExperiencePhase
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.data.model.ProductUiModel

enum class AvatarState {
    IDLE,
    LISTENING,
    SEARCHING,
    PRESENTING,
    CELEBRATING,
    LEVEL_UP,
    ERROR,
}

data class SpriteLayerSet(
    val baseResId: Int? = null,
    val outfitResId: Int? = null,
    val accessoryResId: Int? = null,
    val propResId: Int? = null,
)

data class SpriteHomeUiState(
    val avatarState: AvatarState = AvatarState.IDLE,
    val userAvatarUri: String? = null,
    val partnerAvatarUri: String? = null,
    val fireValue: Int = 698,
    val identity: String = "\u9ed8\u8ba4\u8bc1\u4ef6",
    val identityBadge: String = "V2",
    val newOutfitTitle: String = "\u6570\u7801\u8fbe\u4eba",
    val newOutfitBadge: String = "\u65b0",
    val spriteName: String = "\u8d2d\u8d2d\u5b9d\u5b9d",
    val level: Int = 22,
    val intimacy: Int = 115,
    val intimacyMax: Int = 2000,
    val intimacyLabel: String = "\u4eb2\u5bc6\u5ea6",
    val subtitle: String = "\u6211\u7684\u4e13\u5c5e\u667a\u80fd\u8d2d\u7269\u5c0f\u52a9\u624b",
    val speechText: String? = "\u60f3\u6362\u65b0\u88c5\u626e",
    val earnedStars: Int = 886,
    val dailyTaskTitle: String = "\u6bcf\u65e5\u4efb\u52a1",
    val dailyTaskDescription: String = "\u5b8c\u62101\u6b21\u667a\u80fd\u5bfc\u8d2d\u5bf9\u8bdd",
    val dailyTaskProgress: Int = 0,
    val dailyTaskTarget: Int = 1,
    val latestProduct: ProductUiModel? = null,
    val spriteLayers: SpriteLayerSet = SpriteLayerSet(),
) {
    val intimacyProgress: Float
        get() = if (intimacyMax <= 0) 0f else intimacy.toFloat() / intimacyMax.toFloat()
}

object SpriteHomeRewards {
    const val ADD_TO_CART_FIRE = 20
    const val ADD_TO_CART_INTIMACY = 20
    const val GUIDE_TASK_FIRE = 8
    const val GUIDE_TASK_INTIMACY = 10
}

object SpriteHomeStateMapper {
    @JvmStatic
    fun avatarStateFromChatState(state: ChatUiState): AvatarState = when {
        state.phase == ChatExperiencePhase.Error || !state.errorMessage.isNullOrBlank() -> AvatarState.ERROR
        state.phase == ChatExperiencePhase.RecommendationLoading -> AvatarState.SEARCHING
        state.phase == ChatExperiencePhase.AssistantThinking -> AvatarState.SEARCHING
        state.phase == ChatExperiencePhase.UserSending -> AvatarState.SEARCHING
        state.isSending -> AvatarState.SEARCHING
        latestProduct(state) != null -> AvatarState.PRESENTING
        else -> AvatarState.IDLE
    }

    @JvmStatic
    fun latestProduct(state: ChatUiState): ProductUiModel? = state.messages
        .asReversed()
        .firstNotNullOfOrNull { message ->
            message.products.firstOrNull { it.isPrimary } ?: message.products.firstOrNull()
        }

    fun speechFor(state: AvatarState, product: ProductUiModel? = null): String = when (state) {
        AvatarState.IDLE -> "\u60f3\u6362\u65b0\u88c5\u626e"
        AvatarState.LISTENING -> "\u6211\u5728\u542c\uff0c\u8bf4\u8bf4\u4f60\u60f3\u4e70\u4ec0\u4e48"
        AvatarState.SEARCHING -> "\u6b63\u5728\u627e\u597d\u7269"
        AvatarState.PRESENTING -> product?.let { "\u63a8\u8350 ${it.name}" } ?: "\u627e\u5230\u5408\u9002\u597d\u7269"
        AvatarState.CELEBRATING -> "\u52a0\u8d2d\u6210\u529f\uff0c\u4eb2\u5bc6\u5ea6\u63d0\u5347"
        AvatarState.LEVEL_UP -> "\u7b49\u7ea7\u63d0\u5347\u5566"
        AvatarState.ERROR -> "\u521a\u624d\u6ca1\u542c\u6e05\uff0c\u6211\u4eec\u518d\u8bd5\u4e00\u6b21"
    }
}
