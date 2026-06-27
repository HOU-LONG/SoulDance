package com.example.shopguideagent.data.history

import androidx.annotation.Keep
import com.example.shopguideagent.data.model.ChatMessageUiModel

@Keep
data class ChatSessionUiModel(
    val sessionId: String,
    val title: String,
    val updatedAtMillis: Long,
    val messages: List<ChatMessageUiModel>,
)

@Keep
data class ChatHistoryUiState(
    val sessions: List<ChatSessionUiModel> = emptyList(),
    val currentSessionId: String? = null,
)
