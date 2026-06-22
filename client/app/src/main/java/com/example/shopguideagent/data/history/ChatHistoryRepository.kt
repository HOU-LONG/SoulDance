package com.example.shopguideagent.data.history

import android.content.Context
import android.content.SharedPreferences
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.MessageRole
import com.example.shopguideagent.data.model.ProductUiModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.Base64

interface ChatHistoryStore {
    fun read(): String
    fun write(value: String)
}

class ChatHistoryRepository(
    private val store: ChatHistoryStore,
) {
    private val _state = MutableStateFlow(decodeState(store.read()))
    val state: StateFlow<ChatHistoryUiState> = _state.asStateFlow()

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
        update(ChatHistoryUiState(sessions = nextSessions, currentSessionId = sessionId))
    }

    fun selectSession(sessionId: String) {
        if (_state.value.sessions.any { it.sessionId == sessionId }) {
            update(_state.value.copy(currentSessionId = sessionId))
        }
    }

    fun deleteSession(sessionId: String) {
        val remaining = _state.value.sessions.filterNot { it.sessionId == sessionId }
        val nextCurrentId = when {
            _state.value.currentSessionId != sessionId &&
                remaining.any { it.sessionId == _state.value.currentSessionId } -> _state.value.currentSessionId
            else -> remaining.firstOrNull()?.sessionId
        }
        update(ChatHistoryUiState(sessions = remaining, currentSessionId = nextCurrentId))
    }

    fun currentSession(): ChatSessionUiModel? =
        _state.value.sessions.firstOrNull { it.sessionId == _state.value.currentSessionId }

    private fun update(state: ChatHistoryUiState) {
        _state.value = state
        store.write(encodeState(state))
    }

    companion object {
        private const val MAX_SESSIONS = 30

        private fun encodeState(state: ChatHistoryUiState): String =
            buildString {
                append("current=")
                append(encode(state.currentSessionId.orEmpty()))
                append('\n')
                state.sessions.forEach { session ->
                    append("session|")
                    append(encode(session.sessionId))
                    append('|')
                    append(encode(session.title))
                    append('|')
                    append(session.updatedAtMillis)
                    append('\n')
                    session.messages.forEach { message ->
                        append("message|")
                        append(encode(session.sessionId))
                        append('|')
                        append(encode(message.id))
                        append('|')
                        append(message.role.name)
                        append('|')
                        append(message.createdAtMillis)
                        append('|')
                        append(encode(message.text))
                        append('|')
                        append(encodeProducts(message.products))
                        append('\n')
                    }
                }
            }

        private fun decodeState(raw: String): ChatHistoryUiState {
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

        private fun encodeProducts(products: List<ProductUiModel>): String =
            encode(products.joinToString(";") { product ->
                listOf(
                    product.productId,
                    product.name,
                    product.price.toString(),
                    product.imageUrl.orEmpty(),
                    product.tags.joinToString(","),
                    product.reason.orEmpty(),
                    product.isPrimary.toString(),
                ).joinToString("~") { encode(it) }
            })

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

        private fun encode(value: String): String =
            Base64.getUrlEncoder().withoutPadding().encodeToString(value.toByteArray(Charsets.UTF_8))

        private fun decode(value: String): String =
            runCatching {
                String(Base64.getUrlDecoder().decode(value), Charsets.UTF_8)
            }.getOrDefault("")
    }
}

class SharedPreferencesChatHistoryStore(
    private val preferences: SharedPreferences,
) : ChatHistoryStore {
    override fun read(): String = preferences.getString(KEY_HISTORY, "").orEmpty()

    override fun write(value: String) {
        preferences.edit().putString(KEY_HISTORY, value).apply()
    }

    companion object {
        private const val KEY_HISTORY = "chat_history"
    }
}

class InMemoryChatHistoryStore(
    private var value: String = "",
) : ChatHistoryStore {
    override fun read(): String = value

    override fun write(value: String) {
        this.value = value
    }
}

fun chatHistoryRepository(context: Context): ChatHistoryRepository {
    val preferences = context.applicationContext.getSharedPreferences("shopguide_chat_history", Context.MODE_PRIVATE)
    return ChatHistoryRepository(SharedPreferencesChatHistoryStore(preferences))
}
