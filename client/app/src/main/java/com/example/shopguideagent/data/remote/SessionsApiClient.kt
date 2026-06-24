package com.example.shopguideagent.data.remote

class SessionsApiClient(
    private val service: SessionsApiService = SessionsApiService.create(),
) {
    @Deprecated("Use constructor with service that includes userIdProvider")
    constructor() : this(SessionsApiService.create())

    suspend fun getLatest(): LatestSessionResponse {
        return service.getLatest()
    }
}
