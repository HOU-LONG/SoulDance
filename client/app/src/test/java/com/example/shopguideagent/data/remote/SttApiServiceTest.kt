package com.example.shopguideagent.data.remote

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class SttApiServiceTest {
    @Test
    fun transcribePostsAudioMultipartFieldToSttEndpoint() = runBlocking {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"text":"推荐防晒霜"}"""),
        )
        server.start()

        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0))
        }

        try {
            val service = SttApiService(
                baseHttpUrl = server.url("/").toString().trimEnd('/'),
            )

            val result = service.transcribe(wav)
            val request = server.takeRequest()
            val body = request.body.readUtf8()

            assertTrue(result.isSuccess)
            assertEquals("推荐防晒霜", result.getOrThrow())
            assertEquals("/api/stt", request.path)
            assertTrue(body.contains("name=\"audio\""))
            assertFalse(body.contains("name=\"file\""))
        } finally {
            wav.delete()
            server.shutdown()
        }
    }

    @Test
    fun transcribeFailureUsesBackendDetailMessage() = runBlocking {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setResponseCode(503)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail":"STT is disabled"}"""),
        )
        server.start()

        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0))
        }

        try {
            val service = SttApiService(
                baseHttpUrl = server.url("/").toString().trimEnd('/'),
            )

            val result = service.transcribe(wav)

            assertTrue(result.isFailure)
            assertEquals("STT is disabled", result.exceptionOrNull()?.message)
        } finally {
            wav.delete()
            server.shutdown()
        }
    }

    @Test
    fun transcribeDisconnectRetriesOnceAndCanSucceed() = runBlocking {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setSocketPolicy(SocketPolicy.DISCONNECT_AT_START),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"text":"我要一瓶东鹏特饮"}"""),
        )
        server.start()

        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0))
        }

        try {
            val service = SttApiService(
                baseHttpUrl = server.url("/").toString().trimEnd('/'),
            )

            val result = service.transcribe(wav)

            assertTrue(result.isSuccess)
            assertEquals("我要一瓶东鹏特饮", result.getOrThrow())
            assertEquals(2, server.requestCount)
        } finally {
            wav.delete()
            server.shutdown()
        }
    }

    @Test
    fun transcribeRepeatedDisconnectReturnsFriendlyChineseMessage() = runBlocking {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setSocketPolicy(SocketPolicy.DISCONNECT_AT_START),
        )
        server.enqueue(
            MockResponse()
                .setSocketPolicy(SocketPolicy.DISCONNECT_AT_START),
        )
        server.start()

        val wav = File.createTempFile("voice-test", ".wav").apply {
            writeBytes(byteArrayOf(0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0))
        }

        try {
            val service = SttApiService(
                baseHttpUrl = server.url("/").toString().trimEnd('/'),
            )

            val result = service.transcribe(wav)

            assertTrue(result.isFailure)
            assertEquals("语音识别连接中断，请再试一次", result.exceptionOrNull()?.message)
        } finally {
            wav.delete()
            server.shutdown()
        }
    }
}
