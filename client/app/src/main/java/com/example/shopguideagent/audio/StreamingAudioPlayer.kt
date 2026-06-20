package com.example.shopguideagent.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import kotlinx.coroutines.*
import java.util.concurrent.atomic.AtomicBoolean

open class StreamingAudioPlayer {
    private val queue = AudioQueue()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var playJob: Job? = null
    private val isPlaying = AtomicBoolean(false)
    private val endOfStream = AtomicBoolean(false)

    @Volatile
    private var sampleRate = DEFAULT_SAMPLE_RATE
    private val channelConfig = AudioFormat.CHANNEL_OUT_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT

    open fun enqueuePcm(chunk: ByteArray, sampleRate: Int = DEFAULT_SAMPLE_RATE) {
        if (!isPlaying.get()) {
            this.sampleRate = sampleRate
        }
        queue.offer(chunk)
        startIfNeeded()
    }

    open fun markEndOfStream() {
        endOfStream.set(true)
    }

    open fun stop() {
        playJob?.cancel()
        playJob = null
        queue.clear()
        endOfStream.set(false)
        isPlaying.set(false)
    }

    open fun release() {
        stop()
        scope.cancel()
    }

    private fun startIfNeeded() {
        if (isPlaying.getAndSet(true)) return

        playJob = scope.launch {
            val bufferSize = AudioTrack.getMinBufferSize(sampleRate, channelConfig, audioFormat)
            val track = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setSampleRate(sampleRate)
                        .setEncoding(audioFormat)
                        .setChannelMask(channelConfig)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize * 2)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            track.play()

            try {
                while (isActive) {
                    val chunk = queue.poll()
                    if (chunk != null) {
                        track.write(chunk, 0, chunk.size)
                    } else if (endOfStream.get()) {
                        delay(300)
                        break
                    } else {
                        delay(40)
                    }
                }
            } catch (e: Exception) {
                Log.e("StreamingAudioPlayer", "Playback error", e)
            } finally {
                track.stop()
                track.release()
                isPlaying.set(false)
                endOfStream.set(false)
            }
        }
    }

    private companion object {
        const val DEFAULT_SAMPLE_RATE = 16000
    }
}
