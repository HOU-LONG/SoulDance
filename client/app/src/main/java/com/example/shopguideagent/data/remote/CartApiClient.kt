package com.example.shopguideagent.data.remote

import com.example.shopguideagent.data.model.CartItemUiModel
import com.example.shopguideagent.data.model.CheckoutResult
import com.example.shopguideagent.data.model.ProductUiModel
import org.json.JSONObject
import retrofit2.HttpException

open class CartApiClient(private val service: CartApiService) {
    @Deprecated("Use constructor with service instead")
    constructor() : this(CartApiService.create())


    open suspend fun getCart(sessionId: String): List<CartItemUiModel> {
        val response = backendRequest { service.getCart(sessionId) }
        return response.items?.map { it.toUiModel() } ?: emptyList()
    }

    open suspend fun addToCart(sessionId: String, product: ProductUiModel, quantity: Int = 1): CartItemUiModel {
        val response = backendRequest {
            service.addToCart(AddToCartRequest(sessionId, product.productId, quantity))
        }.ensureSuccess()
        return response.items?.firstOrNull { it.product_id == product.productId }?.toUiModel()
            ?: CartItemUiModel(
                productId = product.productId,
                name = product.name,
                price = product.price,
                quantity = quantity,
                imageUrl = product.imageUrl,
                tags = product.tags,
                stock = product.stock,
                reason = product.reason,
            )
    }

    open suspend fun updateQuantity(sessionId: String, productId: String, quantity: Int): Boolean {
        return backendRequest {
            service.updateQuantity(UpdateQuantityRequest(sessionId, productId, quantity))
        }.ensureSuccess().success != false
    }

    open suspend fun removeItem(sessionId: String, productId: String): Boolean {
        return backendRequest {
            service.removeItem(RemoveItemRequest(sessionId, productId))
        }.ensureSuccess().success != false
    }

    open suspend fun selectItem(sessionId: String, productId: String, selected: Boolean): Boolean {
        return backendRequest {
            service.selectItem(SelectItemRequest(sessionId, productId, selected))
        }.ensureSuccess().success != false
    }

    open suspend fun clearCart(sessionId: String): Boolean {
        return backendRequest {
            service.clearCart(ClearCartRequest(sessionId))
        }.ensureSuccess().success != false
    }

    open suspend fun checkout(sessionId: String): CheckoutResult? {
        val response = backendRequest {
            service.checkout(CheckoutRequest(sessionId))
        }
        val ok = response.success == true || response.status == "ok"
        return if (ok && response.order_id != null && response.paid_amount != null) {
            CheckoutResult(
                orderId = response.order_id,
                paidAmount = response.paid_amount,
            )
        } else {
            response.message?.takeIf { it.isNotBlank() }?.let { throw IllegalStateException(it) }
            null
        }
    }

    private suspend fun <T> backendRequest(block: suspend () -> T): T =
        try {
            block()
        } catch (e: HttpException) {
            throw IllegalStateException(e.backendMessage() ?: e.message(), e)
        }

    private fun CartActionResponse.ensureSuccess(): CartActionResponse {
        if (success == false) {
            throw IllegalStateException(message?.takeIf { it.isNotBlank() } ?: "购物车操作失败")
        }
        return this
    }

    private fun HttpException.backendMessage(): String? {
        val body = response()?.errorBody()?.string()?.takeIf { it.isNotBlank() } ?: return null
        return runCatching {
            val json = JSONObject(body)
            json.optString("detail").takeIf { it.isNotBlank() }
                ?: json.optString("message").takeIf { it.isNotBlank() }
                ?: json.optString("error").takeIf { it.isNotBlank() }
        }.getOrNull() ?: body
    }

    private fun CartItemDto.toUiModel(): CartItemUiModel = CartItemUiModel(
        productId = product_id,
        name = name,
        price = price,
        quantity = quantity,
        selected = selected,
        imageUrl = image_url,
        tags = tags ?: emptyList(),
        stock = stock,
        reason = reason,
    )
}
