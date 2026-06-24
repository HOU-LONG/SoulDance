package com.example.shopguideagent.data.remote

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

class UserIdHeaderInterceptorTest {
    private lateinit var server: MockWebServer

    @Before fun setUp() { server = MockWebServer().apply { start() } }
    @After fun tearDown() { server.shutdown() }

    @Test
    fun `adds X-User-Id header from provider`() {
        server.enqueue(MockResponse().setBody("ok"))
        val client = OkHttpClient.Builder()
            .addInterceptor(UserIdHeaderInterceptor { "demo_user_b" })
            .build()
        client.newCall(Request.Builder().url(server.url("/")).build()).execute().close()
        val recorded = server.takeRequest()
        assertEquals("demo_user_b", recorded.getHeader("X-User-Id"))
    }

    @Test
    fun `does not overwrite an explicitly set header`() {
        server.enqueue(MockResponse().setBody("ok"))
        val client = OkHttpClient.Builder()
            .addInterceptor(UserIdHeaderInterceptor { "from_provider" })
            .build()
        val req = Request.Builder().url(server.url("/")).header("X-User-Id", "explicit").build()
        client.newCall(req).execute().close()
        assertEquals("explicit", server.takeRequest().getHeader("X-User-Id"))
    }
}
