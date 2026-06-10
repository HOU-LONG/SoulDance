package com.example.shopguideagent.audio

class AudioQueue {
    private val chunks = ArrayDeque<ByteArray>()

    fun offer(chunk: ByteArray) {
        chunks.addLast(chunk)
    }

    fun poll(): ByteArray? = chunks.removeFirstOrNull()

    fun peek(): ByteArray? = chunks.firstOrNull()

    fun isEmpty(): Boolean = chunks.isEmpty()

    fun clear() {
        chunks.clear()
    }
}
