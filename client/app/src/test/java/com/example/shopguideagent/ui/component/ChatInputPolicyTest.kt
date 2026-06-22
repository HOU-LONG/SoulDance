package com.example.shopguideagent.ui.component

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class ChatInputPolicyTest {
    @Test
    fun chatInputAllowsMultilineTextUpToFiveLines() {
        assertFalse(ChatInputTextPolicy.singleLine)
        assertEquals(1, ChatInputTextPolicy.minLines)
        assertEquals(5, ChatInputTextPolicy.maxLines)
    }

    @Test
    fun productFocusInputAllowsMultilineTextUpToFiveLines() {
        assertFalse(ProductFocusInputTextPolicy.singleLine)
        assertEquals(1, ProductFocusInputTextPolicy.minLines)
        assertEquals(5, ProductFocusInputTextPolicy.maxLines)
    }

    @Test
    fun thinkingIndicatorDoesNotExposeEnglishStatusLabel() {
        assertEquals(null, ThinkingLogoIndicatorTextPolicy.visibleLabel)
    }

    @Test
    fun voiceInputHintsKeepReleaseAsSubmitAndUpwardDragAsCancel() {
        assertEquals("上滑取消", VoiceInputTextPolicy.cancelHint)
        assertEquals("正在聆听...", VoiceInputTextPolicy.listeningHint)
    }
}
