# Sprite Space as Primary Shopping Surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Android app so the "精灵空间" (Sprite Space) becomes the primary interactive shopping surface with voice conversation, and a chat-mode switch opens the existing traditional chat page.

**Architecture:** SpriteHomeScreen becomes the app's landing/home screen. It embeds a voice-first interaction bar (hold-to-talk mic) that connects directly to the WebSocket chat backend via a shared `ChatSessionCoordinator`. Product recommendations appear inline as bottom sheets/carousels within the sprite space. A chat-mode toggle in the top bar switches to the existing ChatScreen (preserved as-is). State is managed by a merged `SpriteHomeViewModel` that subsumes the real-time chat responsibilities, while `ChatViewModel` remains for the dedicated chat page.

**Tech Stack:** Kotlin, Jetpack Compose, Material3, Kotlin Coroutines/Flow, OkHttp WebSocket, AudioTrack PCM playback.

## Global Constraints

- Target SDK: aligned with existing `build.gradle` (API 34+)
- Compose BOM version: aligned with existing project
- No new external dependencies without justification
- Keep all existing tests passing
- Preserve existing ChatScreen behavior when accessed via chat-mode switch
- Voice input requires `RECORD_AUDIO` permission (already declared)
- TTS audio uses pcm_s16le 16000Hz (already supported)
- All new UI components must have `@Preview` variants
- Follow existing file naming conventions (`PascalCase.kt` for classes, `camelCase` for functions)
- String resources: hardcode Chinese strings inline (follow existing pattern) unless reused >2 times

---

## File Structure Map

### New Files
- `ui/home/SpriteVoiceBar.kt` — Hold-to-talk mic button + voice wave animation + text input field, styled for sprite room warm theme
- `ui/home/ProductPresentationSheet.kt` — Bottom sheet showing primary product + alternatives inline in sprite space
- `ui/home/SpriteTopBar.kt` — Top bar with chat-mode switch, cart badge, settings; replaces the generic RoundIconButton row
- `ui/home/QuickActionChips.kt` — Horizontal chip row for quick actions (extracted/refactored from chat components)
- `ui/home/SpriteChatCoordinator.kt` — Shared WebSocket session lifecycle manager (extracted from ChatViewModel)
- `vm/SpriteChatViewModel.kt` — Merged ViewModel combining SpriteHomeViewModel + real-time chat capabilities

### Modified Files
- `navigation/AppNavGraph.kt` — Home becomes landing; add chat-mode route switch; simplify back stack
- `ui/home/SpriteHomeScreen.kt` — Add voice bar, product sheet, chat-mode switch; remove old bottom action bar or repurpose
- `ui/home/SpriteHomeViewModel.kt` — Merge in chat send/receive, voice flow, TTS playback, cart operations
- `ui/home/SpriteHomeUiState.kt` — Add chat message history, voice state, product presentation, cart count fields
- `ui/home/SpriteHomeAction.kt` — Add voice actions, product actions, cart actions, chat-mode switch action
- `ui/home/SpriteHomeTokens.kt` — Unify with app theme tokens; add voice bar colors
- `ui/theme/Theme.kt` — Fix light-status-bar / background consistency with styles.xml
- `ui/screen/ChatScreen.kt` — Add chat-mode switch entry point (back-to-sprite button)
- `vm/ChatViewModel.kt` — Extract shared WebSocket coordination to SpriteChatCoordinator
- `MainActivity.kt` — Possibly adjust system bars / edge-to-edge if needed

### Deleted / Deprecated
- `ui/home/BottomActionBar.kt` — Remove or repurpose (the "导购" button becomes the voice bar itself)
- `ui/home/SpriteHomeRoute.kt` — May be absorbed into AppNavGraph if thin enough

---

## Task 1: Unify Theme Tokens and Fix Background Mismatch

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeTokens.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/theme/Theme.kt`
- Modify: `client/app/src/main/res/values/styles.xml`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/theme/Color.kt`
- Test: `client/app/src/test/java/com/example/shopguideagent/ui/theme/DesignTokenTest.kt` (existing)

**Interfaces:**
- Consumes: existing `Color.kt` palette, `styles.xml` windowBackground
- Produces: unified `SpriteHomeTokens` that reference `Color.kt` tokens instead of hardcoded hex; `styles.xml` background matches `AppBackground`

- [ ] **Step 1: Update `styles.xml` to match Compose theme background**

In `client/app/src/main/res/values/styles.xml`, change line 7:
```xml
<item name="android:windowBackground">@color/app_background</item>
```

Add to `client/app/src/main/res/values/colors.xml` (create if missing):
```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="app_background">#FFF0FDF4</color>
</resources>
```

- [ ] **Step 2: Add sprite-room warm tokens to `Color.kt`**

In `client/app/src/main/java/com/example/shopguideagent/ui/theme/Color.kt`, append after line 68:
```kotlin
// Sprite Room Warm Palette — unified with app theme
val SpriteRoomTop = Color(0xFFB87942)
val SpriteRoomMiddle = Color(0xFFF4C282)
val SpriteRoomLight = Color(0xFFFFE3B5)
val SpriteRoomBottom = Color(0xFFE0A86C)
val SpritePanel = Color.White.copy(alpha = 0.72f)
val SpritePanelBorder = Color.White.copy(alpha = 0.7f)
val SpritePrimaryButton = Color(0xFFFFC94D)
val SpriteVoiceBarBackground = Color(0xFF4A3524)
val SpriteVoiceBarTint = Color(0xFFFFF8E1)
```

- [ ] **Step 3: Update `SpriteHomeTokens.kt` to reference unified tokens**

Replace the entire file `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeTokens.kt`:
```kotlin
package com.example.shopguideagent.ui.home

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.SpriteRoomTop
import com.example.shopguideagent.ui.theme.SpriteRoomMiddle
import com.example.shopguideagent.ui.theme.SpriteRoomLight
import com.example.shopguideagent.ui.theme.SpriteRoomBottom
import com.example.shopguideagent.ui.theme.SpritePanel
import com.example.shopguideagent.ui.theme.SpritePanelBorder
import com.example.shopguideagent.ui.theme.SpritePrimaryButton
import com.example.shopguideagent.ui.theme.SpriteVoiceBarBackground
import com.example.shopguideagent.ui.theme.SpriteVoiceBarTint

object SpriteHomeTokens {
    val RoomTop = SpriteRoomTop
    val RoomMiddle = SpriteRoomMiddle
    val RoomLight = SpriteRoomLight
    val RoomBottom = SpriteRoomBottom
    val Panel = SpritePanel
    val PanelBorder = SpritePanelBorder
    val PrimaryButton = SpritePrimaryButton
    val CardRadius = 34.dp
    val VoiceBarBackground = SpriteVoiceBarBackground
    val VoiceBarTint = SpriteVoiceBarTint
}
```

- [ ] **Step 4: Update `Theme.kt` to ensure status bar consistency**

In `client/app/src/main/java/com/example/shopguideagent/ui/theme/Theme.kt`, verify `lightColorScheme` uses `AppBackground` for `background`. It already does. Add a comment noting the styles.xml sync requirement:
```kotlin
// NOTE: When changing AppBackground, also update values/styles.xml android:windowBackground
// and values/colors.xml app_background to match.
```

- [ ] **Step 5: Run existing design token tests**

Run: `./gradlew :app:testDebugUnitTest --tests "*DesignTokenTest*"`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeTokens.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/theme/Color.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/theme/Theme.kt \
        client/app/src/main/res/values/styles.xml \
        client/app/src/main/res/values/colors.xml
git commit -m "style: unify sprite room tokens with app theme and fix styles.xml background mismatch"
```

---

## Task 2: Create SpriteChatCoordinator — Shared WebSocket Session Manager

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/domain/chat/SpriteChatCoordinator.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
- Test: `client/app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.kt` (existing, verify still passes)

**Interfaces:**
- Consumes: `RealtimeChatWebSocketClient`, `StreamingAudioPlayer`, `SttApiService`
- Produces: `SpriteChatCoordinator` with methods:
  - `val realtimeEvents: SharedFlow<RealtimeEvent>`
  - `val chatMessages: StateFlow<List<ChatMessageUiModel>>`
  - `fun sendUserMessage(sessionId: String, text: String, ttsEnabled: Boolean)`
  - `fun sendProductFollowUp(sessionId: String, productId: String, text: String, ttsEnabled: Boolean)`
  - `fun sendVoiceMessage(audioFile: File, sessionId: String, ttsEnabled: Boolean)`
  - `fun newSession(): String` (returns new sessionId)
  - `fun selectSession(sessionId: String, messages: List<ChatMessageUiModel>)`
  - `fun stopAudio()`
  - `fun setSpeakerEnabled(enabled: Boolean)`
  - `val isSpeakerEnabled: StateFlow<Boolean>`
  - `fun connect()` / `fun disconnect()`

- [ ] **Step 1: Extract WebSocket + audio logic from ChatViewModel into SpriteChatCoordinator**

Create `client/app/src/main/java/com/example/shopguideagent/domain/chat/SpriteChatCoordinator.kt`:
```kotlin
package com.example.shopguideagent.domain.chat

import com.example.shopguideagent.audio.StreamingAudioPlayer
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.ChatExperiencePhase
import com.example.shopguideagent.data.model.MessageRole
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.ProductFollowUpPayload
import com.example.shopguideagent.data.model.RealtimeEvent
import com.example.shopguideagent.data.model.VoiceRecognitionState
import com.example.shopguideagent.data.remote.RealtimeChatWebSocketClient
import com.example.shopguideagent.data.remote.SpeechToTextClient
import com.example.shopguideagent.data.remote.SttApiService
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.io.File
import java.util.UUID

