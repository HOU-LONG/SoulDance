package com.example.shopguideagent.data.remote

import com.example.shopguideagent.data.model.AddressUiModel
import org.json.JSONObject
import retrofit2.HttpException

open class OrderApiClient(private val service: OrderApiService) {
    @Deprecated("Use constructor with service instead")
    constructor() : this(OrderApiService.create())

    open suspend fun initiate(sessionId: String): Result<OrderResponse> = runCatching {
        backendRequest { service.initiate(OrderInitiateRequest(sessionId)) }
    }

    open suspend fun getAddresses(): Result<List<AddressUiModel>> = runCatching {
        backendRequest { service.getAddresses() }.addresses?.map { it.toUiModel() } ?: emptyList()
    }

    open suspend fun selectAddress(orderId: String, addressId: String): Result<OrderResponse> = runCatching {
        backendRequest { service.selectAddress(SelectAddressRequest(orderId, addressId)) }
    }

    open suspend fun confirm(
        orderId: String,
        token: String,
        idempotencyKey: String,
    ): Result<OrderResponse> = runCatching {
        backendRequest { service.confirm(OrderConfirmRequest(orderId, token, idempotencyKey)) }
    }

    private suspend fun <T> backendRequest(block: suspend () -> T): T =
        try {
            block()
        } catch (e: HttpException) {
            throw IllegalStateException(e.backendMessage() ?: e.message(), e)
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

    private fun AddressDto.toUiModel() = AddressUiModel(
        addressId = address_id,
        name = name,
        phone = phone,
        province = province,
        city = city,
        detail = detail ?: "",
        isDefault = is_default ?: false,
    )
}
