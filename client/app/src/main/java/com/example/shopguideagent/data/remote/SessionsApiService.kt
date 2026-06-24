package com.example.shopguideagent.data.remote

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import com.example.shopguideagent.config.AppConfig
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

interface SessionsApiService {

    @GET("/api/sessions/latest")
    suspend fun getLatest(): LatestSessionResponse

    companion object {
        @Deprecated("Use create(userIdProvider) instead")
        fun create(): SessionsApiService = create({ "demo_user_a" })

        fun create(userIdProvider: () -> String): SessionsApiService {
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
            return retrofit.create(SessionsApiService::class.java)
        }
    }
}

data class LatestSessionResponse(
    val session_id: String,
)
