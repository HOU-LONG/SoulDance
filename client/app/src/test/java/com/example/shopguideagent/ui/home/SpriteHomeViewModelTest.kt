package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.RealtimeEvent
import com.example.shopguideagent.domain.event.CartOperationEvent
import com.example.shopguideagent.test.CoroutineTestHelper
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
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
    fun productEventsUpdateBaseStateAndStoreLatestProduct() {
        val viewModel = SpriteHomeViewModel()

        viewModel.onRealtimeEvent(RealtimeEvent.ProductsStart("m1", expectedCount = 2, title = null))
        assertEquals(AvatarState.SEARCHING, viewModel.uiState.value.baseAvatarState)
        assertEquals(AvatarState.SEARCHING, viewModel.uiState.value.displayedAvatarState)
        assertEquals(2, viewModel.uiState.value.productPresentation.expectedCount)

        viewModel.onRealtimeEvent(RealtimeEvent.ProductItem("m1", 0, sampleProduct()))
        assertEquals(AvatarState.PRESENTING, viewModel.uiState.value.baseAvatarState)
        assertEquals(AvatarState.PRESENTING, viewModel.uiState.value.displayedAvatarState)
        assertEquals("p1", viewModel.uiState.value.presentingProduct?.productId)
        assertEquals("p1", viewModel.uiState.value.productPresentation.primaryProduct?.productId)

        viewModel.onRealtimeEvent(RealtimeEvent.ProductsDone("m1"))
        assertEquals(AvatarState.PRESENTING, viewModel.uiState.value.baseAvatarState)
        assertEquals(true, viewModel.uiState.value.productPresentation.completed)
    }

    @Test
    fun successfulCartUpdateUsesTransientCelebrationAndIncreasesRewardsOnce() {
        val viewModel = SpriteHomeViewModel()
        val before = viewModel.uiState.value
        val event = cartUpdate("m1", success = true)

        viewModel.onRealtimeEvent(event)
        viewModel.onRealtimeEvent(event)

        val after = viewModel.uiState.value
        assertEquals(AvatarState.CELEBRATING, after.transientAvatarState)
        assertEquals(AvatarState.CELEBRATING, after.displayedAvatarState)
        assertEquals(before.userProfile.firePoints + SpriteHomeRewards.ADD_TO_CART_FIRE, after.userProfile.firePoints)
        assertEquals(before.spiritProgress.currentIntimacy + SpriteHomeRewards.ADD_TO_CART_INTIMACY, after.spiritProgress.currentIntimacy)
    }

    @Test
    fun failedCartUpdateDoesNotCelebrateOrIncreaseRewards() {
        val viewModel = SpriteHomeViewModel()
        val before = viewModel.uiState.value

        viewModel.onRealtimeEvent(cartUpdate("m1", success = false))

        assertNull(viewModel.uiState.value.transientAvatarState)
        assertEquals(before.userProfile.firePoints, viewModel.uiState.value.userProfile.firePoints)
        assertEquals(before.spiritProgress.currentIntimacy, viewModel.uiState.value.spiritProgress.currentIntimacy)
    }

    @Test
    fun intimacyCrossingThresholdTriggersLevelUpTransientState() {
        val viewModel = SpriteHomeViewModel(
            initialState = SpriteHomeUiState(
                spiritProgress = SpiritProgressUiState(level = 1, currentIntimacy = 95, requiredIntimacy = 100),
            ),
        )

        viewModel.onCartOperationEvent(CartOperationEvent.AddToCartSucceeded("p1", 1))

        assertEquals(AvatarState.LEVEL_UP, viewModel.uiState.value.transientAvatarState)
        assertEquals(AvatarState.LEVEL_UP, viewModel.uiState.value.displayedAvatarState)
        assertEquals(2, viewModel.uiState.value.spiritProgress.level)
        assertEquals(0, viewModel.uiState.value.spiritProgress.currentIntimacy)
    }

    @Test
    fun productStartDuringCelebrationUpdatesBaseButKeepsTransientUntilAnimationFinishes() {
        val viewModel = SpriteHomeViewModel(
            initialState = SpriteHomeUiState(baseAvatarState = AvatarState.PRESENTING, presentingProduct = sampleProduct()),
        )

        viewModel.onRealtimeEvent(cartUpdate("m1", success = true))
        viewModel.onRealtimeEvent(RealtimeEvent.ProductsStart("m2", expectedCount = 1, title = null))

        assertEquals(AvatarState.SEARCHING, viewModel.uiState.value.baseAvatarState)
        assertEquals(AvatarState.CELEBRATING, viewModel.uiState.value.transientAvatarState)
        assertEquals(AvatarState.CELEBRATING, viewModel.uiState.value.displayedAvatarState)

        viewModel.onStageAnimationFinished()
        assertNull(viewModel.uiState.value.transientAvatarState)
        assertEquals(AvatarState.SEARCHING, viewModel.uiState.value.displayedAvatarState)
    }

    @Test
    fun voiceAndRequestCallbacksSetBaseListeningAndSearching() {
        val viewModel = SpriteHomeViewModel()

        viewModel.onVoiceRecordingStarted()
        assertEquals(AvatarState.LISTENING, viewModel.uiState.value.baseAvatarState)

        viewModel.onRequestSent()
        assertEquals(AvatarState.SEARCHING, viewModel.uiState.value.baseAvatarState)
        assertNotNull(viewModel.uiState.value.speechBubble.text)
    }

    @Test
    fun actionsEmitEffectsWithoutNavigatingInComposable() = runTest {
        val viewModel = SpriteHomeViewModel()
        val effects = mutableListOf<SpriteHomeEffect>()
        val job = launch(UnconfinedTestDispatcher(testScheduler)) {
            viewModel.effects.take(3).collect { effects.add(it) }
        }

        viewModel.onAction(SpriteHomeAction.ChatModeClicked)
        viewModel.onAction(SpriteHomeAction.DressUpClicked)
        viewModel.onAction(SpriteHomeAction.DailyTaskClicked)

        assertEquals(
            listOf(SpriteHomeEffect.NavigateToChat, SpriteHomeEffect.NavigateToWardrobe, SpriteHomeEffect.NavigateToTasks),
            effects,
        )
        job.cancel()
    }

    private fun cartUpdate(messageId: String, success: Boolean): RealtimeEvent.CartUpdate = RealtimeEvent.CartUpdate(
        messageId = messageId,
        badgeCount = 1,
        message = "added",
        action = "add_to_cart",
        productId = "p1",
        success = success,
    )

    private fun sampleProduct(): ProductUiModel = ProductUiModel(
        productId = "p1",
        name = "Smart headphones",
        price = 299.0,
        isPrimary = true,
    )
}
