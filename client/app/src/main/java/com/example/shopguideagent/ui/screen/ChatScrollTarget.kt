package com.example.shopguideagent.ui.screen

object ChatScrollTarget {
    @JvmStatic
    fun latestMessageIndex(messageCount: Int): Int =
        messageCount.coerceAtLeast(0)

    @JvmStatic
    fun bottomIndex(messageCount: Int): Int =
        messageCount.coerceAtLeast(0) + 1

    @JvmStatic
    fun shouldAutoFollow(
        isSending: Boolean,
        latestMessageStreaming: Boolean,
        userAwayFromBottom: Boolean,
    ): Boolean =
        isSending || latestMessageStreaming || !userAwayFromBottom
}
