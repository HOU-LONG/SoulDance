package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.RealtimeEvent
import com.example.shopguideagent.test.CoroutineTestHelper
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Before
import org.junit.Test

class SpriteHomeViewModelTest {
    @Before
    fun setUp() {
        CoroutineTestHelper.setMainDispatcher()
    }

    @After
    fun tearDown() {
        CoroutineTestHelper.resetMainDispatcher()
    }

    @Test
    fun productEventsMoveAvatarFromSearchingToPresentingAndStoreLatestProduct() {
        val viewModel = SpriteHomeViewModel()

        viewModel.onRealtimeEvent(RealtimeEvent.ProductsStart("m1", expectedCount = 2, title = null))
        assertEquals(AvatarState.SEARCHING, viewModel.uiState.value.avatarState)

        viewModel.onRealtimeEvent(RealtimeEvent.ProductItem("m1", 0, sampleProduct()))
        assertEquals(AvatarState.PRESENTING, viewModel.uiState.value.avatarState)
        assertEquals("p1", viewModel.uiState.value.latestProduct?.productId)

        viewModel.onRealtimeEvent(RealtimeEvent.ProductsDone("m1"))
        assertEquals(AvatarState.PRESENTING, viewModel.uiState.value.avatarState)
    }

    @Test
    fun successfulCartUpdateCelebratesAndIncreasesRewards() {
        val viewModel = SpriteHomeViewModel()
        val before = viewModel.uiState.value

        viewModel.onRealtimeEvent(
            RealtimeEvent.CartUpdate(
                messageId = "m1",
                badgeCount = 1,
                message = "added",
                action = "add_to_cart",
                productId = "p1",
                success = true,
            ),
        )

        val after = viewModel.uiState.value
        assertEquals(AvatarState.CELEBRATING, after.avatarState)
        assertEquals(before.fireValue + SpriteHomeRewards.ADD_TO_CART_FIRE, after.fireValue)
        assertEquals(before.intimacy + SpriteHomeRewards.ADD_TO_CART_INTIMACY, after.intimacy)
    }

    @Test
    fun intimacyCrossingThresholdTriggersLevelUp() {
        val viewModel = SpriteHomeViewModel(
            initialState = SpriteHomeUiState(level = 1, intimacy = 95, intimacyMax = 100),
        )

        viewModel.onLocalAddToCartSuccess()

        assertEquals(AvatarState.LEVEL_UP, viewModel.uiState.value.avatarState)
        assertEquals(2, viewModel.uiState.value.level)
        assertEquals(0, viewModel.uiState.value.intimacy)
    }

    @Test
    fun stageAnimationFinishedReturnsTransientStatesToStableState() {
        val viewModel = SpriteHomeViewModel()

        viewModel.onRealtimeEvent(RealtimeEvent.Error("bad network"))
        assertEquals(AvatarState.ERROR, viewModel.uiState.value.avatarState)

        viewModel.onStageAnimationFinished()
        assertEquals(AvatarState.IDLE, viewModel.uiState.value.avatarState)
    }

    @Test
    fun voiceAndRequestCallbacksSetListeningAndSearching() {
        val viewModel = SpriteHomeViewModel()

        viewModel.onVoiceRecordingStarted()
        assertEquals(AvatarState.LISTENING, viewModel.uiState.value.avatarState)

        viewModel.onRequestSent()
        assertEquals(AvatarState.SEARCHING, viewModel.uiState.value.avatarState)
        assertNotNull(viewModel.uiState.value.speechText)
    }

    private fun sampleProduct(): ProductUiModel = ProductUiModel(
        productId = "p1",
        name = "Smart headphones",
        price = 299.0,
        isPrimary = true,
    )
}
