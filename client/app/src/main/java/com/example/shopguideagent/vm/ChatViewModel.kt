package com.example.shopguideagent.vm

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.catalog.ProductCatalog
import com.example.shopguideagent.data.history.ChatHistoryRepository
import com.example.shopguideagent.data.model.ChatExperiencePhase
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.data.model.MessageRole
import com.example.shopguideagent.data.model.ProductDerivedAttributes
import com.example.shopguideagent.data.model.ProductFocusUiState
import com.example.shopguideagent.data.model.ProductFollowUpPayload
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.RealtimeEvent
import com.example.shopguideagent.data.model.VoiceRecognitionState
import com.example.shopguideagent.audio.StreamingAudioPlayer
import com.example.shopguideagent.data.remote.RealtimeChatWebSocketClient
import com.example.shopguideagent.data.remote.SessionsApi
import com.example.shopguideagent.data.remote.SessionsApiClient
import com.example.shopguideagent.data.remote.SessionsApiService
import com.example.shopguideagent.data.remote.SpeechToTextClient
import com.example.shopguideagent.data.remote.SttApiService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import java.io.File
import java.net.SocketTimeoutException
import java.util.UUID

class ChatViewModel @JvmOverloads constructor(
    private val productCatalog: ProductCatalog? = null,
    private val historyRepository: ChatHistoryRepository? = null,
    private val wsClient: RealtimeChatWebSocketClient = RealtimeChatWebSocketClient(),
    private val sttApi: SpeechToTextClient = SttApiService(),
    private val audioPlayer: StreamingAudioPlayer = StreamingAudioPlayer(),
    private val voiceRecognitionTimeoutMillis: Long = VOICE_RECOGNITION_TIMEOUT_MILLIS,
    private val userSession: UserSession? = null,
    private val sessionsApi: SessionsApi = SessionsApiClient(
        SessionsApiService.create(userIdProvider = { userSession?.currentUserId?.value ?: "demo_user_a" })
    ),
    private val userIdProvider: () -> String = { userSession?.currentUserId?.value ?: "demo_user_a" },
) : ViewModel() {

    @JvmOverloads
    constructor(
        context: Context,
        productCatalog: ProductCatalog? = null,
        historyRepository: ChatHistoryRepository? = null,
        wsClient: RealtimeChatWebSocketClient = RealtimeChatWebSocketClient(),
        sttApi: SpeechToTextClient = SttApiService(),
        audioPlayer: StreamingAudioPlayer = StreamingAudioPlayer(),
    ) : this(
        productCatalog = productCatalog,
        historyRepository = historyRepository,
        wsClient = wsClient,
        sttApi = sttApi,
        audioPlayer = audioPlayer,
        userSession = UserSession.get(context),
        userIdProvider = { UserSession.get(context).currentUserId.value },
    )

    private val welcome = ChatMessageUiModel(
        id = "welcome",
        role = MessageRole.Assistant,
        text = "你好，我是你的智能导购助手。告诉我你想买什么、预算和不想要的点，我会帮你找到合适的商品。",
    )

    private val initialSession = historyRepository?.currentSession()
    private var activeSessionId: String = initialSession?.sessionId ?: "session_${UUID.randomUUID()}"

    private val _uiState = kotlinx.coroutines.flow.MutableStateFlow(
        ChatUiState(
            sessionId = activeSessionId,
            messages = initialSession?.messages ?: listOf(welcome),
        ),
    )
    val uiState: StateFlow<ChatUiState> = _uiState

    private val _realtimeEvents = MutableSharedFlow<RealtimeEvent>(extraBufferCapacity = 64)
    val realtimeEvents: SharedFlow<RealtimeEvent> = _realtimeEvents.asSharedFlow()
    val historyState: StateFlow<com.example.shopguideagent.data.history.ChatHistoryUiState> =
        historyRepository?.state
            ?: kotlinx.coroutines.flow.MutableStateFlow(
                com.example.shopguideagent.data.history.ChatHistoryUiState(),
            )
    private var lastProductFollowUpPayload: ProductFollowUpPayload? = null
    private var activeStreamUserText: String? = null
    private var activeAssistantId: String? = null
    private var activeFollowUpAssistantId: String? = null
    private var activeFollowUpText: String? = null
    private var wsJob: Job? = null

    override fun onCleared() {
        super.onCleared()
        wsClient.close()
        wsJob?.cancel()
        audioPlayer.release()
    }

    fun newSession() {
        activeSessionId = "session_${UUID.randomUUID()}"
        _uiState.value = ChatUiState(
            sessionId = activeSessionId,
            cartBadgeCount = _uiState.value.cartBadgeCount,
            isSpeakerEnabled = true,
            voiceRecognitionState = VoiceRecognitionState.Idle,
            messages = listOf(welcome),
        )
        activeStreamUserText = null
        lastProductFollowUpPayload = null
        activeAssistantId = null
        activeFollowUpAssistantId = null
        activeFollowUpText = null
        audioPlayer.stop()
        persist()
    }

    fun selectSession(session: com.example.shopguideagent.data.history.ChatSessionUiModel) {
        activeSessionId = session.sessionId
        historyRepository?.selectSession(session.sessionId)
        lastProductFollowUpPayload = null
        activeStreamUserText = null
        activeAssistantId = null
        activeFollowUpAssistantId = null
        activeFollowUpText = null
        _uiState.value = _uiState.value.copy(
            sessionId = activeSessionId,
            messages = session.messages,
            isSending = false,
            phase = ChatExperiencePhase.Idle,
            isSpeakerEnabled = true,
            voiceRecognitionState = VoiceRecognitionState.Idle,
            focus = ProductFocusUiState(),
            errorMessage = null,
            retryMessageText = null,
            streamStartedAtMillis = null,
        )
    }

    fun deleteSession(session: com.example.shopguideagent.data.history.ChatSessionUiModel) {
        val repository = historyRepository ?: return
        val deletingActiveSession = session.sessionId == activeSessionId
        repository.deleteSession(session.sessionId)
        if (!deletingActiveSession) return

        val nextSession = repository.currentSession()
        if (nextSession != null) {
            selectSession(nextSession)
            return
        }

        activeSessionId = "session_${UUID.randomUUID()}"
        lastProductFollowUpPayload = null
        activeStreamUserText = null
        activeAssistantId = null
        activeFollowUpAssistantId = null
        activeFollowUpText = null
        audioPlayer.stop()
        _uiState.value = _uiState.value.copy(
            sessionId = activeSessionId,
            messages = listOf(welcome),
            isSending = false,
            phase = ChatExperiencePhase.Idle,
            isSpeakerEnabled = true,
            voiceRecognitionState = VoiceRecognitionState.Idle,
            focus = ProductFocusUiState(),
            errorMessage = null,
            retryMessageText = null,
            streamStartedAtMillis = null,
        )
    }

    fun sendMessage(rawText: String) {
        // 统一走流式通道，后端会以流式方式返回，UI 可以实时渲染
        sendMessageStreaming(rawText)
    }

    fun sendProductFollowUp(product: ProductUiModel, rawText: String) {
        val text = rawText.trim()
        if (text.isEmpty()) return
        audioPlayer.stop()

        lastProductFollowUpPayload = ProductFollowUpPayload(
            focusProductId = product.productId,
            message = text,
        )

        val userMessage = ChatMessageUiModel(
            id = "user_${UUID.randomUUID()}",
            role = MessageRole.User,
            text = "围绕「${product.name}」追问：$text",
        )
        val assistantId = "assistant_${UUID.randomUUID()}"
        activeFollowUpAssistantId = assistantId
        activeFollowUpText = text

        _uiState.update { current ->
            current.copy(
                isSending = true,
                phase = ChatExperiencePhase.AssistantThinking,
                focus = current.focus.copy(
                    selectedProduct = product,
                    responseText = "",
                    replacementProducts = emptyList(),
                    isStreaming = true,
                ),
                messages = current.messages + userMessage + ChatMessageUiModel(
                    id = assistantId,
                    role = MessageRole.Assistant,
                    isStreaming = true,
                ),
                errorMessage = null,
                retryMessageText = null,
                streamStartedAtMillis = System.currentTimeMillis(),
            )
        }
        persist()

        ensureWebSocketConnection()
        wsClient.sendProductFollowup(
            activeSessionId,
            product.productId,
            text,
            ttsEnabled = _uiState.value.isSpeakerEnabled,
        )

        viewModelScope.launch(Dispatchers.Default) {
            delay(STREAM_TIMEOUT_MILLIS)
            if (activeFollowUpAssistantId == assistantId && isMessageStreaming(assistantId)) {
                handleStreamInterrupted(assistantId, STREAM_INTERRUPTED_MESSAGE)
            }
        }
    }

    fun sendMessageStreaming(rawText: String) {
        if (_uiState.value.isSending) return
        audioPlayer.stop()

        val text = rawText.trim()
        if (text.isEmpty()) return

        val userMessage = ChatMessageUiModel(
            id = "user_${UUID.randomUUID()}",
            role = MessageRole.User,
            text = text,
        )
        val assistantId = "assistant_${UUID.randomUUID()}"
        activeAssistantId = assistantId
        val startedAt = System.currentTimeMillis()
        activeStreamUserText = text
        _uiState.value = _uiState.value.copy(
            isSending = true,
            phase = ChatExperiencePhase.AssistantThinking,
            messages = _uiState.value.messages + userMessage + ChatMessageUiModel(
                id = assistantId,
                role = MessageRole.Assistant,
                isStreaming = true,
                expectedProductCount = 0,
            ),
            errorMessage = null,
            retryMessageText = null,
            streamStartedAtMillis = startedAt,
        )
        persist()

        ensureWebSocketConnection()
        wsClient.sendUserMessage(activeSessionId, text, ttsEnabled = _uiState.value.isSpeakerEnabled)

        viewModelScope.launch(Dispatchers.Default) {
            delay(STREAM_TIMEOUT_MILLIS)
            if (shouldInterruptTimedOutStream(assistantId, activeAssistantId, isMessageStreaming(assistantId))) {
                handleStreamInterrupted(assistantId, STREAM_INTERRUPTED_MESSAGE)
            }
        }
    }

    fun sendVoiceMessage(audioFile: File) {
        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isSending = true,
                    phase = ChatExperiencePhase.UserSending,
                    voiceRecognitionState = VoiceRecognitionState.Transcribing,
                    voiceRecognitionMessage = "正在识别语音",
                    errorMessage = null,
                )
            }
            val result = try {
                withTimeout(voiceRecognitionTimeoutMillis) {
                    sttApi.transcribe(audioFile)
                }
            } catch (e: Exception) {
                Result.failure(e)
            }
            audioFile.delete()
            result.fold(
                onSuccess = { text ->
                    if (text.isNotBlank()) {
                        _uiState.update {
                            it.copy(
                                isSending = false,
                                voiceRecognitionState = VoiceRecognitionState.Succeeded,
                                voiceRecognitionMessage = text.trim(),
                            )
                        }
                        sendMessageStreaming(text.trim())
                    } else {
                        _uiState.update {
                            it.copy(
                                isSending = false,
                                phase = ChatExperiencePhase.Idle,
                                voiceRecognitionState = VoiceRecognitionState.Empty,
                                voiceRecognitionMessage = "没听清，请再说一次",
                            )
                        }
                    }
                },
                onFailure = { e ->
                    val timedOut = isVoiceRecognitionTimeout(e)
                    val displayMessage = voiceRecognitionFailureMessage(e)
                    _uiState.update {
                        it.copy(
                            isSending = false,
                            phase = ChatExperiencePhase.Idle,
                            voiceRecognitionState = if (timedOut) {
                                VoiceRecognitionState.Timeout
                            } else {
                                VoiceRecognitionState.Failed
                            },
                            voiceRecognitionMessage = displayMessage,
                            errorMessage = "语音识别失败: $displayMessage",
                        )
                    }
                },
            )
        }
    }

    private fun voiceRecognitionFailureMessage(error: Throwable): String {
        val rawMessage = error.message.orEmpty()
        return when {
            isVoiceRecognitionTimeout(error) -> "语音识别超时，请再试一次"
            isVoiceRecognitionConnectionClosed(error) -> "语音识别连接中断，请再试一次"
            rawMessage.isNotBlank() -> rawMessage
            else -> "语音识别失败，请再试一次"
        }
    }

    private fun isVoiceRecognitionTimeout(error: Throwable): Boolean {
        val message = error.message.orEmpty()
        val normalized = message.lowercase()
        return error is TimeoutCancellationException ||
            error is SocketTimeoutException ||
            normalized.contains("timeout") ||
            normalized.contains("timed out") ||
            message.contains("超时")
    }

    private fun isVoiceRecognitionConnectionClosed(error: Throwable): Boolean {
        val normalized = error.message.orEmpty().lowercase()
        return normalized.contains("connection closed") ||
            normalized.contains("unexpected end of stream") ||
            normalized.contains("stream was reset") ||
            normalized.contains("connection reset") ||
            normalized.contains("socket closed") ||
            normalized == "closed" ||
            normalized.contains("reset") ||
            error.message.orEmpty().contains("连接中断")
    }

    fun updateCartBadge(count: Int) {
        _uiState.value = _uiState.value.copy(cartBadgeCount = count)
    }

    fun setSpeakerEnabled(enabled: Boolean) {
        _uiState.update { current ->
            current.copy(isSpeakerEnabled = enabled)
        }
        if (!enabled) {
            audioPlayer.stop()
        }
    }

    fun consumeError() {
        _uiState.value = _uiState.value.copy(errorMessage = null)
    }

    fun getLastProductFollowUpPayload(): ProductFollowUpPayload? = lastProductFollowUpPayload

    fun getLastProductFollowUpPayloadJson(): JSONObject? = lastProductFollowUpPayload?.toJson()

    private fun ensureWebSocketConnection() {
        if (wsJob?.isActive == true) return
        wsJob = viewModelScope.launch {
            wsClient.connect().collect { event ->
                handleRealtimeEvent(event)
            }
        }
    }

    private fun handleRealtimeEvent(event: RealtimeEvent) {
        _realtimeEvents.tryEmit(event)
        when (event) {
            is RealtimeEvent.TextDelta -> {
                val followUpAssistantId = activeFollowUpAssistantId
                if (followUpAssistantId != null) {
                    appendAssistantText(followUpAssistantId, event.text)
                    _uiState.update { current ->
                        current.copy(
                            focus = current.focus.copy(
                                responseText = current.focus.responseText + event.text,
                                isStreaming = true,
                            ),
                        )
                    }
                } else {
                    activeAssistantId?.let { appendAssistantText(it, event.text) }
                }
            }
            is RealtimeEvent.ProductsStart -> {
                activeAssistantId?.let { updateExpectedCount(it, event.expectedCount) }
                _uiState.update { current ->
                    current.copy(phase = ChatExperiencePhase.RecommendationLoading)
                }
            }
            is RealtimeEvent.ProductItem -> {
                activeAssistantId?.let { id ->
                    val enriched = enrichProduct(event.product)
                    appendAssistantProduct(id, enriched)
                }
            }
            is RealtimeEvent.ProductsDone -> {
                _uiState.update { current ->
                    current.copy(phase = ChatExperiencePhase.RecommendationReady)
                }
            }
            is RealtimeEvent.BundleStart -> {
                activeAssistantId?.let { updateExpectedCount(it, 4) } // 组合包默认预期数量
                _uiState.update { current ->
                    current.copy(phase = ChatExperiencePhase.RecommendationLoading)
                }
            }
            is RealtimeEvent.BundleItem -> {
                activeAssistantId?.let { id ->
                    val enriched = enrichProduct(event.product)
                    appendAssistantProduct(id, enriched)
                }
            }
            is RealtimeEvent.BundleDone -> {
                _uiState.update { current ->
                    current.copy(phase = ChatExperiencePhase.RecommendationReady)
                }
            }
            is RealtimeEvent.FocusTextDelta -> {
                activeFollowUpAssistantId?.let { appendAssistantText(it, event.text) }
                _uiState.update { current ->
                    current.copy(
                        focus = current.focus.copy(
                            responseText = current.focus.responseText + event.text,
                            isStreaming = true,
                        ),
                    )
                }
            }
            is RealtimeEvent.ReplacementProduct -> {
                val enriched = enrichProduct(event.product)
                activeFollowUpAssistantId?.let { appendAssistantProduct(it, enriched) }
                _uiState.update { current ->
                    current.copy(
                        focus = current.focus.copy(
                            replacementProducts = current.focus.replacementProducts + enriched,
                            isStreaming = true,
                        ),
                    )
                }
            }
            is RealtimeEvent.FocusDone -> {
                activeFollowUpAssistantId?.let { finishFollowUpStream(it) }
                activeFollowUpAssistantId = null
                activeFollowUpText = null
                _uiState.update { current ->
                    current.copy(
                        isSending = activeAssistantId != null,
                        focus = current.focus.copy(isStreaming = false),
                    )
                }
            }
            is RealtimeEvent.AudioDelta -> {
                if (_uiState.value.isSpeakerEnabled) {
                    val pcm = android.util.Base64.decode(event.audioBase64, android.util.Base64.DEFAULT)
                    audioPlayer.enqueuePcm(pcm, event.sampleRate)
                }
            }
            is RealtimeEvent.AudioDone -> {
                if (_uiState.value.isSpeakerEnabled) {
                    audioPlayer.markEndOfStream()
                }
            }
            is RealtimeEvent.CartUpdate -> {
                if (!event.message.isNullOrBlank()) {
                    (activeFollowUpAssistantId ?: activeAssistantId)?.let {
                        appendAssistantText(it, event.message)
                    }
                }
                if (!event.success) {
                    return
                }
                _uiState.update { current ->
                    current.copy(
                        cartBadgeCount = event.badgeCount,
                        cartSyncVersion = current.cartSyncVersion + 1L,
                    )
                }
            }
            is RealtimeEvent.QuickActions -> {
                val targetMessageId = activeFollowUpAssistantId ?: activeAssistantId ?: event.messageId
                updateQuickActions(targetMessageId, event.actions)
            }
            is RealtimeEvent.Done -> {
                activeAssistantId?.let { finishStream(it) }
                activeAssistantId = null
            }
            is RealtimeEvent.Ack -> Unit
            is RealtimeEvent.Error -> {
                (activeFollowUpAssistantId ?: activeAssistantId)?.let {
                    handleStreamInterrupted(it, event.message)
                }
            }
            is RealtimeEvent.Unknown -> {
                // 可记录日志，暂不处理
            }
        }
    }

    private fun enrichProduct(product: ProductUiModel): ProductUiModel {
        val local = productCatalog?.findById(product.productId)
        return if (local != null) {
            product.copy(
                imageUrl = product.imageUrl ?: local.imageUrl,
                tags = product.tags.ifEmpty { local.tags },
                reason = product.reason ?: local.reason,
                rating = product.rating ?: local.rating,
                stock = product.stock ?: local.stock,
                derivedAttributes = if (product.derivedAttributes == ProductDerivedAttributes()) {
                    local.derivedAttributes
                } else product.derivedAttributes,
                positiveFeedbackSummary = product.positiveFeedbackSummary.ifEmpty { local.positiveFeedbackSummary },
                negativeFeedbackSummary = product.negativeFeedbackSummary.ifEmpty { local.negativeFeedbackSummary },
                riskTags = product.riskTags.ifEmpty { local.riskTags },
            )
        } else product
    }

    private fun appendAssistantText(messageId: String, delta: String) {
        _uiState.update { current ->
            current.copy(
                messages = current.messages.map {
                    if (it.id == messageId && it.isStreaming) it.copy(text = it.text + delta) else it
                },
            )
        }
    }

    private fun updateExpectedCount(messageId: String, count: Int) {
        _uiState.update { current ->
            current.copy(
                messages = current.messages.map {
                    if (it.id == messageId && it.isStreaming) it.copy(expectedProductCount = count) else it
                },
            )
        }
    }

    private fun appendAssistantProduct(messageId: String, product: ProductUiModel) {
        _uiState.update { current ->
            current.copy(
                messages = current.messages.map { msg ->
                    if (msg.id == messageId && msg.isStreaming) {
                        msg.copy(products = msg.products + product)
                    } else msg
                },
            )
        }
    }

    private fun updateQuickActions(
        messageId: String,
        actions: List<com.example.shopguideagent.data.model.QuickActionUiModel>,
    ) {
        _uiState.update { current ->
            current.copy(
                messages = current.messages.map { msg ->
                    if (msg.id == messageId && actions.isNotEmpty()) {
                        msg.copy(quickActions = actions)
                    } else {
                        msg
                    }
                },
            )
        }
    }

    private fun finishStream(messageId: String) {
        _uiState.update { current ->
            current.copy(
                isSending = false,
                phase = ChatExperiencePhase.RecommendationReady,
                retryMessageText = null,
                streamStartedAtMillis = null,
                messages = current.messages.map {
                    if (it.id == messageId && it.isStreaming) it.copy(isStreaming = false) else it
                },
            )
        }
        activeStreamUserText = null
        persist()
    }

    private fun finishFollowUpStream(messageId: String) {
        _uiState.update { current ->
            current.copy(
                phase = ChatExperiencePhase.RecommendationReady,
                retryMessageText = null,
                streamStartedAtMillis = null,
                messages = current.messages.map {
                    if (it.id == messageId && it.isStreaming) it.copy(isStreaming = false) else it
                },
            )
        }
        persist()
    }

    private fun replaceMessage(message: ChatMessageUiModel) {
        _uiState.value = _uiState.value.copy(
            messages = _uiState.value.messages.map {
                if (it.id == message.id) message else it
            },
        )
    }

    fun handleStreamInterrupted(messageId: String, reason: String) {
        val retryText = when (messageId) {
            activeFollowUpAssistantId -> activeFollowUpText
            activeAssistantId -> activeStreamUserText
            else -> activeStreamUserText ?: activeFollowUpText
        }
        _uiState.update { current ->
            current.copy(
                isSending = false,
                phase = ChatExperiencePhase.Error,
                errorMessage = reason,
                retryMessageText = retryText,
                streamStartedAtMillis = null,
                messages = current.messages.map { message ->
                    if (message.id == messageId && message.isStreaming) {
                        message.copy(
                            text = interruptedStreamMessage(message.text, reason),
                            isStreaming = false,
                            expectedProductCount = message.products.size,
                        )
                    } else {
                        message
                    }
                },
            )
        }
        if (activeAssistantId == messageId) {
            activeAssistantId = null
            activeStreamUserText = null
        }
        if (activeFollowUpAssistantId == messageId) {
            activeFollowUpAssistantId = null
            activeFollowUpText = null
        }
        persist()
    }

    private fun isMessageStreaming(messageId: String): Boolean =
        _uiState.value.messages.any { it.id == messageId && it.isStreaming }

    private fun persist() {
        val messages = _uiState.value.messages
        historyRepository?.saveSession(
            sessionId = activeSessionId,
            title = titleFor(messages),
            messages = messages,
        )
    }

    private fun titleFor(messages: List<ChatMessageUiModel>): String =
        messages.firstOrNull { it.role == MessageRole.User }?.text?.take(18) ?: "新会话"

    fun onUserSwitched(newUserId: String) {
        viewModelScope.launch {
            val currentUserId = userIdProvider()
            if (newUserId == currentUserId) return@launch

            userSession?.setCurrentUserId(newUserId)

            // Get latest session for new user
            val latest = sessionsApi.getLatest()

            // Close current WebSocket
            wsJob?.cancel()
            wsClient.close()
            wsJob = null

            // Reset session and UI for new user
            activeSessionId = latest.session_id
            _uiState.value = ChatUiState(
                sessionId = activeSessionId,
                cartBadgeCount = _uiState.value.cartBadgeCount,
                isSpeakerEnabled = true,
                voiceRecognitionState = VoiceRecognitionState.Idle,
                messages = listOf(welcome),
            )

            // Clear active state
            activeStreamUserText = null
            lastProductFollowUpPayload = null
            activeAssistantId = null
            activeFollowUpAssistantId = null
            activeFollowUpText = null
            audioPlayer.stop()

            // Reopen WebSocket against the new session id. Subsequent sendUserMessage
            // calls will use activeSessionId (which is now the new session id).
            ensureWebSocketConnection()
        }
    }
}

fun visibleProductCountForStreaming(
    completedChunks: Int,
    totalChunks: Int,
    productCount: Int,
): Int {
    if (productCount <= 0) return 0
    if (totalChunks <= 0) return productCount
    val revealInterval = (totalChunks / (productCount + 1)).coerceAtLeast(1)
    return (completedChunks / revealInterval).coerceIn(0, productCount)
}

fun shouldExitRecommendationSkeleton(
    isStreaming: Boolean,
    elapsedMillis: Long,
    timeoutMillis: Long,
): Boolean = isStreaming && elapsedMillis >= timeoutMillis

fun shouldInterruptTimedOutStream(
    timeoutAssistantId: String,
    activeAssistantId: String?,
    isStreaming: Boolean,
): Boolean = activeAssistantId == timeoutAssistantId && isStreaming

fun interruptedStreamMessage(partialText: String, reason: String): String =
    if (partialText.isBlank()) reason else "$partialText\n\n$reason"

private const val STREAM_TIMEOUT_MILLIS = 30_000L
private const val STREAM_INTERRUPTED_MESSAGE = "连接中断，请重试。"
private const val VOICE_RECOGNITION_TIMEOUT_MILLIS = 30_000L
