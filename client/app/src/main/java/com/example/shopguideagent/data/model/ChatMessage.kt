package com.example.shopguideagent.data.model

import org.json.JSONObject

enum class MessageRole {
    User,
    Assistant,
    System,
}

enum class ChatExperiencePhase {
    Idle,
    UserSending,
    AssistantThinking,
    RecommendationLoading,
    RecommendationReady,
    Error,
}

enum class VoiceRecognitionState {
    Idle,
    Recording,
    Uploading,
    Transcribing,
    Succeeded,
    Empty,
    Failed,
    Timeout,
}

data class ChatUiState(
    val sessionId: String = com.example.shopguideagent.config.UserSession.DEFAULT_SESSION_ID,
    val isConnected: Boolean = false,
    val isSending: Boolean = false,
    val phase: ChatExperiencePhase = ChatExperiencePhase.Idle,
    val messages: List<ChatMessageUiModel> = emptyList(),
    val cartBadgeCount: Int = 0,
    val cartSyncVersion: Long = 0L,
    val isSpeakerEnabled: Boolean = true,
    val voiceRecognitionState: VoiceRecognitionState = VoiceRecognitionState.Idle,
    val voiceRecognitionMessage: String? = null,
    val focus: ProductFocusUiState = ProductFocusUiState(),
    val errorMessage: String? = null,
    val retryMessageText: String? = null,
    val streamStartedAtMillis: Long? = null,
    val expandedProductId: String? = null,  // F5: 当前展开的 ProductDetailSheet 商品 ID，null = 收起
)

data class ProductFollowUpPayload(
    val focusProductId: String,
    val message: String,
) {
    val type: String = TYPE

    fun toJson(sessionId: String = com.example.shopguideagent.config.UserSession.DEFAULT_SESSION_ID, ttsEnabled: Boolean = true): JSONObject =
        JSONObject()
            .put("type", type)
            .put("session_id", sessionId)
            .put("focus_product_id", focusProductId)
            .put("message", message)
            .put("tts_enabled", ttsEnabled)

    companion object {
        const val TYPE = "product_followup"
    }
}

data class QuickActionUiModel @JvmOverloads constructor(
    val label: String,
    val message: String = label,
)

data class ChatMessageUiModel @JvmOverloads constructor(
    val id: String,
    val role: MessageRole,
    val text: String = "",
    val isStreaming: Boolean = false,
    val createdAtMillis: Long = System.currentTimeMillis(),
    val products: List<ProductUiModel> = emptyList(),
    val bundle: BundleUiModel? = null,
    val quickActions: List<QuickActionUiModel> = emptyList(),
)

data class ProductFocusUiState(
    val selectedProduct: ProductUiModel? = null,
    val responseText: String = "",
    val replacementProducts: List<ProductUiModel> = emptyList(),
    val isStreaming: Boolean = false,
)
