package com.example.shopguideagent.data.repository

import com.example.shopguideagent.data.local.SpiritPreferencesDataSource
import com.example.shopguideagent.ui.home.AvatarAppearance

interface SpiritAppearanceRepository {
    fun loadAppearance(): AvatarAppearance
    fun saveAppearance(appearance: AvatarAppearance)
}

class InMemorySpiritAppearanceRepository(
    private var appearance: AvatarAppearance = AvatarAppearance(),
) : SpiritAppearanceRepository {
    override fun loadAppearance(): AvatarAppearance = appearance

    override fun saveAppearance(appearance: AvatarAppearance) {
        this.appearance = appearance
    }
}

class SharedPreferencesSpiritAppearanceRepository(
    private val dataSource: SpiritPreferencesDataSource,
) : SpiritAppearanceRepository {
    override fun loadAppearance(): AvatarAppearance = dataSource.loadAppearance()

    override fun saveAppearance(appearance: AvatarAppearance) {
        dataSource.saveAppearance(appearance)
    }
}