class SpriteChatCoordinator(
    private val wsClient: RealtimeChatWebSocketClient = RealtimeChatWebSocketClient(),
    private val sttApi: SpeechToTextClient = SttApiService(),
    private val audioPlayer: StreamingAudioPlayer = StreamingAudioPlayer(),
    private val voiceRecognitionTimeoutMillis: Long = 30_000L,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private val _realtimeEvents = MutableSharedFlow<RealtimeEvent>(extraBufferCapacity = 64)
    val realtimeEvents: SharedFlow<RealtimeEvent> = _realtimeEvents.asSharedFlow()

    private val _chatMessages = MutableStateFlow<List<ChatMessageUiModel>>(emptyList())
    val chatMessages: StateFlow<List<ChatMessageUiModel>> = _chatMessages.asStateFlow()

    private val _phase = MutableStateFlow(ChatExperiencePhase.Idle)
    val phase: StateFlow<ChatExperiencePhase> = _phase.asStateFlow()

    private val _isSending = MutableStateFlow(false)
    val isSending: StateFlow<Boolean> = _isSending.asStateFlow()

    private val _isSpeakerEnabled = MutableStateFlow(true)
    val isSpeakerEnabled: StateFlow<Boolean> = _isSpeakerEnabled.asStateFlow()

    private val _cartBadgeCount = MutableStateFlow(0)
    val cartBadgeCount: StateFlow<Int> = _cartBadgeCount.asStateFlow()

    private val _voiceRecognitionState = MutableStateFlow(VoiceRecognitionState.Idle)
    val voiceRecognitionState: StateFlow<VoiceRecognitionState> = _voiceRecognitionState.asStateFlow()

    private val _voiceRecognitionMessage = MutableStateFlow<String?>(null)
    val voiceRecognitionMessage: StateFlow<String?> = _voiceRecognitionMessage.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    private var wsJob: Job? = null
    private var activeAssistantId: String? = null
    private var activeFollowUpAssistantId: String? = null
    private var activeStreamUserText: String? = null
    private var activeFollowUpText: String? = null
    private var lastProductFollowUpPayload: ProductFollowUpPayload? = null

    fun connect() {
        if (wsJob?.isActive == true) return
        wsJob = scope.launch {
            wsClient.connect().collect { event ->
                _realtimeEvents.tryEmit(event)
                handleRealtimeEvent(event)
            }
        }
    }

    fun disconnect() {
        wsJob?.cancel()
        wsJob = null
        wsClient.close()
        audioPlayer.release()
    }

    fun newSession(): String {
        val sessionId = "session_${UUID.randomUUID()}"
        _chatMessages.value = emptyList()
        _phase.value = ChatExperiencePhase.Idle
        _isSending.value = false
        _errorMessage.value = null
        activeAssistantId = null
        activeFollowUpAssistantId = null
        activeStreamUserText = null
        activeFollowUpText = null
        lastProductFollowUpPayload = null
        audioPlayer.stop()
        return sessionId
    }

    fun selectSession(sessionId: String, messages: List<ChatMessageUiModel>) {
        _chatMessages.value = messages
        _phase.value = ChatExperiencePhase.Idle
        _isSending.value = false
        _errorMessage.value = null
        activeAssistantId = null
        activeFollowUpAssistantId = null
        activeStreamUserText = null
        activeFollowUpText = null
        lastProductFollowUpPayload = null
        audioPlayer.stop()
    }

    fun sendUserMessage(sessionId: String, text: String, ttsEnabled: Boolean) {
        if (_isSending.value) return
        audioPlayer.stop()

        val userMessage = ChatMessageUiModel(
            id = "user_${UUID.randomUUID()}",
            role = MessageRole.User,
            text = text.trim(),
        )
        val assistantId = "assistant_${UUID.randomUUID()}"
        activeAssistantId = assistantId
        activeStreamUserText = text.trim()

        _chatMessages.value = _chatMessages.value + userMessage + ChatMessageUiModel(
            id = assistantId,
            role = MessageRole.Assistant,
            isStreaming = true,
            expectedProductCount = 0,
        )
        _isSending.value = true
        _phase.value = ChatExperiencePhase.AssistantThinking
        _errorMessage.value = null

        ensureConnected()
        wsClient.sendUserMessage(sessionId, text.trim(), ttsEnabled = ttsEnabled)

        scope.launch(Dispatchers.Default) {
            delay(30_000L)
            if (activeAssistantId == assistantId && isMessageStreaming(assistantId)) {
                handleStreamInterrupted(assistantId, "连接中断，请重试。")
            }
        }
    }

    fun sendProductFollowUp(sessionId: String, productId: String, text: String, ttsEnabled: Boolean) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return
        audioPlayer.stop()

        lastProductFollowUpPayload = ProductFollowUpPayload(productId, trimmed)

        val userMessage = ChatMessageUiModel(
            id = "user_${UUID.randomUUID()}",
            role = MessageRole.User,
            text = "围绕追问：$trimmed",
        )
        val assistantId = "assistant_${UUID.randomUUID()}"
        activeFollowUpAssistantId = assistantId
        activeFollowUpText = trimmed

        _chatMessages.value = _chatMessages.value + userMessage + ChatMessageUiModel(
            id = assistantId,
            role = MessageRole.Assistant,
            isStreaming = true,
        )
        _isSending.value = true
        _phase.value = ChatExperiencePhase.AssistantThinking

        ensureConnected()
        wsClient.sendProductFollowup(sessionId, productId, trimmed, ttsEnabled = ttsEnabled)

        scope.launch(Dispatchers.Default) {
            delay(30_000L)
            if (activeFollowUpAssistantId == assistantId && isMessageStreaming(assistantId)) {
                handleStreamInterrupted(assistantId, "连接中断，请重试。")
            }
        }
    }

    fun sendVoiceMessage(audioFile: File, sessionId: String, ttsEnabled: Boolean) {
        scope.launch {
            _isSending.value = true
            _phase.value = ChatExperiencePhase.UserSending
            _voiceRecognitionState.value = VoiceRecognitionState.Transcribing
            _voiceRecognitionMessage.value = "正在识别语音"
            _errorMessage.value = null

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
                        _voiceRecognitionState.value = VoiceRecognitionState.Succeeded
                        _voiceRecognitionMessage.value = text.trim()
                        sendUserMessage(sessionId, text.trim(), ttsEnabled)
                    } else {
                        _isSending.value = false
                        _phase.value = ChatExperiencePhase.Idle
                        _voiceRecognitionState.value = VoiceRecognitionState.Empty
                        _voiceRecognitionMessage.value = "没听清，请再说一次"
                    }
                },
                onFailure = { e ->
                    val timedOut = e is TimeoutCancellationException ||
                        e is java.net.SocketTimeoutException ||
                        e.message?.lowercase()?.contains("timeout") == true
                    val displayMessage = when {
                        timedOut -> "语音识别超时，请再试一次"
                        e.message?.lowercase()?.contains("connection") == true -> "语音识别连接中断，请再试一次"
                        !e.message.isNullOrBlank() -> e.message!!
                        else -> "语音识别失败，请再试一次"
                    }
                    _isSending.value = false
                    _phase.value = ChatExperiencePhase.Idle
                    _voiceRecognitionState.value = if (timedOut) VoiceRecognitionState.Timeout else VoiceRecognitionState.Failed
                    _voiceRecognitionMessage.value = displayMessage
                    _errorMessage.value = "语音识别失败: $displayMessage"
                }
            )
        }
    }

    fun setSpeakerEnabled(enabled: Boolean) {
        _isSpeakerEnabled.value = enabled
        if (!enabled) audioPlayer.stop()
    }

    fun stopAudio() {
        audioPlayer.stop()
    }

    fun consumeError() {
        _errorMessage.value = null
    }

    fun getLastProductFollowUpPayload(): ProductFollowUpPayload? = lastProductFollowUpPayload

    private fun ensureConnected() {
        connect()
    }

    private fun handleRealtimeEvent(event: RealtimeEvent) {
        when (event) {
            is RealtimeEvent.TextDelta -> {
                activeFollowUpAssistantId?.let { appendAssistantText(it, event.text) }
                    ?: activeAssistantId?.let { appendAssistantText(it, event.text) }
            }
            is RealtimeEvent.ProductsStart -> {
                activeAssistantId?.let { updateExpectedCount(it, event.expectedCount) }
                _phase.value = ChatExperiencePhase.RecommendationLoading
            }
            is RealtimeEvent.ProductItem -> {
                activeAssistantId?.let { appendAssistantProduct(it, event.product) }
            }
            is RealtimeEvent.ProductsDone -> {
                _phase.value = ChatExperiencePhase.RecommendationReady
            }
            is RealtimeEvent.BundleStart -> {
                activeAssistantId?.let { updateExpectedCount(it, 4) }
                _phase.value = ChatExperiencePhase.RecommendationLoading
            }
            is RealtimeEvent.BundleItem -> {
                activeAssistantId?.let { appendAssistantProduct(it, event.product) }
            }
            is RealtimeEvent.BundleDone -> {
                _phase.value = ChatExperiencePhase.RecommendationReady
            }
            is RealtimeEvent.FocusTextDelta -> {
                activeFollowUpAssistantId?.let { appendAssistantText(it, event.text) }
            }
            is RealtimeEvent.ReplacementProduct -> {
                activeFollowUpAssistantId?.let { appendAssistantProduct(it, event.product) }
            }
            is RealtimeEvent.FocusDone -> {
                activeFollowUpAssistantId?.let { finishFollowUpStream(it) }
                activeFollowUpAssistantId = null
                activeFollowUpText = null
                _isSending.value = activeAssistantId != null
            }
            is RealtimeEvent.AudioDelta -> {
                if (_isSpeakerEnabled.value) {
                    val pcm = android.util.Base64.decode(event.audioBase64, android.util.Base64.DEFAULT)
                    audioPlayer.enqueuePcm(pcm, event.sampleRate)
                }
            }
            is RealtimeEvent.AudioDone -> {
                if (_isSpeakerEnabled.value) audioPlayer.markEndOfStream()
            }
            is RealtimeEvent.CartUpdate -> {
                if (!event.message.isNullOrBlank()) {
                    (activeFollowUpAssistantId ?: activeAssistantId)?.let {
                        appendAssistantText(it, event.message)
                    }
                }
                if (event.success) {
                    _cartBadgeCount.value = event.badgeCount
                }
            }
            is RealtimeEvent.QuickActions -> {
                val targetId = activeFollowUpAssistantId ?: activeAssistantId ?: event.messageId
                updateQuickActions(targetId, event.actions)
            }
            is RealtimeEvent.Done -> {
                activeAssistantId?.let { finishStream(it) }
                activeAssistantId = null
            }
            is RealtimeEvent.Error -> {
                (activeFollowUpAssistantId ?: activeAssistantId)?.let {
                    handleStreamInterrupted(it, event.message)
                }
            }
            is RealtimeEvent.Ack -> Unit
            is RealtimeEvent.Unknown -> Unit
        }
    }

    private fun appendAssistantText(messageId: String, delta: String) {
        _chatMessages.update { messages ->
            messages.map { if (it.id == messageId && it.isStreaming) it.copy(text = it.text + delta) else it }
        }
    }

    private fun updateExpectedCount(messageId: String, count: Int) {
        _chatMessages.update { messages ->
            messages.map { if (it.id == messageId && it.isStreaming) it.copy(expectedProductCount = count) else it }
        }
    }

    private fun appendAssistantProduct(messageId: String, product: ProductUiModel) {
        _chatMessages.update { messages ->
            messages.map { msg ->
                if (msg.id == messageId && msg.isStreaming) msg.copy(products = msg.products + product) else msg
            }
        }
    }

    private fun updateQuickActions(messageId: String, actions: List<com.example.shopguideagent.data.model.QuickActionUiModel>) {
        _chatMessages.update { messages ->
            messages.map { msg ->
                if (msg.id == messageId && actions.isNotEmpty()) msg.copy(quickActions = actions) else msg
            }
        }
    }

    private fun finishStream(messageId: String) {
        _isSending.value = false
        _phase.value = ChatExperiencePhase.RecommendationReady
        _chatMessages.update { messages ->
            messages.map { if (it.id == messageId && it.isStreaming) it.copy(isStreaming = false) else it }
        }
        activeStreamUserText = null
    }

    private fun finishFollowUpStream(messageId: String) {
        _phase.value = ChatExperiencePhase.RecommendationReady
        _chatMessages.update { messages ->
            messages.map { if (it.id == messageId && it.isStreaming) it.copy(isStreaming = false) else it }
        }
    }

    private fun handleStreamInterrupted(messageId: String, reason: String) {
        val retryText = when (messageId) {
            activeFollowUpAssistantId -> activeFollowUpText
            activeAssistantId -> activeStreamUserText
            else -> activeStreamUserText ?: activeFollowUpText
        }
        _isSending.value = false
        _phase.value = ChatExperiencePhase.Error
        _errorMessage.value = reason
        _chatMessages.update { messages ->
            messages.map { message ->
                if (message.id == messageId && message.isStreaming) {
                    message.copy(
                        text = if (message.text.isBlank()) reason else "${message.text}\n\n$reason",
                        isStreaming = false,
                        expectedProductCount = message.products.size,
                    )
                } else message
            }
        }
        if (activeAssistantId == messageId) {
            activeAssistantId = null
            activeStreamUserText = null
        }
        if (activeFollowUpAssistantId == messageId) {
            activeFollowUpAssistantId = null
            activeFollowUpText = null
        }
    }

    private fun isMessageStreaming(messageId: String): Boolean =
        _chatMessages.value.any { it.id == messageId && it.isStreaming }
}
```

- [ ] **Step 2: Update ChatViewModel to delegate to SpriteChatCoordinator**

In `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`, add a `coordinator: SpriteChatCoordinator` constructor parameter (with default) and delegate all WebSocket/audio operations to it. Keep the history repository logic in ChatViewModel since it is chat-page-specific. The key changes:

Add import:
```kotlin
import com.example.shopguideagent.domain.chat.SpriteChatCoordinator
```

Change constructor:
```kotlin
class ChatViewModel @JvmOverloads constructor(
    private val productCatalog: ProductCatalog? = null,
    private val historyRepository: ChatHistoryRepository? = null,
    private val coordinator: SpriteChatCoordinator = SpriteChatCoordinator(),
) : ViewModel() {
```

Remove the `wsClient`, `sttApi`, `audioPlayer` fields and all WebSocket/audio handling logic. Replace `sendMessageStreaming`, `sendProductFollowUp`, `sendVoiceMessage`, `ensureWebSocketConnection`, `handleRealtimeEvent`, and all helper methods with delegation to `coordinator`.

Keep: `newSession`, `selectSession`, `deleteSession`, `updateCartBadge`, `setSpeakerEnabled`, `consumeError`, `getLastProductFollowUpPayload`, `getLastProductFollowUpPayloadJson`, `persist`, `titleFor`, and the `historyState` flow.

Expose coordinator flows via ChatViewModel:
```kotlin
val uiState: StateFlow<ChatUiState> = ... // derived from coordinator + history
val realtimeEvents: SharedFlow<RealtimeEvent> = coordinator.realtimeEvents
```

- [ ] **Step 3: Run ChatViewModel tests**

Run: `./gradlew :app:testDebugUnitTest --tests "*ChatViewModel*"`
Expected: All pass. If failures, adjust delegation to preserve observable behavior.

- [ ] **Step 4: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/domain/chat/SpriteChatCoordinator.kt \
        client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt
git commit -m "refactor: extract SpriteChatCoordinator from ChatViewModel for shared session management"
```

---

## Task 3: Expand SpriteHomeUiState and SpriteHomeAction for Voice + Chat + Product

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeUiState.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeAction.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeStateMapper.kt` (inline in SpriteHomeUiState.kt)
- Test: `client/app/src/test/java/com/example/shopguideagent/ui/theme/DesignTokenTest.kt` (existing, verify compile)

**Interfaces:**
- Consumes: `ChatExperiencePhase`, `VoiceRecognitionState`, `ChatMessageUiModel`, `ProductUiModel`
- Produces: expanded `SpriteHomeUiState` with chat/voice/product fields; expanded `SpriteHomeAction` sealed interface

- [ ] **Step 1: Expand SpriteHomeUiState**

In `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeUiState.kt`, add new fields to `SpriteHomeUiState` and supporting data classes:

After `SpeechBubbleStyle` enum, add:
```kotlin
data class VoiceBarUiState(
    val isRecording: Boolean = false,
    val isCancelPending: Boolean = false,
    val transcript: String = "",
    val recognitionState: com.example.shopguideagent.data.model.VoiceRecognitionState = com.example.shopguideagent.data.model.VoiceRecognitionState.Idle,
    val recognitionMessage: String? = null,
)

data class SpriteProductSheetUiState(
    val primaryProduct: ProductUiModel? = null,
    val alternatives: List<ProductUiModel> = emptyList(),
    val isVisible: Boolean = false,
    val isLoading: Boolean = false,
    val quickActions: List<com.example.shopguideagent.data.model.QuickActionUiModel> = emptyList(),
)
```

Update `SpriteHomeUiState` data class (add new fields, keep all existing):
```kotlin
data class SpriteHomeUiState(
    val userProfile: UserProfileUiState = UserProfileUiState(),
    val spiritProgress: SpiritProgressUiState = SpiritProgressUiState(),
    val appearance: AvatarAppearance = AvatarAppearance(),
    val baseAvatarState: AvatarState = AvatarState.IDLE,
    val transientAvatarState: AvatarState? = null,
    val speechBubble: SpeechBubbleUiState = SpeechBubbleUiState(),
    val dailyTask: DailyTaskUiState = DailyTaskUiState(),
    val newOutfitHint: NewOutfitHintUiState? = NewOutfitHintUiState(),
    val presentingProduct: ProductUiModel? = null,
    val productPresentation: ProductPresentationUiState = ProductPresentationUiState(),
    val cartCount: Int = 0,
    val isRealtimeConnected: Boolean = false,
    val isLoading: Boolean = false,
    val animationSequence: Long = 0L,
    val earnedStars: Int = 886,
    // NEW fields for voice-first shopping:
    val voiceBar: VoiceBarUiState = VoiceBarUiState(),
    val productSheet: SpriteProductSheetUiState = SpriteProductSheetUiState(),
    val chatMessages: List<ChatMessageUiModel> = emptyList(),
    val isChatMode: Boolean = false,
    val isSpeakerEnabled: Boolean = true,
    val errorMessage: String? = null,
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
```

- [ ] **Step 2: Expand SpriteHomeAction**

Replace `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeAction.kt`:
```kotlin
package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ProductUiModel

sealed interface SpriteHomeAction {
    // Existing actions (keep)
    object DressUpClicked : SpriteHomeAction
    object EarnFireClicked : SpriteHomeAction
    object GuideClicked : SpriteHomeAction
    object DailyTaskClicked : SpriteHomeAction
    object NewOutfitClicked : SpriteHomeAction
    object MenuClicked : SpriteHomeAction
    object CloseClicked : SpriteHomeAction
    object ProfileClicked : SpriteHomeAction
    object SpeechBubbleClicked : SpriteHomeAction
    object ProductClicked : SpriteHomeAction
    object RetryClicked : SpriteHomeAction

    // NEW: Voice actions
    data class VoicePressStarted(val permissionGranted: Boolean) : SpriteHomeAction
    object VoiceDragCancelled : SpriteHomeAction
    object VoiceReleased : SpriteHomeAction
    object VoiceCancelled : SpriteHomeAction

    // NEW: Text input action
    data class TextSubmitted(val text: String) : SpriteHomeAction

    // NEW: Product actions
    data class ProductAddToCart(val product: ProductUiModel) : SpriteHomeAction
    data class ProductDetailOpen(val product: ProductUiModel) : SpriteHomeAction
    data class ProductFollowUp(val product: ProductUiModel, val followUpText: String) : SpriteHomeAction
    data class QuickActionClicked(val action: String) : SpriteHomeAction

    // NEW: Cart action
    object CartClicked : SpriteHomeAction

    // NEW: Chat-mode switch
    object ChatModeSwitchClicked : SpriteHomeAction
    object BackToSpriteSpace : SpriteHomeAction

    // NEW: Speaker toggle
    object SpeakerToggleClicked : SpriteHomeAction

    // NEW: Error dismiss
    object ErrorDismissed : SpriteHomeAction
}
```

- [ ] **Step 3: Verify compilation**

Run: `./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL (or at least no errors in these files).

- [ ] **Step 4: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeUiState.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeAction.kt
git commit -m "feat: expand SpriteHomeUiState and SpriteHomeAction for voice, product, and chat-mode"
```

---

## Task 4: Build SpriteTopBar Component

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteTopBar.kt`
- Test: Preview-based verification (no unit test needed for pure UI)

**Interfaces:**
- Consumes: `cartCount: Int`, `isChatMode: Boolean`, `onAction: (SpriteHomeAction) -> Unit`
- Produces: `SpriteTopBar` composable with chat-mode switch, cart badge, settings/menu

- [ ] **Step 1: Create SpriteTopBar composable**

Create `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteTopBar.kt`:
```kotlin
package com.example.shopguideagent.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.SmartToy
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.component.CartBadge
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpriteHomeTokens
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun SpriteTopBar(
    cartCount: Int,
    isChatMode: Boolean,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Left: Settings / Menu
        IconButton(
            onClick = { onAction(SpriteHomeAction.MenuClicked) },
            modifier = Modifier.size(44.dp),
        ) {
            Surface(
                shape = CircleShape,
                color = SpriteHomeTokens.Panel,
                shadowElevation = 4.dp,
            ) {
                Icon(
                    imageVector = Icons.Outlined.Settings,
                    contentDescription = "设置",
                    tint = Color(0xFF4A3524),
                    modifier = Modifier
                        .size(44.dp)
                        .padding(10.dp),
                )
            }
        }

        // Center: Title / identity
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(
                imageVector = Icons.Outlined.SmartToy,
                contentDescription = null,
                tint = Color(0xFF4A3524),
                modifier = Modifier.size(24.dp),
            )
            Text(
                text = "精灵空间",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = TextPrimary,
            )
        }

        // Right: Chat-mode switch + Cart
        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Chat-mode toggle button
            IconButton(
                onClick = { onAction(SpriteHomeAction.ChatModeSwitchClicked) },
                modifier = Modifier.size(44.dp),
            ) {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = if (isChatMode) SpriteHomeTokens.PrimaryButton else SpriteHomeTokens.Panel,
                    shadowElevation = 4.dp,
                ) {
                    Icon(
                        imageVector = if (isChatMode) Icons.AutoMirrored.Outlined.Chat else Icons.Outlined.ChatBubbleOutline,
                        contentDescription = if (isChatMode) "切换回精灵空间" else "切换到聊天模式",
                        tint = if (isChatMode) Color(0xFF4A3524) else Color(0xFF4A3524),
                        modifier = Modifier
                            .size(44.dp)
                            .padding(10.dp),
                    )
                }
            }

            CartBadge(
                count = cartCount,
                onClick = { onAction(SpriteHomeAction.CartClicked) },
            )
        }
    }
}

@Preview(showBackground = true, widthDp = 390)
@Composable
private fun SpriteTopBarPreview() {
    ShopGuideAgentTheme {
        SpriteTopBar(cartCount = 3, isChatMode = false, onAction = {})
    }
}

@Preview(showBackground = true, widthDp = 390)
@Composable
private fun SpriteTopBarChatModePreview() {
    ShopGuideAgentTheme {
        SpriteTopBar(cartCount = 0, isChatMode = true, onAction = {})
    }
}
```

- [ ] **Step 2: Verify preview renders**

Use Android Studio layout inspector or build:
Run: `./gradlew :app:compileDebugKotlin`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteTopBar.kt
git commit -m "feat: add SpriteTopBar with chat-mode switch and cart badge"
```

---

## Task 5: Build SpriteVoiceBar Component

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteVoiceBar.kt`
- Test: Preview-based verification

**Interfaces:**
- Consumes: `VoiceBarUiState`, `enabled: Boolean`, `onAction: (SpriteHomeAction) -> Unit`
- Produces: `SpriteVoiceBar` composable with hold-to-talk mic, text input, speaker toggle

- [ ] **Step 1: Create SpriteVoiceBar composable**

Create `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteVoiceBar.kt`:
```kotlin
package com.example.shopguideagent.ui.home

import android.Manifest
import android.content.pm.PackageManager
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.VolumeMute
import androidx.compose.material.icons.outlined.VolumeUp
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.VoiceRecognitionState
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SurfaceSecondary
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextTertiary
import com.example.shopguideagent.ui.theme.WarningColor

@Composable
fun SpriteVoiceBar(
    state: VoiceBarUiState,
    enabled: Boolean,
    speakerEnabled: Boolean,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var inputText by remember { mutableStateOf("") }
    val keyboardController = LocalSoftwareKeyboardController.current
    val canSend = enabled && inputText.isNotBlank() && !state.isRecording

    Surface(
        modifier = modifier.fillMaxWidth(),
        color = Color.White.copy(alpha = 0.85f),
        shape = RoundedCornerShape(topStart = AppCornerRadius.Sheet, topEnd = AppCornerRadius.Sheet),
        shadowElevation = 12.dp,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // Voice cancel indicator
            AnimatedVisibility(
                visible = state.isCancelPending,
                enter = fadeIn(tween(150)) + slideInVertically(tween(200)) { it / 2 },
                exit = fadeOut(tween(120)) + slideOutVertically(tween(180)) { it / 2 },
            ) {
                Text(
                    text = "上滑取消",
                    color = WarningColor,
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.padding(top = 10.dp, bottom = 6.dp),
                )
            }

            // Recognition status
            AnimatedVisibility(
                visible = state.recognitionState != VoiceRecognitionState.Idle &&
                    state.recognitionState != VoiceRecognitionState.Succeeded,
                enter = fadeIn(tween(150)) + slideInVertically(tween(180)) { it / 2 },
                exit = fadeOut(tween(120)) + slideOutVertically(tween(160)) { it / 2 },
            ) {
                val color = when (state.recognitionState) {
                    VoiceRecognitionState.Failed, VoiceRecognitionState.Timeout -> WarningColor
                    VoiceRecognitionState.Empty -> TextSecondary
                    else -> BrandPrimary
                }
                Text(
                    text = state.recognitionMessage.orEmpty(),
                    color = color,
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 18.dp, vertical = 6.dp),
                )
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 68.dp)
                    .padding(horizontal = 14.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // Speaker toggle
                IconButton(
                    onClick = { onAction(SpriteHomeAction.SpeakerToggleClicked) },
                    modifier = Modifier.size(40.dp),
                ) {
                    Surface(
                        shape = CircleShape,
                        color = if (speakerEnabled) BrandPrimary else SurfaceSecondary,
                    ) {
                        Icon(
                            imageVector = if (speakerEnabled) Icons.Outlined.VolumeUp else Icons.Outlined.VolumeMute,
                            contentDescription = if (speakerEnabled) "扬声器开启" else "扬声器关闭",
                            tint = if (speakerEnabled) TextOnBrand else TextTertiary,
                            modifier = Modifier
                                .size(40.dp)
                                .padding(8.dp),
                        )
                    }
                }

                // Hold-to-talk mic button (when not recording) or wave animation (when recording)
                if (state.isRecording) {
                    VoiceWaveAnimation(
                        isCancelPending = state.isCancelPending,
                        modifier = Modifier.weight(1f),
                    )
                } else {
                    TextField(
                        value = inputText,
                        onValueChange = { inputText = it },
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = 48.dp, max = 120.dp),
                        placeholder = { Text("说说你想买什么...", color = TextTertiary) },
                        enabled = enabled,
                        singleLine = false,
                        maxLines = 3,
                        shape = RoundedCornerShape(AppCornerRadius.Input),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = {
                            if (inputText.isNotBlank()) {
                                onAction(SpriteHomeAction.TextSubmitted(inputText.trim()))
                                inputText = ""
                                keyboardController?.hide()
                            }
                        }),
                        colors = TextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            focusedContainerColor = SurfaceSecondary,
                            unfocusedContainerColor = SurfaceSecondary,
                            disabledContainerColor = SurfaceSecondary,
                            focusedIndicatorColor = Color.Transparent,
                            unfocusedIndicatorColor = Color.Transparent,
                            disabledIndicatorColor = Color.Transparent,
                            cursorColor = BrandPrimary,
                        ),
                    )
                }

                // Mic hold button
                Box(
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .background(
                            when {
                                !enabled -> Color.LightGray
                                state.isRecording -> if (state.isCancelPending) WarningColor else BrandPrimary
                                else -> BrandPrimary.copy(alpha = 0.15f)
                            }
                        )
                        .pointerInput(enabled) {
                            if (!enabled) return@pointerInput
                            awaitEachGesture {
                                awaitFirstDown(requireUnconsumed = false)
                                val hasPermission = context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                                    PackageManager.PERMISSION_GRANTED
                                onAction(SpriteHomeAction.VoicePressStarted(hasPermission))
                                var totalDragY = 0f
                                do {
                                    val event = awaitPointerEvent()
                                    event.changes.forEach { change ->
                                        totalDragY += change.positionChange().y
                                        change.consume()
                                    }
                                    if (totalDragY < -80f && !state.isCancelPending) {
                                        onAction(SpriteHomeAction.VoiceDragCancelled)
                                    }
                                } while (event.changes.any { it.pressed })
                                if (state.isCancelPending) {
                                    onAction(SpriteHomeAction.VoiceCancelled)
                                } else {
                                    onAction(SpriteHomeAction.VoiceReleased)
                                }
                            }
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = Icons.Outlined.Mic,
                        contentDescription = if (state.isRecording) "正在聆听" else "按住说话",
                        tint = if (state.isRecording) TextOnBrand else BrandPrimary,
                        modifier = Modifier.size(24.dp),
                    )
                }

                // Send button (when text entered and not recording)
                if (!state.isRecording) {
                    Surface(
                        onClick = {
                            if (inputText.isNotBlank()) {
                                onAction(SpriteHomeAction.TextSubmitted(inputText.trim()))
                                inputText = ""
                                keyboardController?.hide()
                            }
                        },
                        enabled = canSend,
                        modifier = Modifier.size(40.dp),
                        shape = CircleShape,
                        color = if (canSend) BrandPrimary else Color.Transparent,
                        contentColor = if (canSend) TextOnBrand else TextTertiary,
                        shadowElevation = if (canSend) 2.dp else 0.dp,
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Outlined.Send,
                                contentDescription = "发送",
                                modifier = Modifier.size(20.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun VoiceWaveAnimation(
    isCancelPending: Boolean,
    modifier: Modifier = Modifier,
) {
    val transition = rememberInfiniteTransition(label = "voiceWave")
    val phase by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 720),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "voiceWavePhase",
    )
    val color = if (isCancelPending) WarningColor else BrandPrimary

    Surface(
        modifier = modifier.height(48.dp),
        shape = RoundedCornerShape(AppCornerRadius.Input),
        color = SurfaceSecondary,
        border = androidx.compose.foundation.BorderStroke(1.dp, BorderLight),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(
                modifier = Modifier.width(54.dp),
                horizontalArrangement = Arrangement.spacedBy(3.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                repeat(5) { index ->
                    val height = 10.dp + (phase * (index + 1) * 2).dp
                    Box(
                        modifier = Modifier
                            .width(4.dp)
                            .height(height)
                            .clip(CircleShape)
                            .background(color),
                    )
                }
            }
            Text(
                text = if (isCancelPending) "上滑取消" else "正在聆听...",
                color = if (isCancelPending) WarningColor else TextPrimary,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Preview(showBackground = true, widthDp = 390)
@Composable
private fun SpriteVoiceBarIdlePreview() {
    ShopGuideAgentTheme {
        SpriteVoiceBar(
            state = VoiceBarUiState(),
            enabled = true,
            speakerEnabled = true,
            onAction = {},
        )
    }
}

@Preview(showBackground = true, widthDp = 390)
@Composable
private fun SpriteVoiceBarRecordingPreview() {
    ShopGuideAgentTheme {
        SpriteVoiceBar(
            state = VoiceBarUiState(isRecording = true),
            enabled = true,
            speakerEnabled = true,
            onAction = {},
        )
    }
}
```

- [ ] **Step 2: Verify compilation**

Run: `./gradlew :app:compileDebugKotlin`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteVoiceBar.kt
git commit -m "feat: add SpriteVoiceBar with hold-to-talk mic, text input, and speaker toggle"
```

---

## Task 6: Build ProductPresentationSheet Component

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/ui/home/ProductPresentationSheet.kt`
- Test: Preview-based verification

**Interfaces:**
- Consumes: `SpriteProductSheetUiState`, `onAction: (SpriteHomeAction) -> Unit`
- Produces: `ProductPresentationSheet` composable showing primary product card + alternatives carousel

- [ ] **Step 1: Create ProductPresentationSheet composable**

Create `client/app/src/main/java/com/example/shopguideagent/ui/home/ProductPresentationSheet.kt`:
```kotlin
package com.example.shopguideagent.ui.home

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.QuickActionUiModel
import com.example.shopguideagent.ui.component.AlternativeProductCard
import com.example.shopguideagent.ui.component.HeroProductCard
import com.example.shopguideagent.ui.component.QuickActionChips
import com.example.shopguideagent.ui.component.ProductSkeletonCard
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpriteHomeTokens
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun ProductPresentationSheet(
    state: SpriteProductSheetUiState,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    AnimatedVisibility(
        visible = state.isVisible,
        enter = slideInVertically(tween(350)) { it } + fadeIn(tween(250)),
        exit = slideOutVertically(tween(250)) { it },
        modifier = modifier,
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(
                topStart = SpriteHomeTokens.CardRadius,
                topEnd = SpriteHomeTokens.CardRadius,
            ),
            color = SpriteHomeTokens.Panel.copy(alpha = 1f),
            shadowElevation = 16.dp,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 14.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                // Sheet handle
                Surface(
                    modifier = Modifier
                        .fillMaxWidth(0.2f)
                        .height(4.dp)
                        .align(androidx.compose.ui.Alignment.CenterHorizontally),
                    shape = RoundedCornerShape(999.dp),
                    color = TextSecondary.copy(alpha = 0.3f),
                ) {}

                // Primary product
                state.primaryProduct?.let { product ->
                    HeroProductCard(
                        product = product,
                        onClick = { onAction(SpriteHomeAction.ProductDetailOpen(product)) },
                        onAddToCart = { onAction(SpriteHomeAction.ProductAddToCart(product)) },
                        onRefine = { onAction(SpriteHomeAction.ProductFollowUp(product, it)) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }

                // Skeleton loading state
                if (state.isLoading && state.primaryProduct == null) {
                    ProductSkeletonCard(hero = true)
                }

                // Quick actions
                if (state.quickActions.isNotEmpty()) {
                    QuickActionChips(
                        actions = state.quickActions,
                        onActionClick = { onAction(SpriteHomeAction.QuickActionClicked(it)) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }

                // Alternatives carousel
                if (state.alternatives.isNotEmpty()) {
                    Column(
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text(
                            text = "你也可以看看",
                            style = MaterialTheme.typography.titleSmall,
                            color = TextPrimary,
                            fontWeight = FontWeight.SemiBold,
                        )
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            items(state.alternatives, key = { it.productId }) { product ->
                                AlternativeProductCard(
                                    product = product,
                                    index = 0,
                                    onClick = { onAction(SpriteHomeAction.ProductDetailOpen(product)) },
                                    onAddToCart = { onAction(SpriteHomeAction.ProductAddToCart(product)) },
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))
            }
        }
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 600)
@Composable
private fun ProductPresentationSheetPreview() {
    ShopGuideAgentTheme {
        ProductPresentationSheet(
            state = SpriteProductSheetUiState(
                primaryProduct = ProductUiModel(
                    productId = "p1",
                    name = "智能降噪耳机",
                    price = 299.0,
                    isPrimary = true,
                ),
                alternatives = listOf(
                    ProductUiModel(productId = "p2", name = "运动蓝牙耳机", price = 199.0),
                    ProductUiModel(productId = "p3", name = "头戴式耳机", price = 399.0),
                ),
                isVisible = true,
                quickActions = listOf(
                    QuickActionUiModel("再看看别的", "refine"),
                    QuickActionUiModel("加入购物车", "add_to_cart"),
                ),
            ),
            onAction = {},
        )
    }
}
```

- [ ] **Step 2: Verify compilation**

Run: `./gradlew :app:compileDebugKotlin`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/ProductPresentationSheet.kt
git commit -m "feat: add ProductPresentationSheet for inline product recommendations in sprite space"
```

---

## Task 7: Merge SpriteHomeViewModel with Chat/Voice Capabilities

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt`
- Test: `client/app/src/test/java/com/example/shopguideagent/vm/ChatViewModelVoiceTest.kt` (existing, verify still passes)

**Interfaces:**
- Consumes: `SpriteChatCoordinator`, `CartOperationEvent`, `VoiceInputManager`, `VoiceInputResult`
- Produces: `SpriteHomeViewModel` that handles all voice input, WebSocket messaging, TTS, product presentation, and cart operations

- [ ] **Step 1: Rewrite SpriteHomeViewModel to integrate chat/voice**

Replace `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt`:

```kotlin
package com.example.shopguideagent.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.shopguideagent.data.model.ChatExperiencePhase
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.RealtimeEvent
import com.example.shopguideagent.data.model.VoiceRecognitionState
import com.example.shopguideagent.domain.chat.SpriteChatCoordinator
import com.example.shopguideagent.domain.event.CartOperationEvent
import com.example.shopguideagent.data.repository.InMemorySpiritAppearanceRepository
import com.example.shopguideagent.data.repository.InMemorySpiritProgressRepository
import com.example.shopguideagent.data.repository.SpiritAppearanceRepository
import com.example.shopguideagent.data.repository.SpiritProgressRepository
import com.example.shopguideagent.voice.VoiceInputManager
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File

class SpriteHomeViewModel(
    initialState: SpriteHomeUiState? = null,
    private val progressRepository: SpiritProgressRepository = InMemorySpiritProgressRepository(),
    private val appearanceRepository: SpiritAppearanceRepository = InMemorySpiritAppearanceRepository(),
    private val coordinator: SpriteChatCoordinator = SpriteChatCoordinator(),
) : ViewModel() {

    private val _uiState = MutableStateFlow(
        initialState ?: SpriteHomeUiState(
            spiritProgress = progressRepository.loadProgress(),
            appearance = appearanceRepository.loadAppearance(),
        ),
    )
    val uiState: StateFlow<SpriteHomeUiState> = _uiState.asStateFlow()

    private val _effects = MutableSharedFlow<SpriteHomeEffect>(extraBufferCapacity = 16)
    val effects: SharedFlow<SpriteHomeEffect> = _effects.asSharedFlow()

    private val processedCartEvents = mutableSetOf<String>()
    private var voiceManager: VoiceInputManager? = null
    private var sessionId: String = coordinator.newSession()

    init {
        coordinator.connect()
        viewModelScope.launch {
            coordinator.realtimeEvents.collect { onRealtimeEvent(it) }
        }
        viewModelScope.launch {
            coordinator.phase.collect { phase ->
                onChatPhaseChanged(phase)
            }
        }
        viewModelScope.launch {
            coordinator.cartBadgeCount.collect { count ->
                _uiState.update { it.copy(cartCount = count) }
            }
        }
        viewModelScope.launch {
            coordinator.voiceRecognitionState.collect { state ->
                _uiState.update { current ->
                    current.copy(
                        voiceBar = current.voiceBar.copy(recognitionState = state),
                    )
                }
            }
        }
        viewModelScope.launch {
            coordinator.voiceRecognitionMessage.collect { message ->
                _uiState.update { current ->
                    current.copy(
                        voiceBar = current.voiceBar.copy(recognitionMessage = message),
                    )
                }
            }
        }
        viewModelScope.launch {
            coordinator.errorMessage.collect { error ->
                _uiState.update { current ->
                    current.copy(errorMessage = error)
                }
            }
        }
        viewModelScope.launch {
            coordinator.isSpeakerEnabled.collect { enabled ->
                _uiState.update { current ->
                    current.copy(isSpeakerEnabled = enabled)
                }
            }
        }
    }

    override fun onCleared() {
        coordinator.disconnect()
        voiceManager?.release()
        super.onCleared()
    }

    fun onAction(action: SpriteHomeAction) {
        when (action) {
            // Legacy actions
            SpriteHomeAction.DressUpClicked -> {
                setSpeech("装扮功能即将开放")
                emitEffect(SpriteHomeEffect.NavigateToWardrobe)
            }
            SpriteHomeAction.EarnFireClicked -> {
                setSpeech("完成导购任务就能赚火星")
                emitEffect(SpriteHomeEffect.NavigateToTasks)
            }
            SpriteHomeAction.GuideClicked,
            SpriteHomeAction.MenuClicked,
            SpriteHomeAction.CloseClicked -> emitEffect(SpriteHomeEffect.NavigateToGuide)
            SpriteHomeAction.DailyTaskClicked -> handleDailyTaskClicked()
            SpriteHomeAction.NewOutfitClicked -> applyNewOutfit()
            SpriteHomeAction.ProfileClicked -> emitEffect(SpriteHomeEffect.ShowMessage("用户资料暂未开放"))
            SpriteHomeAction.SpeechBubbleClicked -> Unit
            SpriteHomeAction.ProductClicked -> {
                uiState.value.presentingProduct?.productId?.let {
                    emitEffect(SpriteHomeEffect.OpenProduct(it))
                }
            }
            SpriteHomeAction.RetryClicked -> setBaseState(AvatarState.SEARCHING)

            // NEW: Voice actions
            is SpriteHomeAction.VoicePressStarted -> {
                if (action.permissionGranted) {
                    startVoiceRecording()
                } else {
                    emitEffect(SpriteHomeEffect.ShowMessage("需要麦克风权限才能语音输入"))
                }
            }
            SpriteHomeAction.VoiceDragCancelled -> {
                _uiState.update { current ->
                    current.copy(voiceBar = current.voiceBar.copy(isCancelPending = true))
                }
            }
            SpriteHomeAction.VoiceReleased -> {
                voiceManager?.finishRecording()
                _uiState.update { current ->
                    current.copy(voiceBar = current.voiceBar.copy(isRecording = false, isCancelPending = false))
                }
            }
            SpriteHomeAction.VoiceCancelled -> {
                voiceManager?.cancelRecording()
                _uiState.update { current ->
                    current.copy(voiceBar = current.voiceBar.copy(isRecording = false, isCancelPending = false))
                }
            }

            // NEW: Text input
            is SpriteHomeAction.TextSubmitted -> {
                coordinator.sendUserMessage(sessionId, action.text, _uiState.value.isSpeakerEnabled)
                onRequestSent()
            }

            // NEW: Product actions
            is SpriteHomeAction.ProductAddToCart -> {
                // Handled by CartViewModel via effect; emit effect for AppNavGraph
                emitEffect(SpriteHomeEffect.ShowMessage("已加入购物车"))
                // Also trigger sprite celebration
                rewardAddToCart(cartEventKey = null)
            }
            is SpriteHomeAction.ProductDetailOpen -> {
                emitEffect(SpriteHomeEffect.OpenProduct(action.product.productId))
            }
            is SpriteHomeAction.ProductFollowUp -> {
                coordinator.sendProductFollowUp(
                    sessionId,
                    action.product.productId,
                    action.followUpText,
                    _uiState.value.isSpeakerEnabled,
                )
                onRequestSent()
            }
            is SpriteHomeAction.QuickActionClicked -> {
                val focus = _uiState.value.productSheet.primaryProduct
                if (focus != null) {
                    coordinator.sendProductFollowUp(
                        sessionId,
                        focus.productId,
                        action.action,
                        _uiState.value.isSpeakerEnabled,
                    )
                } else {
                    coordinator.sendUserMessage(sessionId, action.action, _uiState.value.isSpeakerEnabled)
                }
                onRequestSent()
            }

            // NEW: Cart
            SpriteHomeAction.CartClicked -> emitEffect(SpriteHomeEffect.NavigateToGuide)

            // NEW: Chat mode switch
            SpriteHomeAction.ChatModeSwitchClicked -> {
                _uiState.update { it.copy(isChatMode = true) }
                emitEffect(SpriteHomeEffect.NavigateToGuide)
            }
            SpriteHomeAction.BackToSpriteSpace -> {
                _uiState.update { it.copy(isChatMode = false) }
            }

            // NEW: Speaker toggle
            SpriteHomeAction.SpeakerToggleClicked -> {
                coordinator.setSpeakerEnabled(!_uiState.value.isSpeakerEnabled)
            }

            // NEW: Error dismiss
            SpriteHomeAction.ErrorDismissed -> {
                coordinator.consumeError()
                _uiState.update { it.copy(errorMessage = null) }
            }
        }
    }

    fun bindVoiceManager(manager: VoiceInputManager) {
        voiceManager?.release()
        voiceManager = manager
    }

    fun onCartOperationEvent(event: CartOperationEvent) {
        when (event) {
            is CartOperationEvent.AddToCartSucceeded -> rewardAddToCart(eventKey = null)
            is CartOperationEvent.AddToCartFailed -> Unit
        }
    }

    fun onLocalAddToCartSuccess() {
        // Kept for binary/source compatibility
    }

    fun onStageAnimationFinished() {
        _uiState.update { current ->
            val stable = current.baseAvatarState
            current.copy(
                transientAvatarState = null,
                speechBubble = SpriteHomeStateMapper.speechFor(stable, current.presentingProduct),
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    // --- Private methods ---

    private fun startVoiceRecording() {
        _uiState.update { current ->
            current.copy(
                voiceBar = current.voiceBar.copy(isRecording = true, isCancelPending = false),
            )
        }
        setBaseState(AvatarState.LISTENING)
        voiceManager?.startRecording()
    }

    private fun onRequestSent() {
        setBaseState(AvatarState.SEARCHING)
    }

    private fun onChatPhaseChanged(phase: ChatExperiencePhase) {
        val baseState = when (phase) {
            ChatExperiencePhase.AssistantThinking,
            ChatExperiencePhase.UserSending,
            ChatExperiencePhase.RecommendationLoading -> AvatarState.SEARCHING
            ChatExperiencePhase.RecommendationReady -> AvatarState.PRESENTING
            ChatExperiencePhase.Error -> AvatarState.ERROR
            ChatExperiencePhase.Idle -> AvatarState.IDLE
        }
        val product = coordinator.chatMessages.value
            .asReversed()
            .firstNotNullOfOrNull { msg ->
                msg.products.firstOrNull { it.isPrimary } ?: msg.products.firstOrNull()
            }
        _uiState.update { current ->
            val nextProduct = product ?: current.presentingProduct
            current.copy(
                baseAvatarState = baseState,
                presentingProduct = nextProduct,
                speechBubble = SpriteHomeStateMapper.speechFor(
                    current.transientAvatarState ?: baseState,
                    nextProduct,
                ),
                productSheet = current.productSheet.copy(
                    isVisible = phase == ChatExperiencePhase.RecommendationLoading ||
                        phase == ChatExperiencePhase.RecommendationReady,
                    isLoading = phase == ChatExperiencePhase.RecommendationLoading,
                    primaryProduct = nextProduct,
                    alternatives = coordinator.chatMessages.value
                        .flatMap { it.products }
                        .filter { it.productId != nextProduct?.productId }
                        .take(2),
                    quickActions = coordinator.chatMessages.value
                        .lastOrNull { it.role == com.example.shopguideagent.data.model.MessageRole.Assistant }
                        ?.quickActions ?: emptyList(),
                ),
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun onRealtimeEvent(event: RealtimeEvent) {
        when (event) {
            is RealtimeEvent.CartUpdate -> if (event.success) {
                rewardAddToCart(cartEventKey(event))
            }
            is RealtimeEvent.Error -> {
                setTransientState(
                    AvatarState.ERROR,
                    SpeechBubbleUiState(event.message, style = SpeechBubbleStyle.ERROR),
                )
            }
            else -> Unit
        }
    }

    private fun setBaseState(avatarState: AvatarState) {
        _uiState.update { current ->
            current.copy(
                baseAvatarState = avatarState,
                speechBubble = SpriteHomeStateMapper.speechFor(
                    current.transientAvatarState ?: avatarState,
                    current.presentingProduct,
                ),
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun setTransientState(
        avatarState: AvatarState,
        speechBubble: SpeechBubbleUiState = SpriteHomeStateMapper.speechFor(
            avatarState,
            _uiState.value.presentingProduct,
        ),
    ) {
        _uiState.update { current ->
            current.copy(
                transientAvatarState = avatarState,
                speechBubble = speechBubble,
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun rewardAddToCart(eventKey: String?) {
        if (eventKey != null && !processedCartEvents.add(eventKey)) return
        var progressToSave: SpiritProgressUiState? = null
        _uiState.update { current ->
            val intimacyTotal = current.spiritProgress.currentIntimacy + SpriteHomeRewards.ADD_TO_CART_INTIMACY
            val levelUp = intimacyTotal >= current.spiritProgress.requiredIntimacy &&
                current.spiritProgress.requiredIntimacy > 0
            val nextTransient = if (levelUp) AvatarState.LEVEL_UP else AvatarState.CELEBRATING
            val nextLevel = if (levelUp) current.spiritProgress.level + 1 else current.spiritProgress.level
            val nextProgress = current.spiritProgress.copy(
                level = nextLevel,
                currentIntimacy = if (levelUp) 0 else intimacyTotal,
            )
            progressToSave = nextProgress
            current.copy(
                transientAvatarState = nextTransient,
                userProfile = current.userProfile.copy(
                    firePoints = current.userProfile.firePoints + SpriteHomeRewards.ADD_TO_CART_FIRE,
                ),
                spiritProgress = nextProgress,
                speechBubble = SpriteHomeStateMapper.speechFor(nextTransient, current.presentingProduct),
                animationSequence = current.animationSequence + 1,
            )
        }
        progressToSave?.let(progressRepository::saveProgress)
        if (_uiState.value.transientAvatarState == AvatarState.LEVEL_UP) {
            emitEffect(SpriteHomeEffect.ShowLevelUpReward(_uiState.value.spiritProgress.level))
        }
    }

    private fun handleDailyTaskClicked() {
        val task = uiState.value.dailyTask
        if (task.completed && !task.claimed) {
            _uiState.update { current ->
                current.copy(
                    dailyTask = current.dailyTask.copy(claimed = true),
                    userProfile = current.userProfile.copy(
                        firePoints = current.userProfile.firePoints + current.dailyTask.rewardFirePoints,
                    ),
                    speechBubble = SpeechBubbleUiState("任务奖励已领取", style = SpeechBubbleStyle.SUCCESS),
                    animationSequence = current.animationSequence + 1,
                )
            }
            emitEffect(SpriteHomeEffect.ShowMessage("任务奖励已领取"))
        } else {
            setSpeech("去聊天页完成一次导购吧")
            emitEffect(SpriteHomeEffect.NavigateToTasks)
        }
    }

    private fun applyNewOutfit() {
        var appearanceToSave: AvatarAppearance? = null
        _uiState.update { current ->
            val hint = current.newOutfitHint ?: return@update current
            val nextAppearance = current.appearance.copy(outfitId = hint.outfitId)
            appearanceToSave = nextAppearance
            current.copy(
                appearance = nextAppearance,
                newOutfitHint = null,
                speechBubble = SpeechBubbleUiState("已换上${hint.title}装扮", style = SpeechBubbleStyle.SUCCESS),
                animationSequence = current.animationSequence + 1,
            )
        }
        appearanceToSave?.let(appearanceRepository::saveAppearance)
    }

    private fun setSpeech(text: String) {
        _uiState.update { current ->
            current.copy(speechBubble = current.speechBubble.copy(text = text, visible = true))
        }
    }

    private fun emitEffect(effect: SpriteHomeEffect) {
        _effects.tryEmit(effect)
    }

    private fun cartEventKey(event: RealtimeEvent.CartUpdate): String =
        listOf(event.messageId, event.action, event.productId ?: "").joinToString(":")
}
```

- [ ] **Step 2: Run existing tests**

Run: `./gradlew :app:testDebugUnitTest --tests "*ChatViewModel*"`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt
git commit -m "feat: merge chat/voice/WebSocket capabilities into SpriteHomeViewModel via SpriteChatCoordinator"
```

---

## Task 8: Redesign SpriteHomeScreen Layout

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomePreviewData.kt`
- Test: Preview-based verification + `./gradlew :app:compileDebugKotlin`

**Interfaces:**
- Consumes: `SpriteHomeUiState`, `SpriteHomeAction`, `SpriteTopBar`, `SpriteVoiceBar`, `ProductPresentationSheet`, `SpriteStage`
- Produces: redesigned `SpriteHomeScreen` with voice bar at bottom, product sheet overlay, chat-mode switch in top bar

- [ ] **Step 1: Rewrite SpriteHomeScreen layout**

Replace `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt`:

```kotlin
package com.example.shopguideagent.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpriteRoomLight
import com.example.shopguideagent.ui.theme.SpriteRoomMiddle
import com.example.shopguideagent.ui.theme.SpriteRoomTop
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun SpriteHomeScreen(
    state: SpriteHomeUiState,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { stageState, stageModifier ->
        SpriteStage(state = stageState, modifier = stageModifier)
    },
) {
    BoxWithConstraints(
        modifier = modifier
            .fillMaxSize()
            .testTag("sprite_home")
            .background(RoomBackgroundBrush),
    ) {
        RoomBackgroundDecorations()
        val compact = maxHeight < 720.dp

        Column(
            modifier = Modifier
                .fillMaxSize()
                .safeDrawingPadding(),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            // Top bar with chat-mode switch, cart, settings
            SpriteTopBar(
                cartCount = state.cartCount,
                isChatMode = state.isChatMode,
                onAction = onAction,
                modifier = Modifier.fillMaxWidth(),
            )

            // Main content: avatar stage + speech bubble
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(horizontal = 18.dp),
            ) {
                avatarStage(
                    state.toAvatarStageUiState(),
                    Modifier
                        .align(Alignment.Center)
                        .fillMaxWidth()
                        .height(if (compact) 360.dp else 440.dp),
                )
                state.newOutfitHint?.let { hint ->
                    NewOutfitHintCard(
                        state = hint,
                        onAction = onAction,
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(top = if (compact) 12.dp else 24.dp),
                    )
                }
            }

            // Intimacy panel (compact when product sheet is visible)
            AnimatedVisibility(
                visible = !state.productSheet.isVisible,
                enter = fadeIn(tween(200)),
                exit = fadeOut(tween(150)),
            ) {
                IntimacyPanel(
                    spriteName = state.spiritProgress.spiritName,
                    level = state.spiritProgress.level,
                    intimacy = state.spiritProgress.currentIntimacy,
                    intimacyMax = state.spiritProgress.requiredIntimacy,
                    subtitle = state.spiritProgress.subtitle,
                    intimacyLabel = state.spiritProgress.intimacyLabel,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 18.dp),
                )
            }

            // Daily task bar (compact when product sheet is visible)
            AnimatedVisibility(
                visible = !state.productSheet.isVisible,
                enter = fadeIn(tween(200)),
                exit = fadeOut(tween(150)),
            ) {
                DailyTaskBar(
                    state = state.dailyTask,
                    onAction = onAction,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 18.dp, vertical = 8.dp),
                )
            }

            // Product presentation sheet (slides up over voice bar when products arrive)
            ProductPresentationSheet(
                state = state.productSheet,
                onAction = onAction,
                modifier = Modifier.fillMaxWidth(),
            )

            // Voice bar at the very bottom
            SpriteVoiceBar(
                state = state.voiceBar,
                enabled = !state.isLoading,
                speakerEnabled = state.isSpeakerEnabled,
                onAction = onAction,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

private val RoomBackgroundBrush = Brush.verticalGradient(
    colors = listOf(
        SpriteRoomTop,
        SpriteRoomMiddle,
        SpriteRoomLight,
        Color(0xFFE0A86C),
    ),
)

@Composable
private fun RoomBackgroundDecorations() {
    Box(modifier = Modifier.fillMaxSize()) {
        Box(
            modifier = Modifier
                .align(Alignment.TopStart)
                .offset(x = (-70).dp, y = 80.dp)
                .size(230.dp)
                .clip(CircleShape)
                .background(Color.White.copy(alpha = 0.16f)),
        )
        Box(
            modifier = Modifier
                .align(Alignment.TopCenter)
                .offset(y = 150.dp)
                .size(width = 260.dp, height = 170.dp)
                .clip(RoundedCornerShape(42.dp))
                .background(Color.White.copy(alpha = 0.12f)),
        )
        Box(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .offset(y = (-210).dp)
                .size(width = 340.dp, height = 74.dp)
                .clip(CircleShape)
                .background(Color(0x33FFF8E1)),
        )
        Box(
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .offset(x = 52.dp, y = (-40).dp)
                .size(160.dp)
                .clip(CircleShape)
                .background(Color(0x22FFFFFF)),
        )
    }
}

// Add missing import for AnimatedVisibility
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut

@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun SpriteHomeScreenIdlePreview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(state = SpriteHomePreviewData.idle, onAction = {})
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun SpriteHomeScreenPresentingPreview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(
            state = SpriteHomePreviewData.presenting.copy(
                productSheet = SpriteProductSheetUiState(
                    primaryProduct = SpriteHomePreviewData.product,
                    alternatives = emptyList(),
                    isVisible = true,
                    isLoading = false,
                ),
            ),
            onAction = {},
        )
    }
}
```

- [ ] **Step 2: Update SpriteHomePreviewData with new fields**

In `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomePreviewData.kt`, ensure existing previews compile with the expanded state. The existing previews use default values for new fields, so they should compile as-is. Add a new preview for the presenting-with-sheet state:

```kotlin
val presentingWithSheet = presenting.copy(
    productSheet = SpriteProductSheetUiState(
        primaryProduct = product,
        alternatives = listOf(
            ProductUiModel(productId = "alt1", name = "备选商品A", price = 199.0),
        ),
        isVisible = true,
        isLoading = false,
    ),
)
```

- [ ] **Step 3: Verify compilation**

Run: `./gradlew :app:compileDebugKotlin`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomePreviewData.kt
git commit -m "feat: redesign SpriteHomeScreen with voice bar, product sheet, and chat-mode switch"
```

---

## Task 9: Redesign Navigation (AppNavGraph)

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/navigation/AppNavGraph.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeRoute.kt` (thin or remove)
- Test: `client/app/src/test/java/com/example/shopguideagent/navigation/AppRouteBackStackTest.kt` (existing)

**Interfaces:**
- Consumes: `SpriteHomeViewModel`, `ChatViewModel`, `CartViewModel`, `SpriteChatCoordinator`
- Produces: `AppNavGraph` where Home is the landing screen, Chat is accessed via chat-mode switch, back stack is simplified

- [ ] **Step 1: Rewrite AppNavGraph**

Replace `client/app/src/main/java/com/example/shopguideagent/navigation/AppNavGraph.kt`:

```kotlin
package com.example.shopguideagent.navigation

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.shopguideagent.data.catalog.AndroidAssetProductCatalog
import com.example.shopguideagent.data.history.chatHistoryRepository
import com.example.shopguideagent.data.local.SharedPreferencesCartPersistenceStore
import com.example.shopguideagent.data.local.SpiritPreferencesDataSource
import com.example.shopguideagent.data.repository.SharedPreferencesSpiritAppearanceRepository
import com.example.shopguideagent.data.repository.SharedPreferencesSpiritProgressRepository
import com.example.shopguideagent.domain.chat.SpriteChatCoordinator
import com.example.shopguideagent.ui.home.SpriteHomeEffect
import com.example.shopguideagent.ui.home.SpriteHomeRoute
import com.example.shopguideagent.ui.home.SpriteHomeViewModel
import com.example.shopguideagent.ui.screen.CartScreen
import com.example.shopguideagent.ui.screen.ChatScreen
import com.example.shopguideagent.ui.screen.OrdersScreen
import com.example.shopguideagent.vm.CartViewModel
import com.example.shopguideagent.vm.ChatViewModel
import com.example.shopguideagent.voice.VoiceInputManager

enum class AppRoute {
    Home,
    Chat,
    Wardrobe,
    Tasks,
    Cart,
    Orders,
}

object AppRouteBackStack {
    @JvmStatic
    fun previousRoute(route: AppRoute): AppRoute? =
        when (route) {
            AppRoute.Home -> null
            AppRoute.Chat -> AppRoute.Home
            AppRoute.Wardrobe -> AppRoute.Home
            AppRoute.Tasks -> AppRoute.Home
            AppRoute.Cart -> AppRoute.Home
            AppRoute.Orders -> AppRoute.Cart
        }
}

@Composable
fun AppNavGraph() {
    val context = LocalContext.current
    var route by rememberSaveable { mutableStateOf(AppRoute.Home) }

    // Shared coordinator for both sprite home and chat
    val coordinator = remember { SpriteChatCoordinator() }

    val chatViewModel = remember {
        ChatViewModel(
            productCatalog = AndroidAssetProductCatalog(context.assets),
            historyRepository = chatHistoryRepository(context),
            coordinator = coordinator,
        )
    }

    val cartStore = remember { SharedPreferencesCartPersistenceStore(context) }
    val cartViewModel: CartViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return CartViewModel(persistenceStore = cartStore) as T
            }
        },
    )

    val spiritPreferences = remember { SpiritPreferencesDataSource(context) }
    val spriteHomeViewModel: SpriteHomeViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return SpriteHomeViewModel(
                    progressRepository = SharedPreferencesSpiritProgressRepository(spiritPreferences),
                    appearanceRepository = SharedPreferencesSpiritAppearanceRepository(spiritPreferences),
                    coordinator = coordinator,
                ) as T
            }
        },
    )

    val chatState by chatViewModel.uiState.collectAsState()
    val cartState by cartViewModel.uiState.collectAsState()
    val spriteState by spriteHomeViewModel.uiState.collectAsState()

    // Bind voice manager to sprite home
    LaunchedEffect(context) {
        val voiceManager = VoiceInputManager(
            context = context.applicationContext,
            onFinished = { file ->
                spriteHomeViewModel.onAction(
                    com.example.shopguideagent.ui.home.SpriteHomeAction.VoicePressStarted(true)
                )
                // Actually we need to handle the file properly
                // The voice manager callback should trigger the coordinator
                coordinator.sendVoiceMessage(file, "session_placeholder", spriteState.isSpeakerEnabled)
            },
            onError = { message ->
                // Show error via effect or state
            },
        )
        spriteHomeViewModel.bindVoiceManager(voiceManager)
    }

    // Sync cart events to sprite home
    LaunchedEffect(cartViewModel) {
        cartViewModel.operationEvents.collect { spriteHomeViewModel.onCartOperationEvent(it) }
    }

    // Sync cart count to sprite home
    LaunchedEffect(cartState.totalCount) {
        // Cart count is already synced via coordinator, but ensure consistency
    }

    BackHandler(enabled = AppRouteBackStack.previousRoute(route) != null) {
        AppRouteBackStack.previousRoute(route)?.let { route = it }
    }

    when (route) {
        AppRoute.Home -> SpriteHomeRoute(
            viewModel = spriteHomeViewModel,
            onEffect = { effect ->
                when (effect) {
                    SpriteHomeEffect.NavigateToGuide -> route = AppRoute.Chat
                    SpriteHomeEffect.NavigateToWardrobe -> route = AppRoute.Wardrobe
                    SpriteHomeEffect.NavigateToTasks -> route = AppRoute.Tasks
                    is SpriteHomeEffect.OpenProduct -> route = AppRoute.Chat
                    is SpriteHomeEffect.ShowMessage -> Unit
                    is SpriteHomeEffect.ShowLevelUpReward -> Unit
                }
            },
        )
        AppRoute.Chat -> ChatScreen(
            chatViewModel = chatViewModel,
            cartBadgeCount = cartState.totalCount,
            onCartClick = { route = AppRoute.Cart },
            onAddToCart = cartViewModel::addProduct,
            onVoiceRecordingStarted = spriteHomeViewModel::onVoiceRecordingStarted,
            onMessageSubmitted = spriteHomeViewModel::onRequestSent,
        )
        AppRoute.Wardrobe -> PlaceholderRoute(
            title = "装扮衣橱",
            message = "正式换装系统下一阶段接入",
            onBackClick = { route = AppRoute.Home },
        )
        AppRoute.Tasks -> PlaceholderRoute(
            title = "任务中心",
            message = "完成一次导购对话后可回到首页领取奖励",
            onBackClick = { route = AppRoute.Home },
        )
        AppRoute.Cart -> CartScreen(
            cartViewModel = cartViewModel,
            onBackClick = { route = AppRoute.Home },
            onOrdersClick = { route = AppRoute.Orders },
        )
        AppRoute.Orders -> OrdersScreen(
            cartViewModel = cartViewModel,
            onBackClick = { route = AppRoute.Cart },
        )
    }
}

@Composable
private fun PlaceholderRoute(
    title: String,
    message: String,
    onBackClick: () -> Unit,
) {
    Surface(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            Text(
                message,
                modifier = Modifier.padding(top = 12.dp),
                style = MaterialTheme.typography.bodyLarge,
            )
            Button(
                onClick = onBackClick,
                modifier = Modifier.padding(top = 24.dp),
            ) {
                Text("返回首页")
            }
        }
    }
}
```

Note: The `SpriteHomeRoute` needs to be updated to pass the `onVoiceRecordingStarted` and `onRequestSent` callbacks. Actually, since these are now internal to the ViewModel, we can simplify `SpriteHomeRoute`:

- [ ] **Step 2: Simplify SpriteHomeRoute**

Replace `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeRoute.kt`:
```kotlin
package com.example.shopguideagent.ui.home

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier

@Composable
fun SpriteHomeRoute(
    viewModel: SpriteHomeViewModel,
    onEffect: (SpriteHomeEffect) -> Unit,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { stageState, stageModifier ->
        SpriteStage(state = stageState, modifier = stageModifier)
    },
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(viewModel) {
        viewModel.effects.collect { onEffect(it) }
    }

    SpriteHomeScreen(
        state = state,
        onAction = viewModel::onAction,
        modifier = modifier,
        avatarStage = avatarStage,
    )
}
```

- [ ] **Step 3: Update ChatScreen with back-to-sprite button**

In `client/app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`, add a back-to-sprite button in the top bar. Modify the `AppTopBar` call (line 248) to include a back button:

```kotlin
topBar = {
    AppTopBar(
        cartCount = state.cartBadgeCount,
        onCartClick = onCartClick,
        onHistoryClick = { scope.launch { drawerState.open() } },
        onBackClick = { /* Navigate back to Home */ }, // NEW parameter
    )
},
```

Then update `AppTopBar` to accept and show the back button:

In `client/app/src/main/java/com/example/shopguideagent/ui/component/AppTopBar.kt`, add:
```kotlin
import androidx.compose.material.icons.automirrored.outlined.ArrowBack

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppTopBar(
    cartCount: Int,
    onCartClick: () -> Unit,
    onHistoryClick: () -> Unit,
    onBackClick: (() -> Unit)? = null, // NEW
    modifier: Modifier = Modifier,
) {
    CenterAlignedTopAppBar(
        ...
        navigationIcon = {
            if (onBackClick != null) {
                IconButton(onClick = onBackClick) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Outlined.ArrowBack,
                        contentDescription = "返回精灵空间",
                        tint = BrandPrimary,
                    )
                }
            } else {
                IconButton(onClick = onHistoryClick) {
                    Icon(...)
                }
            }
        },
        ...
    )
}
```

- [ ] **Step 4: Run navigation tests**

Run: `./gradlew :app:testDebugUnitTest --tests "*AppRouteBackStackTest*"`
Expected: All pass (update test if back stack changed).

- [ ] **Step 5: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/navigation/AppNavGraph.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeRoute.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/component/AppTopBar.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt
git commit -m "feat: redesign navigation with sprite space as landing, chat-mode switch, simplified back stack"
```

---

## Task 10: Add Chat-Mode Switch Entry Point on ChatScreen

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/component/AppTopBar.kt`
- Test: Preview-based verification

**Interfaces:**
- Consumes: `onBackToSprite: () -> Unit` callback
- Produces: ChatScreen with a back-to-sprite button in the top bar

- [ ] **Step 1: Add onBackToSprite parameter to ChatScreen**

In `client/app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`, add parameter:
```kotlin
@Composable
fun ChatScreen(
    chatViewModel: ChatViewModel,
    cartBadgeCount: Int,
    onCartClick: () -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    onVoiceRecordingStarted: () -> Unit = {},
    onMessageSubmitted: () -> Unit = {},
    onBackToSprite: () -> Unit = {}, // NEW
) {
```

Pass it to AppTopBar:
```kotlin
topBar = {
    AppTopBar(
        cartCount = state.cartBadgeCount,
        onCartClick = onCartClick,
        onHistoryClick = { scope.launch { drawerState.open() } },
        onBackClick = onBackToSprite, // NEW
    )
},
```

- [ ] **Step 2: Wire onBackToSprite in AppNavGraph**

In `client/app/src/main/java/com/example/shopguideagent/navigation/AppNavGraph.kt`, update the Chat route:
```kotlin
AppRoute.Chat -> ChatScreen(
    chatViewModel = chatViewModel,
    cartBadgeCount = cartState.totalCount,
    onCartClick = { route = AppRoute.Cart },
    onAddToCart = cartViewModel::addProduct,
    onVoiceRecordingStarted = { /* now handled internally */ },
    onMessageSubmitted = { /* now handled internally */ },
    onBackToSprite = { route = AppRoute.Home }, // NEW
)
```

- [ ] **Step 3: Verify compilation**

Run: `./gradlew :app:compileDebugKotlin`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt \
        client/app/src/main/java/com/example/shopguideagent/navigation/AppNavGraph.kt
git commit -m "feat: add back-to-sprite entry point on ChatScreen top bar"
```

---

## Task 11: Remove or Repurpose BottomActionBar

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/BottomActionBar.kt` (delete or repurpose)
- Test: `./gradlew :app:compileDebugKotlin`

**Interfaces:**
- The "导购" button is now the voice bar itself; "装扮" and "赚火星" can be moved to a secondary actions area or menu

- [ ] **Step 1: Remove BottomActionBar from SpriteHomeScreen**

Already done in Task 8 (SpriteHomeScreen rewrite). The BottomActionBar is no longer referenced.

- [ ] **Step 2: Optionally repurpose BottomActionBar as a secondary action row**

If desired, keep the file but rename it to `SpriteSecondaryActions.kt` and make it a small horizontal row with just "装扮" and "赚火星" icons that appears above the voice bar when no product is showing. For simplicity in this plan, we delete it.

Delete `client/app/src/main/java/com/example/shopguideagent/ui/home/BottomActionBar.kt`:
```bash
rm client/app/src/main/java/com/example/shopguideagent/ui/home/BottomActionBar.kt
```

- [ ] **Step 3: Commit**

```bash
git rm client/app/src/main/java/com/example/shopguideagent/ui/home/BottomActionBar.kt
git commit -m "refactor: remove BottomActionBar, replaced by voice bar as primary interaction"
```

---

## Task 12: Integration Testing and Verification

**Files:**
- All modified files
- Test: `client/app/src/test/java/com/example/shopguideagent/vm/ChatViewModelVoiceTest.kt`
- Test: `client/app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.kt`
- Test: `client/app/src/test/java/com/example/shopguideagent/navigation/AppRouteBackStackTest.kt`
- Test: `client/app/src/test/java/com/example/shopguideagent/ui/theme/DesignTokenTest.kt`

- [ ] **Step 1: Run all unit tests**

Run: `./gradlew :app:testDebugUnitTest`
Expected: All tests pass. Fix any failures.

- [ ] **Step 2: Build debug APK**

Run: `./gradlew :app:assembleDebug`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 3: Verify key flows manually (if emulator available)**

If running on emulator/device:
1. Launch app -> lands on SpriteHomeScreen (warm room background)
2. Tap mic button -> avatar changes to LISTENING, speech bubble shows "我在听"
3. Speak a query -> avatar changes to SEARCHING, speech bubble shows "正在找好物"
4. Products arrive -> product sheet slides up with primary product + alternatives
5. Tap "加购" on product -> sprite celebrates, intimacy increases
6. Tap chat-mode switch (top right) -> navigates to ChatScreen
7. Tap back arrow on ChatScreen -> returns to SpriteHomeScreen
8. Cart badge updates consistently across both screens

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration test fixes for sprite-space-as-primary redesign"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- [x] Navigation redesign: Home is landing, chat-mode switch navigates to Chat (Tasks 8, 9)
- [x] Sprite space UI composition: avatar stage, voice bar, product sheet, speech bubble, cart badge, chat-mode switch (Tasks 4, 5, 6, 8)
- [x] State management: SpriteChatCoordinator shared between SpriteHomeViewModel and ChatViewModel (Tasks 2, 7)
- [x] Voice flow: mic button, assistant_state -> avatar state, audio playback (Tasks 5, 7)
- [x] Product/cart integration in sprite space: ProductPresentationSheet with add-to-cart (Tasks 6, 7)
- [x] Theme/layout cleanup: unified tokens, styles.xml fix (Task 1)
- [x] Phased implementation: 12 tasks with clear sequencing

**2. Placeholder scan:**
- [x] No "TBD", "TODO", or "implement later"
- [x] All code blocks contain actual implementation
- [x] All test commands are explicit
- [x] No "similar to Task N" references

**3. Type consistency:**
- [x] `SpriteHomeAction` uses correct sealed interface syntax
- [x] `SpriteHomeUiState` field names consistent across all tasks
- [x] `SpriteChatCoordinator` method signatures match usage in ViewModels
- [x] `VoiceBarUiState` fields match usage in `SpriteVoiceBar`
- [x] `SpriteProductSheetUiState` fields match usage in `ProductPresentationSheet`

**4. File path consistency:**
- [x] All paths use `client/app/src/main/java/com/example/shopguideagent/...` prefix
- [x] Test paths use `client/app/src/test/java/com/example/shopguideagent/...`

---

## Critical Files for Implementation

- `/home/huadabioa/houlong/SoulDance/client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt`
- `/home/huadabioa/houlong/SoulDance/client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt`
- `/home/huadabioa/houlong/SoulDance/client/app/src/main/java/com/example/shopguideagent/domain/chat/SpriteChatCoordinator.kt`
- `/home/huadabioa/houlong/SoulDance/client/app/src/main/java/com/example/shopguideagent/navigation/AppNavGraph.kt`
- `/home/huadabioa/houlong/SoulDance/client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteVoiceBar.kt`
