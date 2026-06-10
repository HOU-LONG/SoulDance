package com.example.shopguideagent.vm

import com.example.shopguideagent.data.catalog.ListProductCatalog
import com.example.shopguideagent.data.history.ChatHistoryRepository
import com.example.shopguideagent.data.history.InMemoryChatHistoryStore
import com.example.shopguideagent.data.model.MessageRole
import com.example.shopguideagent.data.model.RealtimeEvent
import com.example.shopguideagent.data.model.VoiceRecognitionState
import com.example.shopguideagent.data.remote.RealtimeChatWebSocketClient
import com.example.shopguideagent.data.remote.SpeechToTextClient
import com.example.shopguideagent.audio.StreamingAudioPlayer
import com.example.shopguideagent.test.CoroutineTestHelper
import kotlinx.coroutines.CompletableDeferred
import java.io.File
import java.io.IOException
import java.lang.reflect.Method
import java.net.SocketTimeoutException
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ChatViewModelVoiceTest {
    @Before
    fun setUp() {
        CoroutineTestHelper.setMainDispatcher()
    }

    @After
    fun tearDown() {
        CoroutineTestHelper.resetMainDispatcher()
    }

    @Test
    fun voiceTranscriptionSuccessAppendsUserMessageAndAssistantPlaceholder() {
        val viewModel = ChatViewModel(
            ListProductCatalog(emptyList()),
            ChatHistoryRepository(InMemoryChatHistoryStore("")),
            RealtimeChatWebSocketClient(),
            FakeSpeechToTextClient("voice transcript"),
        )
        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46))
        }

        viewModel.sendVoiceMessage(wav)

        val messages = viewModel.uiState.value.messages
        assertEquals(3, messages.size)
        assertEquals(MessageRole.User, messages[1].role)
        assertEquals("voice transcript", messages[1].text)
        assertEquals(MessageRole.Assistant, messages[2].role)
        assertEquals(VoiceRecognitionState.Succeeded, viewModel.uiState.value.voiceRecognitionState)
    }

    @Test
    fun voiceTranscriptionShowsTranscribingStateWhileWaitingForBackend() {
        val pendingResult = CompletableDeferred<Result<String>>()
        val viewModel = ChatViewModel(
            ListProductCatalog(emptyList()),
            ChatHistoryRepository(InMemoryChatHistoryStore("")),
            NoopRealtimeChatWebSocketClient(),
            DeferredSpeechToTextClient(pendingResult),
        )
        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46))
        }

        viewModel.sendVoiceMessage(wav)

        assertEquals(VoiceRecognitionState.Transcribing, viewModel.uiState.value.voiceRecognitionState)

        pendingResult.complete(Result.success("voice transcript"))
        assertEquals(VoiceRecognitionState.Succeeded, viewModel.uiState.value.voiceRecognitionState)
    }

    @Test
    fun emptyVoiceTranscriptionShowsEmptyStateAndDoesNotSendMessage() {
        val viewModel = ChatViewModel(
            ListProductCatalog(emptyList()),
            ChatHistoryRepository(InMemoryChatHistoryStore("")),
            NoopRealtimeChatWebSocketClient(),
            FakeSpeechToTextClient(Result.success("   ")),
        )
        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46))
        }

        viewModel.sendVoiceMessage(wav)

        assertEquals(VoiceRecognitionState.Empty, viewModel.uiState.value.voiceRecognitionState)
        assertEquals(1, viewModel.uiState.value.messages.size)
    }

    @Test
    fun failedVoiceTranscriptionShowsBackendReason() {
        val viewModel = ChatViewModel(
            ListProductCatalog(emptyList()),
            ChatHistoryRepository(InMemoryChatHistoryStore("")),
            NoopRealtimeChatWebSocketClient(),
            FakeSpeechToTextClient(Result.failure(IllegalStateException("STT is disabled"))),
        )
        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46))
        }

        viewModel.sendVoiceMessage(wav)

        assertEquals(VoiceRecognitionState.Failed, viewModel.uiState.value.voiceRecognitionState)
        assertTrue(viewModel.uiState.value.voiceRecognitionMessage.orEmpty().contains("STT is disabled"))
    }

    @Test
    fun timedOutVoiceTranscriptionShowsTimeoutState() {
        val viewModel = ChatViewModel(
            ListProductCatalog(emptyList()),
            ChatHistoryRepository(InMemoryChatHistoryStore("")),
            NoopRealtimeChatWebSocketClient(),
            FakeSpeechToTextClient(Result.failure(SocketTimeoutException("timeout"))),
        )
        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46))
        }

        viewModel.sendVoiceMessage(wav)

        assertEquals(VoiceRecognitionState.Timeout, viewModel.uiState.value.voiceRecognitionState)
        assertEquals("语音识别超时，请再试一次", viewModel.uiState.value.voiceRecognitionMessage)
        assertEquals("语音识别失败: 语音识别超时，请再试一次", viewModel.uiState.value.errorMessage)
    }

    @Test
    fun disconnectedVoiceTranscriptionDoesNotExposeRawTransportError() {
        val viewModel = ChatViewModel(
            ListProductCatalog(emptyList()),
            ChatHistoryRepository(InMemoryChatHistoryStore("")),
            NoopRealtimeChatWebSocketClient(),
            FakeSpeechToTextClient(Result.failure(IOException("connection closed"))),
        )
        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46))
        }

        viewModel.sendVoiceMessage(wav)

        assertEquals(VoiceRecognitionState.Failed, viewModel.uiState.value.voiceRecognitionState)
        assertEquals("语音识别连接中断，请再试一次", viewModel.uiState.value.voiceRecognitionMessage)
        assertEquals("语音识别失败: 语音识别连接中断，请再试一次", viewModel.uiState.value.errorMessage)
        assertFalse(viewModel.uiState.value.voiceRecognitionMessage.orEmpty().contains("connection closed"))
    }

    @Test
    fun newSessionResetsSpeakerEnabledForCurrentConversation() {
        val viewModel = ChatViewModel(
            ListProductCatalog(emptyList()),
            ChatHistoryRepository(InMemoryChatHistoryStore("")),
        )

        viewModel.setSpeakerEnabled(false)
        assertFalse(viewModel.uiState.value.isSpeakerEnabled)

        viewModel.newSession()

        assertTrue(viewModel.uiState.value.isSpeakerEnabled)
    }

    @Test
    fun mutedConversationDropsIncomingAudioDelta() {
        val audioPlayer = FakeAudioPlayer()
        val viewModel = ChatViewModel(
            ListProductCatalog(emptyList()),
            ChatHistoryRepository(InMemoryChatHistoryStore("")),
            audioPlayer = audioPlayer,
        )
        val handler: Method = ChatViewModel::class.java.getDeclaredMethod(
            "handleRealtimeEvent",
            RealtimeEvent::class.java,
        )
        handler.isAccessible = true

        viewModel.setSpeakerEnabled(false)
        handler.invoke(
            viewModel,
            RealtimeEvent.AudioDelta(
                messageId = "assistant_test",
                audioBase64 = "AQID",
                sampleRate = 16000,
            ),
        )

        assertEquals(1, audioPlayer.stopCount)
        assertEquals(0, audioPlayer.enqueuePcmCount)
    }

    private class FakeSpeechToTextClient(
        private val result: Result<String>,
    ) : SpeechToTextClient {
        constructor(text: String) : this(Result.success(text))

        override suspend fun transcribe(audioFile: File): Result<String> = result
    }

    private class DeferredSpeechToTextClient(
        private val result: CompletableDeferred<Result<String>>,
    ) : SpeechToTextClient {
        override suspend fun transcribe(audioFile: File): Result<String> = result.await()
    }

    private class NoopRealtimeChatWebSocketClient : RealtimeChatWebSocketClient() {
        override fun connect(): kotlinx.coroutines.flow.Flow<RealtimeEvent> = kotlinx.coroutines.flow.emptyFlow()

        override fun sendUserMessage(sessionId: String, message: String, ttsEnabled: Boolean): Boolean = true
    }

    private class FakeAudioPlayer : StreamingAudioPlayer() {
        var stopCount = 0
        var enqueuePcmCount = 0

        override fun enqueuePcm(chunk: ByteArray, sampleRate: Int) {
            enqueuePcmCount += 1
        }

        override fun stop() {
            stopCount += 1
        }
    }
}
