package com.example.shopguideagent.data.remote

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query
import com.example.shopguideagent.config.AppConfig
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

interface CartApiService {

    @GET("/api/cart")
    suspend fun getCart(@Query("session_id") sessionId: String): CartResponse

    @POST("/api/cart/add")
    suspend fun addToCart(@Body request: AddToCartRequest): CartActionResponse

    @POST("/api/cart/add_bundle")
    suspend fun addBundle(@Body request: AddBundleRequest): CartActionResponse

    @POST("/api/cart/update_quantity")
    suspend fun updateQuantity(@Body request: UpdateQuantityRequest): CartActionResponse

    @POST("/api/cart/remove")
    suspend fun removeItem(@Body request: RemoveItemRequest): CartActionResponse

    @POST("/api/cart/select")
    suspend fun selectItem(@Body request: SelectItemRequest): CartActionResponse

    @POST("/api/cart/clear")
    suspend fun clearCart(@Body request: ClearCartRequest): CartActionResponse

    @POST("/api/cart/checkout")
    suspend fun checkout(@Body request: CheckoutRequest): CheckoutResponse

    companion object {
        @Deprecated("Use create(userIdProvider) instead")
        fun create(): CartApiService = create({ "demo_user_a" })

        fun create(userIdProvider: () -> String): CartApiService {
            val httpClient = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .writeTimeout(20, TimeUnit.SECONDS)
                .addInterceptor(UserIdHeaderInterceptor(userIdProvider))
                .build()
            val retrofit = Retrofit.Builder()
                .baseUrl(AppConfig.BASE_HTTP_URL)
                .client(httpClient)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
            return retrofit.create(CartApiService::class.java)
        }
    }
}

// Request DTOs
data class AddToCartRequest(
    val session_id: String,
    val product_id: String,
    val quantity: Int = 1,
)

data class AddBundleRequest(
    val session_id: String,
    val bundle_id: String,
)

data class UpdateQuantityRequest(
    val session_id: String,
    val product_id: String,
    val quantity: Int,
)

data class RemoveItemRequest(
    val session_id: String,
    val product_id: String,
)

data class SelectItemRequest(
    val session_id: String,
    val product_id: String,
    val selected: Boolean,
)

data class ClearCartRequest(
    val session_id: String,
)

data class CheckoutRequest(
    val session_id: String,
)

// Response DTOs
data class CartActionResponse(
    val success: Boolean? = null,
    val items: List<CartItemDto>?,
    val total: Double?,
    val total_amount: Double? = null,
    val message: String?,
)

data class CartResponse(
    val items: List<CartItemDto>?,
    val total: Double?,
    val total_amount: Double? = null,
)

data class CheckoutResponse(
    val success: Boolean? = null,
    val status: String? = null,
    val order_id: String?,
    val paid_amount: Double?,
    val message: String?,
)

data class CartItemDto(
    val product_id: String,
    val name: String,
    val price: Double,
    val quantity: Int,
    val selected: Boolean = true,
    val image_url: String? = null,
    val tags: List<String>? = null,
    val stock: Int? = null,
    val reason: String? = null,
)
