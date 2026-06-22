package com.example.shopguideagent.ui.screen

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class ChatScreenArchitectureTest {
    @Test
    fun chatScreenUsesWarmSpriteRoomBackground() {
        val source = findRepoFile("client/app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt")
            .readText()

        assertTrue("Chat screen should share the warm sprite-space background start", source.contains("SpriteRoomTop"))
        assertTrue("Chat screen should share the warm sprite-space background middle", source.contains("SpriteRoomMiddle"))
        assertTrue("Chat screen should share the warm sprite-space background light", source.contains("SpriteRoomLight"))
        assertTrue("Chat screen should share the warm sprite-space background bottom", source.contains("SpriteRoomBottom"))
        assertFalse("Chat screen should not keep the old green app background container", source.contains("containerColor = AppBackground"))
        assertFalse("Chat screen should not keep the old green gradient end", source.contains("AppBackgroundGradientEnd"))
    }

    private fun findRepoFile(relativePath: String): File {
        var current = File(System.getProperty("user.dir")).absoluteFile
        repeat(8) {
            val candidate = File(current, relativePath)
            if (candidate.exists()) return candidate
            current = current.parentFile ?: current
        }
        throw AssertionError("Could not find $relativePath from ${System.getProperty("user.dir")}")
    }
}
