package com.example.shopguideagent.data.remote

/**
 * Sessions API 抽象接口，便于在测试中替换实现。
 */
interface SessionsApi {
    suspend fun getLatest(): LatestSessionResponse
    suspend fun listSessions(): SessionListResponse
    suspend fun getSession(sessionId: String): SessionDetailResponse
    suspend fun deleteSession(sessionId: String)
}

/**
 * 基于 Retrofit 的默认实现。
 */
class SessionsApiClient(
    private val service: SessionsApiService,
) : SessionsApi {
    override suspend fun getLatest(): LatestSessionResponse = service.getLatest()
    override suspend fun listSessions(): SessionListResponse = service.listSessions()
    override suspend fun getSession(sessionId: String): SessionDetailResponse = service.getSession(sessionId)
    override suspend fun deleteSession(sessionId: String) = service.deleteSession(sessionId)
}
