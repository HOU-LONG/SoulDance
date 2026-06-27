package com.example.shopguideagent.data.history

import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.MessageRole
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ChatHistoryRepositoryTest {
    @Test
    fun `saves and loads per user`() = runTest {
        val store = InMemoryChatHistoryStore()
        val repoA = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })
        val repoB = ChatHistoryRepository(store, userIdProvider = { "demo_user_b" })

        repoA.saveSession("s1", "A session", listOf(
            ChatMessageUiModel("m1", MessageRole.User, "hello A")
        ))
        repoB.saveSession("s1", "B session", listOf(
            ChatMessageUiModel("m1", MessageRole.User, "hello B")
        ))

        assertEquals(1, repoA.state.value.sessions.size)
        assertEquals("hello A", repoA.state.value.sessions.first().messages.first().text)
        assertEquals(1, repoB.state.value.sessions.size)
        assertEquals("hello B", repoB.state.value.sessions.first().messages.first().text)
    }

    @Test
    fun `migrates legacy base64 format to json`() {
        val legacy = "current=czE=\nsession|czE=|QSBTZXNzaW9u|MTAwMA==\n"
        val store = InMemoryChatHistoryStore(legacy)
        val repo = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })
        assertEquals("s1", repo.state.value.currentSessionId)
    }

    @Test
    fun `saves and restores sessions from store`() {
        val store = InMemoryChatHistoryStore()
        val repository = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })

        val message = ChatMessageUiModel(
            "m1",
            MessageRole.User,
            "想买防晒",
            false,
            100L,
            0,
            emptyList(),
            null
        )
        repository.saveSession("s1", "防晒推荐", listOf(message), 200L)

        val restored = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })

        assertEquals(1, restored.state.value.sessions.size)
        assertEquals("s1", restored.state.value.currentSessionId)
        assertEquals("想买防晒", restored.state.value.sessions.first().messages.first().text)
    }

    @Test
    fun `deleteSession removes it from store and keeps current when possible`() {
        val store = InMemoryChatHistoryStore()
        val repository = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })
        val message = ChatMessageUiModel(
            "m1",
            MessageRole.User,
            "想买手机",
            false,
            100L,
            0,
            emptyList(),
            null
        )
        repository.saveSession("s1", "手机推荐", listOf(message), 100L)
        repository.saveSession("s2", "咖啡推荐", listOf(message), 200L)

        repository.deleteSession("s2")

        assertEquals(1, repository.state.value.sessions.size)
        assertEquals("s1", repository.state.value.currentSessionId)

        val restored = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })
        assertEquals(1, restored.state.value.sessions.size)
        assertEquals("s1", restored.state.value.currentSessionId)
    }

    @Test
    fun `delete last session clears current session id`() {
        val store = InMemoryChatHistoryStore()
        val repository = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })
        val message = ChatMessageUiModel(
            "m1",
            MessageRole.User,
            "想买手机",
            false,
            100L,
            0,
            emptyList(),
            null
        )
        repository.saveSession("s1", "手机推荐", listOf(message), 100L)

        repository.deleteSession("s1")

        assertEquals(0, repository.state.value.sessions.size)
        assertNull(repository.state.value.currentSessionId)
    }

    @Test
    fun `enforces 30 session cap by dropping oldest`() {
        val store = InMemoryChatHistoryStore()
        val repository = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })
        val message = ChatMessageUiModel("m1", MessageRole.User, "msg")

        // Create 31 sessions
        repeat(31) { i ->
            repository.saveSession("s$i", "Title $i", listOf(message), i * 1000L)
        }

        assertEquals(30, repository.state.value.sessions.size)
        // Oldest session (s0) should be dropped
        assertEquals(null, repository.state.value.sessions.find { it.sessionId == "s0" })
        // Newest session should still exist
        assertEquals("s30", repository.state.value.sessions.first().sessionId)
    }

    @Test
    fun `selectSession updates current session id`() {
        val store = InMemoryChatHistoryStore()
        val repository = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })
        val message = ChatMessageUiModel("m1", MessageRole.User, "msg")

        repository.saveSession("s1", "Title 1", listOf(message), 100L)
        repository.saveSession("s2", "Title 2", listOf(message), 200L)

        repository.selectSession("s1")

        assertEquals("s1", repository.state.value.currentSessionId)

        val restored = ChatHistoryRepository(store, userIdProvider = { "demo_user_a" })
        assertEquals("s1", restored.state.value.currentSessionId)
    }
}
