package com.example.shopguideagent.vm

import android.content.SharedPreferences
import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.catalog.ListProductCatalog
import com.example.shopguideagent.data.history.ChatHistoryRepository
import com.example.shopguideagent.data.history.InMemoryChatHistoryStore
import com.example.shopguideagent.data.model.RealtimeEvent
import com.example.shopguideagent.data.remote.LatestSessionResponse
import com.example.shopguideagent.data.remote.SessionDetailResponse
import com.example.shopguideagent.data.remote.SessionListResponse
import com.example.shopguideagent.data.remote.RealtimeChatWebSocketClient
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

class ChatViewModelSwitchTest {

    @Before
    fun setUp() {
        CoroutineTestHelper.setMainDispatcher()
    }

    @After
    fun tearDown() {
        CoroutineTestHelper.resetMainDispatcher()
    }

    @Test
    fun onUserSwitched_setsCurrentUserId_callsLatestApi_andReopensWebSocketWithNewSessionId() = runTest {
        val userSession = UserSession.create(fakePrefs())
        val fakeSessionsApi = FakeSessionsApi("new_session_123")
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
        assertEquals("demo_user_a", userSession.currentUserId.first())

        viewModel.onUserSwitched("demo_user_b")

        // (a) UserSession.setCurrentUserId was called with the new id (verified via observable state)
        assertEquals("demo_user_b", userSession.currentUserId.first())

        // (b) sessionsApi.getLatest() was called exactly once
        assertEquals(1, fakeSessionsApi.getLatestCallCount)

        // (c) WebSocket was closed and reopened, and active session id is the latest one
        assertEquals(1, fakeWebSocketClient.closeCount)
        assertTrue(
            "WebSocket should reconnect after switch (connectCount=${fakeWebSocketClient.connectCount})",
            fakeWebSocketClient.connectCount >= 1,
        )
        assertNotEquals(initialSessionId, viewModel.uiState.value.sessionId)
        assertEquals("new_session_123", viewModel.uiState.value.sessionId)
    }

    @Test
    fun onUserSwitched_sameUserId_noopsAndKeepsState() = runTest {
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

        // No API calls, no WebSocket churn, session id unchanged
        assertEquals(0, fakeSessionsApi.getLatestCallCount)
        assertEquals(0, fakeWebSocketClient.closeCount)
        assertEquals(initialSessionId, viewModel.uiState.value.sessionId)
        assertEquals("demo_user_a", userSession.currentUserId.first())
    }

    private class FakeSessionsApi(
        private val sessionIdToReturn: String,
    ) : SessionsApi {
        var getLatestCallCount: Int = 0
            private set

        override suspend fun getLatest(): LatestSessionResponse {
            getLatestCallCount++
            return LatestSessionResponse(session_id = sessionIdToReturn)
        }

        override suspend fun listSessions(): SessionListResponse = SessionListResponse(emptyList())

        override suspend fun getSession(sessionId: String): SessionDetailResponse =
            SessionDetailResponse(sessionId, "", "", emptyList())

        override suspend fun deleteSession(sessionId: String) {}
    }

    private class FakeRealtimeChatWebSocketClient : RealtimeChatWebSocketClient({ "demo_user_a" }) {
        var closeCount: Int = 0
            private set
        var connectCount: Int = 0
            private set
        var lastSessionIdSent: String? = null
            private set

        override fun connect(): Flow<RealtimeEvent> {
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
