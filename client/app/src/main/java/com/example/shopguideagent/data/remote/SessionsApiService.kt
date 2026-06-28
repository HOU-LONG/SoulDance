package com.example.shopguideagent.data.remote

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Path
import com.example.shopguideagent.config.AppConfig
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

interface SessionsApiService {

    @GET("/api/sessions/latest")
    suspend fun getLatest(): LatestSessionResponse

    @GET("/api/sessions")
    suspend fun listSessions(): SessionListResponse

    @GET("/api/sessions/{session_id}")
    suspend fun getSession(@Path("session_id") sessionId: String): SessionDetailResponse

    @DELETE("/api/sessions/{session_id}")
    suspend fun deleteSession(@Path("session_id") sessionId: String)

    companion object {
        fun create(
            userIdProvider: () -> String,
            baseUrl: String = AppConfig.BASE_HTTP_URL,
        ): SessionsApiService {
            val httpClient = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .writeTimeout(20, TimeUnit.SECONDS)
                .addInterceptor(UserIdHeaderInterceptor(userIdProvider))
                .build()
            val retrofit = Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(httpClient)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
            return retrofit.create(SessionsApiService::class.java)
        }
    }
}

data class LatestSessionResponse(
    val session_id: String,
)

data class SessionListResponse(
    val sessions: List<SessionSummaryDto>,
)

data class SessionSummaryDto(
    val session_id: String,
    val title: String,
    val updated_at: String,
    val message_count: Int,
    val preview: String,
)

data class SessionDetailResponse(
    val session_id: String,
    val title: String,
    val updated_at: String,
    val messages: List<RemoteDisplayMessageDto>,
)

data class RemoteDisplayMessageDto(
    val id: String,
    val role: String,
    val text: String,
    val created_at: String,
    val products: List<RemoteProductDto>?,
    val quick_actions: List<RemoteQuickActionDto>?,
)

data class RemoteProductDto(
    val product_id: String,
    val name: String,
    val brand: String,
    val price: Double,
    val image_url: String,
)

data class RemoteQuickActionDto(
    val label: String,
    val action: String,
)
