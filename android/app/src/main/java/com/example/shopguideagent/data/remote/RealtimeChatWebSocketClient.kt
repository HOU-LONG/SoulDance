package com.example.shopguideagent.data.remote

import com.example.shopguideagent.config.AppConfig
import com.example.shopguideagent.data.catalog.ProductImageUrlResolver
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.DerivedAttribute
import com.example.shopguideagent.data.model.ProductDerivedAttributes
import com.example.shopguideagent.data.model.QuickActionUiModel
import com.example.shopguideagent.data.model.RealtimeEvent
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.logging.HttpLoggingInterceptor
import org.json.JSONObject
import java.util.concurrent.TimeUnit

open class RealtimeChatWebSocketClient {

    private val client: OkHttpClient by lazy {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        OkHttpClient.Builder()
            .pingInterval(20, TimeUnit.SECONDS)
            .addInterceptor(logging)
            .build()
    }

    private var webSocket: WebSocket? = null

    open fun connect(): Flow<RealtimeEvent> = callbackFlow {
        val request = Request.Builder()
            .url("${AppConfig.BASE_WS_URL}${AppConfig.WS_CHAT_PATH}")
            .build()

        val listener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                // 连接成功，可发送初始心跳或认证
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val event = try {
                    parseEvent(text)
                } catch (e: Exception) {
                    RealtimeEvent.Unknown(text)
                }
                trySend(event)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                trySend(RealtimeEvent.Error(t.message ?: "WebSocket connection failed"))
                close()
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, reason)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                close()
            }
        }

        webSocket = client.newWebSocket(request, listener)

        awaitClose {
            webSocket?.cancel()
            webSocket = null
        }
    }

    open fun sendUserMessage(
        sessionId: String,
        message: String,
        ttsEnabled: Boolean,
    ): Boolean {
        val payload = JSONObject().apply {
            put("type", "user_message")
            put("session_id", sessionId)
            put("message", message)
            put("input_type", "text")
            put("tts_enabled", ttsEnabled)
            put("voice", "calm_female")
        }.toString()
        return webSocket?.send(payload) ?: false
    }

    open fun sendProductFollowup(
        sessionId: String,
        focusProductId: String,
        message: String,
        ttsEnabled: Boolean,
    ): Boolean {
        val payload = JSONObject().apply {
            put("type", "product_followup")
            put("session_id", sessionId)
            put("focus_product_id", focusProductId)
            put("message", message)
            put("tts_enabled", ttsEnabled)
            put("voice", "calm_female")
        }.toString()
        return webSocket?.send(payload) ?: false
    }

    open fun sendCartAction(
        sessionId: String,
        action: String,
        productId: String,
        quantity: Int = 1,
    ): Boolean {
        val payload = JSONObject().apply {
            put("type", "cart_action")
            put("session_id", sessionId)
            put("action", action)
            put("product_id", productId)
            put("quantity", quantity)
        }.toString()
        return webSocket?.send(payload) ?: false
    }

    open fun close() {
        webSocket?.close(1000, "Client closed")
        webSocket = null
    }

    private fun parseEvent(text: String): RealtimeEvent {
        val json = JSONObject(text)
        val type = json.optString("type")
        val messageId = json.optString("message_id", "")

        return when (type) {
            "text_delta" -> RealtimeEvent.TextDelta(
                messageId = messageId,
                text = json.optString("text"),
            )
            "products_start" -> RealtimeEvent.ProductsStart(
                messageId = messageId,
                expectedCount = json.optInt("expected_count", 0),
                title = json.optString("title").takeIf { it.isNotBlank() },
            )
            "product_item" -> {
                val product = parseProduct(json.getJSONObject("product"))
                RealtimeEvent.ProductItem(
                    messageId = messageId,
                    index = json.optInt("index", 0),
                    product = product,
                )
            }
            "products_done" -> RealtimeEvent.ProductsDone(messageId)
            "bundle_start" -> RealtimeEvent.BundleStart(
                messageId = messageId,
                title = json.optString("title").takeIf { it.isNotBlank() },
            )
            "bundle_item" -> {
                val product = parseProduct(json.getJSONObject("product"))
                RealtimeEvent.BundleItem(
                    messageId = messageId,
                    group = json.optString("group", ""),
                    product = product,
                )
            }
            "bundle_done" -> RealtimeEvent.BundleDone(messageId)
            "focus_text_delta" -> RealtimeEvent.FocusTextDelta(
                messageId = messageId,
                text = json.optString("text"),
            )
            "replacement_product" -> {
                val product = parseProduct(json.getJSONObject("product"))
                RealtimeEvent.ReplacementProduct(messageId, product)
            }
            "focus_done" -> RealtimeEvent.FocusDone(messageId)
            "audio_delta" -> RealtimeEvent.AudioDelta(
                messageId = messageId,
                audioBase64 = json.optString("audio_base64").takeIf { it.isNotBlank() }
                    ?: json.optString("data"),
                encoding = json.optString("encoding", "pcm_s16le"),
                sampleRate = json.optInt("sample_rate", 16000),
            )
            "audio_done" -> RealtimeEvent.AudioDone(messageId)
            "cart_update" -> RealtimeEvent.CartUpdate(
                messageId = messageId,
                badgeCount = parseCartBadgeCount(json),
                message = json.optString("message").takeIf { it.isNotBlank() },
                action = json.optString("action").takeIf { it.isNotBlank() },
                productId = json.optString("product_id").takeIf { it.isNotBlank() },
                success = json.optBoolean("success", true),
            )
            "quick_actions" -> RealtimeEvent.QuickActions(
                messageId = messageId,
                actions = parseQuickActions(json.optJSONArray("actions")),
            )
            "done" -> RealtimeEvent.Done(messageId.takeIf { it.isNotBlank() })
            "error" -> RealtimeEvent.Error(json.optString("message", "Unknown server error"))
            else -> RealtimeEvent.Unknown(text)
        }
    }

    private fun parseProduct(json: JSONObject): ProductUiModel {
        val derived = json.optJSONObject("derived_attributes")
        val rawImageUrl = json.optString("image_url").takeIf { it.isNotBlank() }
            ?: json.optString("main_image_url").takeIf { it.isNotBlank() }
        return ProductUiModel(
            productId = json.getString("product_id"),
            name = json.getString("name"),
            price = json.getDouble("price"),
            imageUrl = ProductImageUrlResolver.remoteUrl(
                imageUrl = rawImageUrl,
                baseHttpUrl = AppConfig.BASE_HTTP_URL,
            ),
            tags = json.optJSONArray("tags")?.let { arr ->
                (0 until arr.length()).map { arr.getString(it) }
            } ?: emptyList(),
            reason = json.optString("reason").takeIf { it.isNotBlank() },
            rating = json.optDouble("rating").takeIf { !it.isNaN() },
            stock = json.optInt("stock").takeIf { it != 0 },
            isPrimary = json.optBoolean("is_primary", false),
            derivedAttributes = derived?.let { parseDerivedAttributes(it) } ?: ProductDerivedAttributes(),
            positiveFeedbackSummary = json.optJSONArray("positive_feedback_summary")?.let { arr ->
                (0 until arr.length()).map { arr.getString(it) }
            } ?: emptyList(),
            negativeFeedbackSummary = json.optJSONArray("negative_feedback_summary")?.let { arr ->
                (0 until arr.length()).map { arr.getString(it) }
            } ?: emptyList(),
            riskTags = json.optJSONArray("risk_tags")?.let { arr ->
                (0 until arr.length()).map { arr.getString(it) }
            } ?: emptyList(),
        )
    }

    private fun parseCartBadgeCount(json: JSONObject): Int {
        if (json.has("badge_count")) return json.optInt("badge_count", 0)
        val items = json.optJSONObject("cart")?.optJSONArray("items") ?: return 0
        return (0 until items.length()).sumOf { index ->
            items.optJSONObject(index)?.optInt("quantity", 0) ?: 0
        }
    }

    private fun parseQuickActions(arr: org.json.JSONArray?): List<QuickActionUiModel> {
        if (arr == null) return emptyList()
        return (0 until arr.length()).mapNotNull { index ->
            val item = arr.opt(index)
            when (item) {
                is JSONObject -> {
                    val label = item.optString("label").trim()
                    val message = item.optString("message", label).trim()
                    if (label.isBlank() && message.isBlank()) {
                        null
                    } else {
                        QuickActionUiModel(
                            label = label.ifBlank { message },
                            message = message.ifBlank { label },
                        )
                    }
                }
                is String -> item.trim().takeIf { it.isNotBlank() }?.let { QuickActionUiModel(it) }
                else -> null
            }
        }
    }

    private fun parseDerivedAttributes(json: JSONObject): ProductDerivedAttributes {
        return ProductDerivedAttributes(
            effects = parseAttributeList(json.optJSONArray("effects")),
            suitableFor = parseAttributeList(json.optJSONArray("suitable_for")),
            notRecommendedFor = parseAttributeList(json.optJSONArray("not_recommended_for")),
            skinTypes = parseAttributeList(json.optJSONArray("skin_types")),
            ingredients = parseAttributeList(json.optJSONArray("ingredients")),
            usageScene = parseAttributeList(json.optJSONArray("usage_scene")),
            cautions = parseAttributeList(json.optJSONArray("cautions")),
            sellingPoints = parseAttributeList(json.optJSONArray("selling_points")),
            generatedTags = parseAttributeList(json.optJSONArray("generated_tags")),
        )
    }

    private fun parseAttributeList(arr: org.json.JSONArray?): List<DerivedAttribute> {
        if (arr == null) return emptyList()
        return (0 until arr.length()).mapNotNull {
            val obj = arr.optJSONObject(it) ?: return@mapNotNull null
            DerivedAttribute(
                value = obj.optString("value", ""),
                evidence = obj.optString("evidence", ""),
                confidence = obj.optDouble("confidence", 0.0),
            )
        }
    }
}
