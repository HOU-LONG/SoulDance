package com.example.shopguideagent.data.model

sealed class RealtimeEvent {
    data class TextDelta(val messageId: String, val text: String) : RealtimeEvent()
    data class Done(val messageId: String?) : RealtimeEvent()
    data class Error(val message: String) : RealtimeEvent()
    data class ProductsStart(
        val messageId: String,
        val expectedCount: Int,
        val title: String?,
    ) : RealtimeEvent()
    data class ProductsDone(val messageId: String) : RealtimeEvent()
    data class ProductItem(
        val messageId: String,
        val index: Int,
        val product: ProductUiModel,
    ) : RealtimeEvent()
    data class BundleStart(val messageId: String, val title: String?) : RealtimeEvent()
    data class BundleItem(
        val messageId: String,
        val group: String,
        val product: ProductUiModel,
    ) : RealtimeEvent()
    data class BundleDone(val messageId: String) : RealtimeEvent()
    data class ComparisonResult(
        val messageId: String,
        val items: List<ProductUiModel>,
        val winnerId: String?,
        val reason: String?,
    ) : RealtimeEvent()
    data class FocusTextDelta(val messageId: String, val text: String) : RealtimeEvent()
    data class ReplacementProduct(
        val messageId: String,
        val product: ProductUiModel,
    ) : RealtimeEvent()
    data class FocusDone(val messageId: String) : RealtimeEvent()
    data class AudioDelta(
        val messageId: String,
        val audioBase64: String,
        val encoding: String = "pcm_s16le",
        val sampleRate: Int = 16000,
    ) : RealtimeEvent()
    data class AudioDone(val messageId: String) : RealtimeEvent()
    data class CartUpdate(
        val messageId: String,
        val badgeCount: Int,
        val message: String? = null,
        val action: String? = null,
        val productId: String? = null,
        val success: Boolean = true,
    ) : RealtimeEvent() {
        constructor(
            messageId: String,
            badgeCount: Int,
            message: String?,
            action: String?,
            productId: String?,
        ) : this(messageId, badgeCount, message, action, productId, true)
    }
    data class QuickActions(
        val messageId: String,
        val actions: List<QuickActionUiModel>,
    ) : RealtimeEvent()
    data class Ack(
        val messageId: String?,
        val traceId: String?,
        val seq: Int,
    ) : RealtimeEvent()
    data class Unknown(val raw: String) : RealtimeEvent()
}
