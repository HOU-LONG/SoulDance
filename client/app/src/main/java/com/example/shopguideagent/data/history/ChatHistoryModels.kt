package com.example.shopguideagent.data.history

import com.example.shopguideagent.data.model.ChatMessageUiModel

data class ChatSessionUiModel(
    val sessionId: String,
    val title: String,
    val updatedAtMillis: Long,
    val messages: List<ChatMessageUiModel>,
)

data class ChatHistoryUiState(
    val sessions: List<ChatSessionUiModel> = emptyList(),
    val currentSessionId: String? = null,
)
