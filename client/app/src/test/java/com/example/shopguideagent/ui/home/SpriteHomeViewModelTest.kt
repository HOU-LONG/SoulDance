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
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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
        val expectedReward = FireRewardCalculator.reward(SpriteHomeRewards.ADD_TO_CART_FIRE, before.spiritProgress.level)

        viewModel.onRealtimeEvent(event)
        viewModel.onRealtimeEvent(event)

        val after = viewModel.uiState.value
        assertEquals(AvatarState.CELEBRATING, after.transientAvatarState)
        assertEquals(AvatarState.CELEBRATING, after.displayedAvatarState)
        assertEquals(before.userProfile.firePoints + expectedReward, after.userProfile.firePoints)
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
        viewModel.onAction(SpriteHomeAction.EarnFireClicked)

        assertEquals(
            listOf(SpriteHomeEffect.NavigateToChat, SpriteHomeEffect.NavigateToWardrobe, SpriteHomeEffect.ShowTaskCenter),
            effects,
        )
        job.cancel()
    }

    // --- Task logic tests ---

    @Test
    fun dailyLoginTaskIsClaimableOnInit() {
        val viewModel = SpriteHomeViewModel()
        val loginTask = viewModel.uiState.value.tasks.find { it.taskId == "daily_login" }
        assertNotNull(loginTask)
        assertTrue(loginTask!!.completed)
        assertFalse(loginTask.claimed)
        assertTrue(loginTask.claimable)
    }

    @Test
    fun claimingDailyLoginTaskMarksClaimedAndAddsReward() = runTest {
        val viewModel = SpriteHomeViewModel()
        val before = viewModel.uiState.value
        val loginTask = before.tasks.find { it.taskId == "daily_login" }!!
        val expectedReward = FireRewardCalculator.reward(loginTask.baseFireReward, before.spiritProgress.level)

        val effects = mutableListOf<SpriteHomeEffect>()
        val job = launch(UnconfinedTestDispatcher(testScheduler)) {
            viewModel.effects.take(1).collect { effects.add(it) }
        }

        viewModel.onAction(SpriteHomeAction.TaskClaimed("daily_login"))

        val after = viewModel.uiState.value
        val claimedTask = after.tasks.find { it.taskId == "daily_login" }!!
        assertTrue(claimedTask.claimed)
        assertFalse(claimedTask.claimable)
        assertEquals(before.userProfile.firePoints + expectedReward, after.userProfile.firePoints)
        assertEquals("任务奖励已领取", after.speechBubble.text)
        assertEquals(SpeechBubbleStyle.SUCCESS, after.speechBubble.style)

        val effect = effects.first() as SpriteHomeEffect.ShowClaimedReward
        assertEquals("daily_login", effect.taskId)
        job.cancel()
    }

    @Test
    fun claimingNonExistentTaskDoesNothing() {
        val viewModel = SpriteHomeViewModel()
        val before = viewModel.uiState.value

        viewModel.onAction(SpriteHomeAction.TaskClaimed("nonexistent"))

        assertEquals(before, viewModel.uiState.value)
    }

    @Test
    fun claimingAlreadyClaimedTaskDoesNothing() {
        val viewModel = SpriteHomeViewModel()
        viewModel.onAction(SpriteHomeAction.TaskClaimed("daily_login"))
        val afterFirstClaim = viewModel.uiState.value

        viewModel.onAction(SpriteHomeAction.TaskClaimed("daily_login"))

        assertEquals(afterFirstClaim.userProfile.firePoints, viewModel.uiState.value.userProfile.firePoints)
    }

    @Test
    fun productsDoneIncrementsDailyGuideChatTask() {
        val viewModel = SpriteHomeViewModel()
        val before = viewModel.uiState.value.tasks.find { it.taskId == "daily_guide_chat" }!!
        assertEquals(0, before.currentCount)
        assertFalse(before.completed)

        viewModel.onRealtimeEvent(RealtimeEvent.ProductsStart("m1", expectedCount = 1, title = null))
        viewModel.onRealtimeEvent(RealtimeEvent.ProductItem("m1", 0, sampleProduct()))
        viewModel.onRealtimeEvent(RealtimeEvent.ProductsDone("m1"))

        val after = viewModel.uiState.value.tasks.find { it.taskId == "daily_guide_chat" }!!
        assertEquals(1, after.currentCount)
        assertTrue(after.completed)
        assertTrue(after.claimable)
    }

    @Test
    fun productViewedForTaskIncrementsBrowseRecommendations() {
        val viewModel = SpriteHomeViewModel()
        val before = viewModel.uiState.value.tasks.find { it.taskId == "browse_recommendations" }!!
        assertEquals(0, before.currentCount)

        viewModel.onAction(SpriteHomeAction.ProductViewedForTask)
        viewModel.onAction(SpriteHomeAction.ProductViewedForTask)

        val after = viewModel.uiState.value.tasks.find { it.taskId == "browse_recommendations" }!!
        assertEquals(2, after.currentCount)
        assertFalse(after.completed) // target is 3
    }

    @Test
    fun productSharedIncrementsShareGoodProductTask() {
        val viewModel = SpriteHomeViewModel()
        val before = viewModel.uiState.value.tasks.find { it.taskId == "share_good_product" }!!
        assertEquals(0, before.currentCount)
        assertFalse(before.completed)

        viewModel.onAction(SpriteHomeAction.ProductShared)

        val after = viewModel.uiState.value.tasks.find { it.taskId == "share_good_product" }!!
        assertEquals(1, after.currentCount)
        assertTrue(after.completed)
        assertTrue(after.claimable)
    }

    @Test
    fun addToCartIncrementsAddToCartTask() {
        val viewModel = SpriteHomeViewModel()
        val before = viewModel.uiState.value.tasks.find { it.taskId == "add_to_cart" }!!
        assertEquals(0, before.currentCount)
        assertFalse(before.completed)

        viewModel.onCartOperationEvent(CartOperationEvent.AddToCartSucceeded("p1", 1))

        val after = viewModel.uiState.value.tasks.find { it.taskId == "add_to_cart" }!!
        assertEquals(1, after.currentCount)
        assertTrue(after.completed)
        assertTrue(after.claimable)
    }

    @Test
    fun addToCartAppliesIntimacyBonusBasedOnLevel() {
        val viewModel = SpriteHomeViewModel(
            initialState = SpriteHomeUiState(
                spiritProgress = SpiritProgressUiState(level = 15, currentIntimacy = 0, requiredIntimacy = 100),
            ),
        )
        val before = viewModel.uiState.value
        // Level 15 bonus rate is 10%
        val expectedReward = FireRewardCalculator.reward(SpriteHomeRewards.ADD_TO_CART_FIRE, 15)

        viewModel.onCartOperationEvent(CartOperationEvent.AddToCartSucceeded("p1", 1))

        val after = viewModel.uiState.value
        assertEquals(before.userProfile.firePoints + expectedReward, after.userProfile.firePoints)
    }

    @Test
    fun taskIncrementDoesNotExceedTarget() {
        val viewModel = SpriteHomeViewModel()
        val browseTask = viewModel.uiState.value.tasks.find { it.taskId == "browse_recommendations" }!!
        assertEquals(3, browseTask.targetCount)

        // Increment 5 times
        repeat(5) { viewModel.onAction(SpriteHomeAction.ProductViewedForTask) }

        val after = viewModel.uiState.value.tasks.find { it.taskId == "browse_recommendations" }!!
        assertEquals(3, after.currentCount)
        assertTrue(after.completed)
    }

    @Test
    fun claimingTaskAfterCompletionUsesCorrectReward() = runTest {
        val viewModel = SpriteHomeViewModel(
            initialState = SpriteHomeUiState(
                spiritProgress = SpiritProgressUiState(level = 25, currentIntimacy = 0, requiredIntimacy = 100),
            ),
        )
        val before = viewModel.uiState.value
        // Level 25 bonus rate is 20%
        val loginTask = before.tasks.find { it.taskId == "daily_login" }!!
        val expectedReward = FireRewardCalculator.reward(loginTask.baseFireReward, 25)

        val effects = mutableListOf<SpriteHomeEffect>()
        val job = launch(UnconfinedTestDispatcher(testScheduler)) {
            viewModel.effects.take(1).collect { effects.add(it) }
        }

        viewModel.onAction(SpriteHomeAction.TaskClaimed("daily_login"))

        val after = viewModel.uiState.value
        assertEquals(before.userProfile.firePoints + expectedReward, after.userProfile.firePoints)
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
