package com.example.shopguideagent.data.remote

/**
 * Sessions API 抽象接口，便于在测试中替换实现。
 */
interface SessionsApi {
    suspend fun getLatest(): LatestSessionResponse
}

/**
 * 基于 Retrofit 的默认实现。
 */
class SessionsApiClient(
    private val service: SessionsApiService = SessionsApiService.create(),
) : SessionsApi {
    @Deprecated("Use constructor with service that includes userIdProvider")
    constructor() : this(SessionsApiService.create())

    override suspend fun getLatest(): LatestSessionResponse {
        return service.getLatest()
    }
}
