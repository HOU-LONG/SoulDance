package com.example.shopguideagent.data.repository

import com.example.shopguideagent.data.local.SpiritPreferencesDataSource
import com.example.shopguideagent.ui.home.SpiritProgressUiState

interface SpiritProgressRepository {
    fun loadProgress(): SpiritProgressUiState
    fun saveProgress(progress: SpiritProgressUiState)
}

class InMemorySpiritProgressRepository(
    private var progress: SpiritProgressUiState = SpiritProgressUiState(),
) : SpiritProgressRepository {
    override fun loadProgress(): SpiritProgressUiState = progress

    override fun saveProgress(progress: SpiritProgressUiState) {
        this.progress = progress
    }
}

class SharedPreferencesSpiritProgressRepository(
    private val dataSource: SpiritPreferencesDataSource,
) : SpiritProgressRepository {
    override fun loadProgress(): SpiritProgressUiState = dataSource.loadProgress()

    override fun saveProgress(progress: SpiritProgressUiState) {
        dataSource.saveProgress(progress)
    }
}
