package com.example.shopguideagent.domain.event

sealed interface CartOperationEvent {
    data class AddToCartSucceeded(
        val productId: String,
        val quantity: Int,
    ) : CartOperationEvent

    data class AddToCartFailed(
        val productId: String,
        val message: String,
    ) : CartOperationEvent
}
