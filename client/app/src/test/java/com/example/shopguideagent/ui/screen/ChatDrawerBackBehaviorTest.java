package com.example.shopguideagent.ui.screen;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class ChatDrawerBackBehaviorTest {
    @Test
    public void systemBackClosesOpenHistoryDrawerBeforeActivityExit() {
        assertTrue(ChatDrawerBackBehavior.shouldCloseDrawer(true));
        assertFalse(ChatDrawerBackBehavior.shouldCloseDrawer(false));
    }
}
