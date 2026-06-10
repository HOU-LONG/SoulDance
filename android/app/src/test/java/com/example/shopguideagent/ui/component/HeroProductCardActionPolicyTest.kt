package com.example.shopguideagent.ui.component

import org.junit.Assert.assertFalse
import org.junit.Test

class HeroProductCardActionPolicyTest {
    @Test
    fun heroProductCardDoesNotShowFavoriteAction() {
        assertFalse(HeroProductCardActionPolicy.showFavoriteAction)
    }
}
