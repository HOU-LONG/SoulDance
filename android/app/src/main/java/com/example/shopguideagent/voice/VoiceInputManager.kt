package com.example.shopguideagent.voice

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException

class VoiceInputManager(
    private val context: Context,
    private val onAmplitude: (Float) -> Unit = {},
    private val onFinished: (File) -> Unit,
    private val onError: (String) -> Unit,
) {
    private data class RecordingSession(
        val record: AudioRecord,
    ) {
        @Volatile
        var isRecording: Boolean = true

        @Volatile
        var emitResult: Boolean = true
    }

    private var activeSession: RecordingSession? = null
    private var recordingJob: Job? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val sampleRate = 16000
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT

    fun startRecording() {
        if (activeSession != null) return

        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            onError("缺少录音权限")
            return
        }

        val minBuffer = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
        if (minBuffer < 0) {
            onError("设备不支持该录音配置")
            return
        }

        val record = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            channelConfig,
            audioFormat,
            minBuffer * 2
        )

        if (record.state != AudioRecord.STATE_INITIALIZED) {
            onError("录音初始化失败")
            return
        }

        val session = RecordingSession(record)
        activeSession = session
        val outputStream = ByteArrayOutputStream()

        record.startRecording()

        recordingJob = scope.launch {
            val buffer = ByteArray(minBuffer)
            try {
                while (isActive && session.isRecording) {
                    val read = record.read(buffer, 0, buffer.size)
                    if (read > 0) {
                        outputStream.write(buffer, 0, read)
                        val amplitude = calculateAmplitude(buffer, read)
                        withContext(Dispatchers.Main) {
                            onAmplitude(amplitude)
                        }
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    onError("录音异常: ${e.message}")
                }
            } finally {
                try {
                    record.stop()
                } catch (_: IllegalStateException) {
                }
                record.release()
                if (activeSession === session) {
                    activeSession = null
                    recordingJob = null
                }

                val pcmData = outputStream.toByteArray()
                outputStream.close()

                if (session.emitResult && pcmData.isNotEmpty()) {
                    val wavFile = writeWavToTempFile(pcmData)
                    withContext(Dispatchers.Main) {
                        onFinished(wavFile)
                    }
                }
            }
        }
    }

    fun stopRecording() {
        finishRecording()
    }

    fun finishRecording() {
        stopActiveRecording(emitResult = true)
    }

    fun cancelRecording() {
        stopActiveRecording(emitResult = false)
    }

    fun release() {
        cancelRecording()
        recordingJob?.cancel()
        recordingJob = null
        scope.cancel()
    }

    private fun stopActiveRecording(emitResult: Boolean) {
        val session = activeSession ?: return
        session.emitResult = emitResult
        session.isRecording = false
        try {
            session.record.stop()
        } catch (_: IllegalStateException) {
        }
    }

    private fun calculateAmplitude(buffer: ByteArray, readSize: Int): Float {
        var sum = 0L
        var i = 0
        while (i < readSize - 1) {
            val low = buffer[i].toInt() and 0xFF
            val high = buffer[i + 1].toInt()
            val sample = (high shl 8 or low).toShort()
            sum += kotlin.math.abs(sample.toInt())
            i += 2
        }
        val samples = readSize / 2
        val avg = if (samples > 0) sum / samples else 0
        return (avg / 32768f).coerceIn(0f, 1f)
    }

    private fun writeWavToTempFile(pcmData: ByteArray): File {
        val file = File.createTempFile("voice_", ".wav", context.cacheDir)
        FileOutputStream(file).use { fos ->
            writeWavHeader(fos, pcmData.size)
            fos.write(pcmData)
        }
        return file
    }

    @Throws(IOException::class)
    private fun writeWavHeader(out: FileOutputStream, pcmLen: Int) {
        val totalLen = pcmLen + 36
        val byteRate = sampleRate * 1 * 16 / 8
        val header = ByteArray(44)

        fun writeIntLE(value: Int, offset: Int) {
            header[offset] = (value and 0xFF).toByte()
            header[offset + 1] = ((value shr 8) and 0xFF).toByte()
            header[offset + 2] = ((value shr 16) and 0xFF).toByte()
            header[offset + 3] = ((value shr 24) and 0xFF).toByte()
        }

        fun writeShortLE(value: Short, offset: Int) {
            header[offset] = (value.toInt() and 0xFF).toByte()
            header[offset + 1] = ((value.toInt() shr 8) and 0xFF).toByte()
        }

        header[0] = 'R'.code.toByte()
        header[1] = 'I'.code.toByte()
        header[2] = 'F'.code.toByte()
        header[3] = 'F'.code.toByte()
        writeIntLE(totalLen, 4)
        header[8] = 'W'.code.toByte()
        header[9] = 'A'.code.toByte()
        header[10] = 'V'.code.toByte()
        header[11] = 'E'.code.toByte()
        header[12] = 'f'.code.toByte()
        header[13] = 'm'.code.toByte()
        header[14] = 't'.code.toByte()
        header[15] = ' '.code.toByte()
        writeIntLE(16, 16)
        writeShortLE(1, 20)
        writeShortLE(1, 22)
        writeIntLE(sampleRate, 24)
        writeIntLE(byteRate, 28)
        writeShortLE(2, 32)
        writeShortLE(16, 34)
        header[36] = 'd'.code.toByte()
        header[37] = 'a'.code.toByte()
        header[38] = 't'.code.toByte()
        header[39] = 'a'.code.toByte()
        writeIntLE(pcmLen, 40)

        out.write(header)
    }
}
