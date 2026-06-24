package com.example.shopguideagent.data.remote

import com.example.shopguideagent.config.AppConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.InterruptedIOException
import java.net.SocketException
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit

interface SpeechToTextClient {
    suspend fun transcribe(audioFile: File): Result<String>
}

class SttApiService(
    private val userIdProvider: () -> String = { "demo_user_a" },
    private val baseHttpUrl: String = AppConfig.BASE_HTTP_URL,
    private val client: OkHttpClient? = null,
) : SpeechToTextClient {

    private val actualClient: OkHttpClient by lazy {
        client ?: defaultSttClient(userIdProvider)
    }


    override suspend fun transcribe(audioFile: File): Result<String> = withContext(Dispatchers.IO) {
        var lastFailure: Exception? = null
        for (attempt in 0 until STT_MAX_ATTEMPTS) {
            try {
                return@withContext executeTranscription(audioFile)
            } catch (e: Exception) {
                val retryable = e.isTransportClosed()
                val normalized = e.normalizedSttException()
                if (attempt + 1 < STT_MAX_ATTEMPTS && retryable) {
                    lastFailure = normalized
                    continue
                }
                return@withContext Result.failure(normalized)
            }
        }
        Result.failure(lastFailure ?: IOException("语音识别失败，请再试一次"))
    }

    private fun executeTranscription(audioFile: File): Result<String> {
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "audio",
                audioFile.name,
                audioFile.asRequestBody("audio/wav".toMediaTypeOrNull()),
            )
            .build()

        val request = Request.Builder()
            .url("${baseHttpUrl.trimEnd('/')}/api/stt")
            .post(requestBody)
            .build()

        actualClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val message = response.body?.string()?.backendMessage()
                return Result.failure(
                    IOException(message ?: "STT request failed: ${response.code}"),
                )
            }
            val body = response.body?.string()
                ?: return Result.failure(IOException("Empty response body"))
            val json = JSONObject(body)
            val text = json.optString("text", "")
            return Result.success(text)
        }
    }

    private fun String.backendMessage(): String? =
        runCatching {
            val json = JSONObject(this)
            json.optString("detail").takeIf { it.isNotBlank() }
                ?: json.optString("message").takeIf { it.isNotBlank() }
                ?: json.optString("error").takeIf { it.isNotBlank() }
        }.getOrNull() ?: takeIf { it.isNotBlank() }

    private fun Exception.normalizedSttException(): Exception {
        return when {
            isSttTimeout() -> IOException("语音识别超时，请再试一次", this)
            isTransportClosed() -> IOException("语音识别连接中断，请再试一次", this)
            else -> this
        }
    }

    private fun Exception.isSttTimeout(): Boolean {
        val message = message.orEmpty()
        val normalized = message.lowercase()
        return this is SocketTimeoutException ||
            (this is InterruptedIOException && normalized.contains("timeout")) ||
            normalized.contains("timeout") ||
            normalized.contains("timed out") ||
            message.contains("超时")
    }

    private fun Exception.isTransportClosed(): Boolean {
        val message = message.orEmpty()
        val normalized = message.lowercase()
        return this is SocketException ||
            normalized.contains("connection closed") ||
            normalized.contains("unexpected end of stream") ||
            normalized.contains("stream was reset") ||
            normalized.contains("connection reset") ||
            normalized.contains("socket closed") ||
            normalized == "closed" ||
            normalized.contains("reset")
    }

    companion object {
        private const val STT_MAX_ATTEMPTS = 2

        private fun defaultSttClient(userIdProvider: () -> String): OkHttpClient =
            OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .callTimeout(45, TimeUnit.SECONDS)
                .addInterceptor(UserIdHeaderInterceptor(userIdProvider))
                .build()
    }
}
