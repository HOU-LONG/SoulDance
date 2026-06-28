package com.example.shopguideagent.data.remote

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Test

class SessionsApiClientTest {
    @Test
    fun `list sends X-User-Id`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("""{"sessions":[]}"""))
        server.start()

        val service = SessionsApiService.create({ "demo_user_b" }, baseUrl = server.url("/").toString())
        val client = SessionsApiClient(service)
        client.listSessions()

        val request = server.takeRequest()
        assertEquals("demo_user_b", request.getHeader("X-User-Id"))
        server.shutdown()
    }

    @Test
    fun `get session sends X-User-Id`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(
            MockResponse().setBody(
                """{"session_id":"s1","title":"t","updated_at":"","messages":[]}"""
            )
        )
        server.start()

        val service = SessionsApiService.create({ "demo_user_c" }, baseUrl = server.url("/").toString())
        val client = SessionsApiClient(service)
        client.getSession("s1")

        val request = server.takeRequest()
        assertEquals("demo_user_c", request.getHeader("X-User-Id"))
        assertEquals("/api/sessions/s1", request.path)
        server.shutdown()
    }

    @Test
    fun `delete session sends X-User-Id`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse())
        server.start()

        val service = SessionsApiService.create({ "demo_user_a" }, baseUrl = server.url("/").toString())
        val client = SessionsApiClient(service)
        client.deleteSession("s1")

        val request = server.takeRequest()
        assertEquals("demo_user_a", request.getHeader("X-User-Id"))
        assertEquals("DELETE", request.method)
        assertEquals("/api/sessions/s1", request.path)
        server.shutdown()
    }
}
