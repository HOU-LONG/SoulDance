package com.example.shopguideagent.data.remote

import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class CartApiClientTest {
    @Test
    fun checkoutAcceptsBackendStatusOkResponse() = runTest {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    {
                      "status": "ok",
                      "order_id": "demo_order_session_1",
                      "paid_amount": 88.5,
                      "items": []
                    }
                    """.trimIndent(),
                ),
        )
        server.start()
        try {
            val service = Retrofit.Builder()
                .baseUrl(server.url("/"))
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(CartApiService::class.java)
            val client = CartApiClient(service)

            val result = client.checkout("session_1")

            assertNotNull(result)
            assertEquals("demo_order_session_1", result?.orderId)
            assertEquals(88.5, result?.paidAmount ?: 0.0, 0.001)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun checkoutThrowsBackendErrorDetail() = runTest {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setResponseCode(400)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail":"\u8d2d\u7269\u8f66\u4e3a\u7a7a\uff0c\u65e0\u6cd5\u7ed3\u7b97\u3002"}"""),
        )
        server.start()
        try {
            val service = Retrofit.Builder()
                .baseUrl(server.url("/"))
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(CartApiService::class.java)
            val client = CartApiClient(service)

            var error: IllegalStateException? = null
            try {
                client.checkout("empty_session")
            } catch (e: IllegalStateException) {
                error = e
            }

            assertNotNull(error)
            assertEquals("\u8d2d\u7269\u8f66\u4e3a\u7a7a\uff0c\u65e0\u6cd5\u7ed3\u7b97\u3002", error?.message)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun getCartThrowsBackendErrorDetail() = runTest {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setResponseCode(500)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"error":"cart backend unavailable"}"""),
        )
        server.start()
        try {
            val service = Retrofit.Builder()
                .baseUrl(server.url("/"))
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(CartApiService::class.java)
            val client = CartApiClient(service)

            var error: IllegalStateException? = null
            try {
                client.getCart("broken_session")
            } catch (e: IllegalStateException) {
                error = e
            }

            assertNotNull(error)
            assertEquals("cart backend unavailable", error?.message)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun addToCartThrowsBackendMessage() = runTest {
        val server = MockWebServer()
        server.enqueue(
            MockResponse()
                .setResponseCode(400)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"message":"unknown product"}"""),
        )
        server.start()
        try {
            val service = Retrofit.Builder()
                .baseUrl(server.url("/"))
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(CartApiService::class.java)
            val client = CartApiClient(service)

            var error: IllegalStateException? = null
            try {
                client.addToCart(
                    "session_1",
                    com.example.shopguideagent.data.model.ProductUiModel(
                        productId = "missing",
                        name = "Missing",
                        price = 1.0,
                    ),
                )
            } catch (e: IllegalStateException) {
                error = e
            }

            assertNotNull(error)
            assertEquals("unknown product", error?.message)
        } finally {
            server.shutdown()
        }
    }
}
