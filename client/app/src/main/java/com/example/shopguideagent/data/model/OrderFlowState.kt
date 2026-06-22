package com.example.shopguideagent.data.model

data class AddressUiModel(
    val addressId: String,
    val name: String,
    val phone: String,
    val province: String,
    val city: String,
    val detail: String,
    val isDefault: Boolean = false,
)

sealed class OrderFlowState {
    data object Idle : OrderFlowState()
    data object Creating : OrderFlowState()

    data class AddressRequired(
        val orderId: String,
        val addresses: List<AddressUiModel>,
        val isLoading: Boolean = false,
        val errorMessage: String? = null,
    ) : OrderFlowState()

    data class OrderPreview(
        val orderId: String,
        val confirmationToken: String,
        val idempotencyKey: String,
        val selectedAddress: AddressUiModel,
        val totalAmount: Double,
        val itemCount: Int,
        val isConfirming: Boolean = false,
    ) : OrderFlowState()

    data class OrderSuccess(val orderId: String, val message: String) : OrderFlowState()

    data class OrderError(val message: String) : OrderFlowState()
}
