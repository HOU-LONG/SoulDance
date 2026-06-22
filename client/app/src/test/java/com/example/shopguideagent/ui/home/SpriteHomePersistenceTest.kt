package com.example.shopguideagent.ui.home

import com.example.shopguideagent.domain.event.CartOperationEvent
import com.example.shopguideagent.data.repository.SpiritAppearanceRepository
import com.example.shopguideagent.data.repository.SpiritProgressRepository
import com.example.shopguideagent.test.CoroutineTestHelper
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

class SpriteHomePersistenceTest {
    @Before
    fun setUp() {
        CoroutineTestHelper.setMainDispatcher()
    }

    @After
    fun tearDown() {
        CoroutineTestHelper.resetMainDispatcher()
    }

    @Test
    fun cartSuccessPersistsUpdatedProgress() {
        val progressRepository = FakeProgressRepository(
            SpiritProgressUiState(level = 1, currentIntimacy = 90, requiredIntimacy = 100),
        )
        val viewModel = SpriteHomeViewModel(
            progressRepository = progressRepository,
            appearanceRepository = FakeAppearanceRepository(),
        )

        viewModel.onCartOperationEvent(CartOperationEvent.AddToCartSucceeded("p1", 1))

        assertEquals(2, progressRepository.savedProgress.last().level)
        assertEquals(0, progressRepository.savedProgress.last().currentIntimacy)
    }

    private class FakeProgressRepository(
        private val initial: SpiritProgressUiState = SpiritProgressUiState(),
    ) : SpiritProgressRepository {
        val savedProgress = mutableListOf<SpiritProgressUiState>()

        override fun loadProgress(): SpiritProgressUiState = initial

        override fun saveProgress(progress: SpiritProgressUiState) {
            savedProgress += progress
        }
    }

    private class FakeAppearanceRepository(
        private val initial: AvatarAppearance = AvatarAppearance(),
    ) : SpiritAppearanceRepository {
        val savedAppearance = mutableListOf<AvatarAppearance>()

        override fun loadAppearance(): AvatarAppearance = initial

        override fun saveAppearance(appearance: AvatarAppearance) {
            savedAppearance += appearance
        }
    }
}
