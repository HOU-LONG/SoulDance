package com.example.shopguideagent.vm

import android.content.SharedPreferences
import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.catalog.ListProductCatalog
import com.example.shopguideagent.data.history.ChatHistoryRepository
import com.example.shopguideagent.data.history.InMemoryChatHistoryStore
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.MessageRole
import com.example.shopguideagent.data.remote.LatestSessionResponse
import com.example.shopguideagent.data.remote.RealtimeChatWebSocketClient
import com.example.shopguideagent.data.remote.RemoteDisplayMessageDto
import com.example.shopguideagent.data.remote.RemoteProductDto
import com.example.shopguideagent.data.remote.SessionDetailResponse
import com.example.shopguideagent.data.remote.SessionListResponse
import com.example.shopguideagent.data.remote.SessionsApi
import com.example.shopguideagent.test.CoroutineTestHelper
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ChatViewModelUserSwitchTest {

    @Before
    fun setUp() {
        CoroutineTestHelper.setMainDispatcher()
    }

    @After
    fun tearDown() {
        CoroutineTestHelper.resetMainDispatcher()
    }

    @Test
    fun `onUserSwitched loads new user history and resets UI`() = runTest {
        val store = InMemoryChatHistoryStore()
        val userSession = UserSession.create(fakePrefs())
        userSession.setCurrentUserId("demo_user_a")

        val historyRepo = ChatHistoryRepository(store, userIdProvider = { userSession.currentUserId.value })
        historyRepo.saveSession("sa", "Session A", listOf(
            ChatMessageUiModel(id = "m1", role = MessageRole.User, text = "Hello A"),
        ))

        val fakeSessionsApi = FakeSessionsApi(
            latestSessionId = "new_session_123",
            sessionDetail = SessionDetailResponse(
                session_id = "new_session_123",
                title = "Backend Session",
                updated_at = "",
                messages = listOf(
                    RemoteDisplayMessageDto(
                        id = "bm1",
                        role = "assistant",
                        text = "Backend welcome",
                        created_at = "",
                        products = null,
                        quick_actions = null,
                    ),
                ),
            ),
        )
        val fakeWebSocketClient = FakeRealtimeChatWebSocketClient()

        val viewModel = ChatViewModel(
            productCatalog = ListProductCatalog(emptyList()),
            historyRepository = historyRepo,
            wsClient = fakeWebSocketClient,
            userSession = userSession,
            sessionsApi = fakeSessionsApi,
            userIdProvider = { userSession.currentUserId.value },
        )
        val initialSessionId = viewModel.uiState.value.sessionId
        assertEquals("demo_user_a", userSession.currentUserId.first())

        // Pre-set a cart badge so we can verify it resets
        viewModel.updateCartBadge(5)
        assertEquals(5, viewModel.uiState.value.cartBadgeCount)

        viewModel.onUserSwitched("demo_user_b")

        // (a) UserSession updated
        assertEquals("demo_user_b", userSession.currentUserId.first())

        // (b) sessionsApi.getLatest() called once
        assertEquals(1, fakeSessionsApi.getLatestCallCount)

        // (c) WebSocket closed and reopened
        assertEquals(1, fakeWebSocketClient.closeCount)
        assertTrue(
            "WebSocket should reconnect after switch (connectCount=${fakeWebSocketClient.connectCount})",
            fakeWebSocketClient.connectCount >= 1,
        )

        // (d) Session id changed to latest from backend
        assertNotEquals(initialSessionId, viewModel.uiState.value.sessionId)
        assertEquals("new_session_123", viewModel.uiState.value.sessionId)

        // (e) UI reset: cart badge cleared to 0
        assertEquals(0, viewModel.uiState.value.cartBadgeCount)

        // (f) Backend messages loaded (non-empty) instead of welcome
        val messages = viewModel.uiState.value.messages
        assertEquals(1, messages.size)
        assertEquals("Backend welcome", messages.first().text)
        assertEquals(MessageRole.Assistant, messages.first().role)
    }

    @Test
    fun `onUserSwitched falls back to local session when backend empty`() = runTest {
        val store = InMemoryChatHistoryStore()
        val userSession = UserSession.create(fakePrefs())
        userSession.setCurrentUserId("demo_user_a")

        val historyRepo = ChatHistoryRepository(store, userIdProvider = { userSession.currentUserId.value })
        historyRepo.saveSession("sa", "Session A", listOf(
            ChatMessageUiModel(id = "m1", role = MessageRole.User, text = "Hello A"),
        ))

        val fakeSessionsApi = FakeSessionsApi(
            latestSessionId = "fallback_session",
            sessionDetail = SessionDetailResponse(
                session_id = "fallback_session",
                title = "Empty",
                updated_at = "",
                messages = emptyList(),
            ),
        )
        val fakeWebSocketClient = FakeRealtimeChatWebSocketClient()

        val viewModel = ChatViewModel(
            productCatalog = ListProductCatalog(emptyList()),
            historyRepository = historyRepo,
            wsClient = fakeWebSocketClient,
            userSession = userSession,
            sessionsApi = fakeSessionsApi,
            userIdProvider = { userSession.currentUserId.value },
        )

        viewModel.onUserSwitched("demo_user_b")

        // Because backend messages are empty, should fall back to local welcome (no local history for B)
        val messages = viewModel.uiState.value.messages
        assertEquals(1, messages.size)
        assertEquals(MessageRole.Assistant, messages.first().role)
        assertTrue(messages.first().text.contains("智能导购助手"))
    }

    @Test
    fun `onUserSwitched same user noops`() = runTest {
        val userSession = UserSession.create(fakePrefs())
        val fakeSessionsApi = FakeSessionsApi("ignored_session")
        val fakeWebSocketClient = FakeRealtimeChatWebSocketClient()
        val viewModel = ChatViewModel(
            productCatalog = ListProductCatalog(emptyList()),
            historyRepository = ChatHistoryRepository(InMemoryChatHistoryStore(), userIdProvider = { "demo_user_a" }),
            wsClient = fakeWebSocketClient,
            userSession = userSession,
            sessionsApi = fakeSessionsApi,
            userIdProvider = { userSession.currentUserId.value },
        )
        val initialSessionId = viewModel.uiState.value.sessionId

        viewModel.onUserSwitched("demo_user_a")

        assertEquals(0, fakeSessionsApi.getLatestCallCount)
        assertEquals(0, fakeWebSocketClient.closeCount)
        assertEquals(initialSessionId, viewModel.uiState.value.sessionId)
        assertEquals("demo_user_a", userSession.currentUserId.first())
    }

    private class FakeSessionsApi(
        private val latestSessionId: String,
        private val sessionDetail: SessionDetailResponse = SessionDetailResponse("", "", "", emptyList()),
    ) : SessionsApi {
        var getLatestCallCount: Int = 0
            private set
        var getSessionCallCount: Int = 0
            private set

        override suspend fun getLatest(): LatestSessionResponse {
            getLatestCallCount++
            return LatestSessionResponse(session_id = latestSessionId)
        }

        override suspend fun listSessions(): SessionListResponse = SessionListResponse(emptyList())

        override suspend fun getSession(sessionId: String): SessionDetailResponse {
            getSessionCallCount++
            return sessionDetail
        }

        override suspend fun deleteSession(sessionId: String) {}
    }

    private class FakeRealtimeChatWebSocketClient : RealtimeChatWebSocketClient({ "demo_user_a" }) {
        var closeCount: Int = 0
            private set
        var connectCount: Int = 0
            private set
        var lastSessionIdSent: String? = null
            private set

        override fun connect(): Flow<com.example.shopguideagent.data.model.RealtimeEvent> {
            connectCount++
            return emptyFlow()
        }

        override fun sendUserMessage(sessionId: String, message: String, ttsEnabled: Boolean): Boolean {
            lastSessionIdSent = sessionId
            return true
        }

        override fun close() {
            closeCount++
        }
    }

    private fun fakePrefs(): SharedPreferences {
        return object : SharedPreferences {
            private val store = mutableMapOf<String, Any?>()

            override fun getAll(): MutableMap<String, *> = store.toMutableMap()
            override fun getString(key: String?, defValue: String?): String? =
                store[key] as? String? ?: defValue
            override fun getStringSet(key: String?, defValues: MutableSet<String>?): MutableSet<String>? =
                @Suppress("UNCHECKED_CAST") (store[key] as? MutableSet<String>? ?: defValues)
            override fun getInt(key: String?, defValue: Int): Int = store[key] as? Int ?: defValue
            override fun getLong(key: String?, defValue: Long): Long = store[key] as? Long ?: defValue
            override fun getFloat(key: String?, defValue: Float): Float = store[key] as? Float ?: defValue
            override fun getBoolean(key: String?, defValue: Boolean): Boolean =
                store[key] as? Boolean ?: defValue
            override fun contains(key: String?): Boolean = store.containsKey(key)
            override fun edit(): SharedPreferences.Editor = object : SharedPreferences.Editor {
                override fun putString(key: String?, value: String?): SharedPreferences.Editor {
                    if (key != null) store[key] = value
                    return this
                }
                override fun putStringSet(key: String?, values: MutableSet<String>?): SharedPreferences.Editor {
                    if (key != null) store[key] = values
                    return this
                }
                override fun putInt(key: String?, value: Int): SharedPreferences.Editor {
                    if (key != null) store[key] = value
                    return this
                }
                override fun putLong(key: String?, value: Long): SharedPreferences.Editor {
                    if (key != null) store[key] = value
                    return this
                }
                override fun putFloat(key: String?, value: Float): SharedPreferences.Editor {
                    if (key != null) store[key] = value
                    return this
                }
                override fun putBoolean(key: String?, value: Boolean): SharedPreferences.Editor {
                    if (key != null) store[key] = value
                    return this
                }
                override fun remove(key: String?): SharedPreferences.Editor {
                    if (key != null) store.remove(key)
                    return this
                }
                override fun clear(): SharedPreferences.Editor {
                    store.clear()
                    return this
                }
                override fun commit(): Boolean = true
                override fun apply() {}
            }
            override fun registerOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}
            override fun unregisterOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}
        }
    }
}
