package com.example.shopguideagent.data.remote

import okhttp3.Interceptor
import okhttp3.Response

/**
 * 为所有出站 HTTP 请求附加 X-User-Id。
 *
 * 单一身份传递通道：避免在 body 里再塞一份 user_id。
 * 如果调用方已经显式设置了 X-User-Id（例如测试），保留不覆盖。
 */
class UserIdHeaderInterceptor(
    private val userIdProvider: () -> String,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        if (original.header(HEADER_NAME) != null) {
            return chain.proceed(original)
        }
        val updated = original.newBuilder()
            .header(HEADER_NAME, userIdProvider())
            .build()
        return chain.proceed(updated)
    }

    companion object {
        const val HEADER_NAME = "X-User-Id"
    }
}
