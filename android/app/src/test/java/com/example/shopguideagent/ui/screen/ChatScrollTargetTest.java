package com.example.shopguideagent.ui.screen;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class ChatScrollTargetTest {
    @Test
    public void bottomIndexAccountsForHeaderAndFooterSpacer() {
        assertEquals(1, ChatScrollTarget.bottomIndex(0));
        assertEquals(2, ChatScrollTarget.bottomIndex(1));
        assertEquals(5, ChatScrollTarget.bottomIndex(4));
    }

    @Test
    public void latestMessageIndexAccountsForHeaderSpacer() {
        assertEquals(0, ChatScrollTarget.latestMessageIndex(0));
        assertEquals(1, ChatScrollTarget.latestMessageIndex(1));
        assertEquals(4, ChatScrollTarget.latestMessageIndex(4));
    }

    @Test
    public void autoFollowKeepsStreamingReplyVisible() {
        assertEquals(true, ChatScrollTarget.shouldAutoFollow(false, true, false));
        assertEquals(true, ChatScrollTarget.shouldAutoFollow(true, false, true));
        assertEquals(false, ChatScrollTarget.shouldAutoFollow(false, false, true));
    }
}
