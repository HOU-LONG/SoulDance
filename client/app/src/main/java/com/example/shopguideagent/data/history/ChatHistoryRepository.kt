package com.example.shopguideagent.data.history

import android.content.Context
import android.content.SharedPreferences
import androidx.annotation.Keep
import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.MessageRole
import com.example.shopguideagent.data.model.ProductUiModel
import com.google.gson.Gson
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.Base64

interface ChatHistoryStore {
    fun read(userId: String): String
    fun write(userId: String, value: String)
}

class ChatHistoryRepository @JvmOverloads constructor(
    private val store: ChatHistoryStore,
    private val userIdProvider: () -> String,
    private val gson: Gson = Gson(),
) {
    private val _state = MutableStateFlow(load())
    val state: StateFlow<ChatHistoryUiState> = _state.asStateFlow()

    private fun currentUserId(): String = userIdProvider()

    private fun load(): ChatHistoryUiState {
        val userId = currentUserId()
        val raw = store.read(userId)
        return if (raw.isBlank()) {
            ChatHistoryUiState()
        } else if (raw.startsWith("current=")) {
            // legacy base64 format: migrate once, then rewrite as JSON
            val migrated = LegacyChatHistoryDecoder.decodeState(raw)
            persist(migrated)
            migrated
        } else {
            runCatching { gson.fromJson(raw, ChatHistoryUiState::class.java) }
                .getOrDefault(ChatHistoryUiState())
        }
    }

    private fun persist(state: ChatHistoryUiState) {
        store.write(currentUserId(), gson.toJson(state))
    }

    fun saveSession(
        sessionId: String,
        title: String,
        messages: List<ChatMessageUiModel>,
        updatedAtMillis: Long = System.currentTimeMillis(),
    ) {
        val session = ChatSessionUiModel(sessionId, title.ifBlank { "新会话" }, updatedAtMillis, messages)
        val nextSessions = (listOf(session) + _state.value.sessions.filterNot { it.sessionId == sessionId })
            .sortedByDescending { it.updatedAtMillis }
            .take(MAX_SESSIONS)
        val newState = ChatHistoryUiState(sessions = nextSessions, currentSessionId = sessionId)
        _state.value = newState
        persist(newState)
    }

    fun selectSession(sessionId: String) {
        if (_state.value.sessions.any { it.sessionId == sessionId }) {
            val newState = _state.value.copy(currentSessionId = sessionId)
            _state.value = newState
            persist(newState)
        }
    }

    fun deleteSession(sessionId: String) {
        val remaining = _state.value.sessions.filterNot { it.sessionId == sessionId }
        val nextCurrentId = when {
            _state.value.currentSessionId != sessionId &&
                remaining.any { it.sessionId == _state.value.currentSessionId } -> _state.value.currentSessionId
            else -> remaining.firstOrNull()?.sessionId
        }
        val newState = ChatHistoryUiState(sessions = remaining, currentSessionId = nextCurrentId)
        _state.value = newState
        persist(newState)
    }

    fun currentSession(): ChatSessionUiModel? =
        _state.value.sessions.firstOrNull { it.sessionId == _state.value.currentSessionId }

    companion object {
        private const val MAX_SESSIONS = 30
    }
}

object LegacyChatHistoryDecoder {
    fun decodeState(raw: String): ChatHistoryUiState {
        if (raw.isBlank()) return ChatHistoryUiState()
        val sessionHeaders = linkedMapOf<String, Triple<String, Long, MutableList<ChatMessageUiModel>>>()
        var currentId: String? = null
        raw.lineSequence().forEach { line ->
            when {
                line.startsWith("current=") -> currentId = decode(line.removePrefix("current=")).ifBlank { null }
                line.startsWith("session|") -> {
                    val parts = line.split('|')
                    if (parts.size >= 4) {
                        sessionHeaders[decode(parts[1])] = Triple(
                            decode(parts[2]),
                            parts[3].toLongOrNull() ?: 0L,
                            mutableListOf(),
                        )
                    }
                }
                line.startsWith("message|") -> {
                    val parts = line.split('|')
                    if (parts.size >= 7) {
                        val sessionId = decode(parts[1])
                        val bucket = sessionHeaders[sessionId]?.third ?: return@forEach
                        bucket += ChatMessageUiModel(
                            id = decode(parts[2]),
                            role = runCatching { MessageRole.valueOf(parts[3]) }.getOrDefault(MessageRole.Assistant),
                            createdAtMillis = parts[4].toLongOrNull() ?: 0L,
                            text = decode(parts[5]),
                            products = decodeProducts(parts[6]),
                        )
                    }
                }
            }
        }
        val sessions = sessionHeaders.map { (id, triple) ->
            ChatSessionUiModel(id, triple.first, triple.second, triple.third)
        }.sortedByDescending { it.updatedAtMillis }
        return ChatHistoryUiState(sessions = sessions, currentSessionId = currentId ?: sessions.firstOrNull()?.sessionId)
    }

    private fun decodeProducts(raw: String): List<ProductUiModel> {
        val decoded = decode(raw)
        if (decoded.isBlank()) return emptyList()
        return decoded.split(';').mapNotNull { item ->
            val parts = item.split('~').map { decode(it) }
            if (parts.size < 7) return@mapNotNull null
            ProductUiModel(
                productId = parts[0],
                name = parts[1],
                price = parts[2].toDoubleOrNull() ?: 0.0,
                imageUrl = parts[3].ifBlank { null },
                tags = parts[4].split(',').filter { it.isNotBlank() },
                reason = parts[5].ifBlank { null },
                isPrimary = parts[6].toBoolean(),
            )
        }
    }

    private fun decode(value: String): String =
        runCatching {
            String(Base64.getUrlDecoder().decode(value), Charsets.UTF_8)
        }.getOrDefault("")
}

class SharedPreferencesChatHistoryStore(
    private val preferences: SharedPreferences,
) : ChatHistoryStore {
    override fun read(userId: String): String = preferences.getString(keyFor(userId), "").orEmpty()

    override fun write(userId: String, value: String) {
        preferences.edit().putString(keyFor(userId), value).apply()
    }

    private fun keyFor(userId: String): String = "chat_history_${userId.replace(Regex("[^a-zA-Z0-9_-]"), "_")}"

    companion object {
        private const val LEGACY_KEY_HISTORY = "chat_history"
    }
}

class InMemoryChatHistoryStore @JvmOverloads constructor(
    private val legacyValue: String = "",
    private val values: MutableMap<String, String> = mutableMapOf(),
) : ChatHistoryStore {
    override fun read(userId: String): String = values[userId] ?: legacyValue
    override fun write(userId: String, value: String) {
        values[userId] = value
    }
}

fun chatHistoryRepository(
    context: Context,
    userIdProvider: () -> String = { UserSession.get(context).currentUserId.value },
): ChatHistoryRepository {
    val preferences = context.applicationContext.getSharedPreferences("shopguide_chat_history", Context.MODE_PRIVATE)
    return ChatHistoryRepository(SharedPreferencesChatHistoryStore(preferences), userIdProvider)
}
