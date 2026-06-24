package com.example.shopguideagent.data.remote

import com.example.shopguideagent.config.AppConfig
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

interface OrderApiService {
    @POST("/api/order/initiate")
    suspend fun initiate(@Body request: OrderInitiateRequest): OrderResponse

    @GET("/api/order/addresses")
    suspend fun getAddresses(): AddressListResponse

    @POST("/api/order/select_address")
    suspend fun selectAddress(@Body request: SelectAddressRequest): OrderResponse

    @POST("/api/order/confirm")
    suspend fun confirm(@Body request: OrderConfirmRequest): OrderResponse

    companion object {
        @Deprecated("Use create(userIdProvider) instead")
        fun create(): OrderApiService = create({ "demo_user_a" })

        fun create(userIdProvider: () -> String): OrderApiService {
            val httpClient = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .writeTimeout(20, TimeUnit.SECONDS)
                .addInterceptor(UserIdHeaderInterceptor(userIdProvider))
                .build()
            return Retrofit.Builder()
                .baseUrl(AppConfig.BASE_HTTP_URL)
                .client(httpClient)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(OrderApiService::class.java)
        }
    }
}

data class OrderInitiateRequest(val session_id: String)

data class SelectAddressRequest(val order_id: String, val address_id: String)

data class OrderConfirmRequest(
    val order_id: String,
    val confirmation_token: String,
    val idempotency_key: String,
)

data class AddressDto(
    val address_id: String,
    val name: String,
    val phone: String,
    val province: String,
    val city: String,
    val detail: String?,
    val is_default: Boolean?,
)

data class AddressListResponse(val addresses: List<AddressDto>?)

data class OrderResponse(
    val order_id: String?,
    val status: String?,
    val total_amount: Double?,
    val confirmation_token: String?,
    val message: String?,
)
