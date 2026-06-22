package com.example.shopguideagent.data.local

import android.content.Context
import com.example.shopguideagent.ui.home.AvatarAppearance
import com.example.shopguideagent.ui.home.SpiritProgressUiState

class SpiritPreferencesDataSource(context: Context) {
    private val preferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun loadProgress(): SpiritProgressUiState = SpiritProgressUiState(
        spiritName = preferences.getString(KEY_SPIRIT_NAME, null) ?: SpiritProgressUiState().spiritName,
        level = preferences.getInt(KEY_LEVEL, SpiritProgressUiState().level),
        currentIntimacy = preferences.getInt(KEY_CURRENT_INTIMACY, SpiritProgressUiState().currentIntimacy),
        requiredIntimacy = preferences.getInt(KEY_REQUIRED_INTIMACY, SpiritProgressUiState().requiredIntimacy),
        intimacyLabel = preferences.getString(KEY_INTIMACY_LABEL, null) ?: SpiritProgressUiState().intimacyLabel,
        subtitle = preferences.getString(KEY_SUBTITLE, null) ?: SpiritProgressUiState().subtitle,
    )

    fun saveProgress(progress: SpiritProgressUiState) {
        preferences.edit()
            .putString(KEY_SPIRIT_NAME, progress.spiritName)
            .putInt(KEY_LEVEL, progress.level)
            .putInt(KEY_CURRENT_INTIMACY, progress.currentIntimacy)
            .putInt(KEY_REQUIRED_INTIMACY, progress.requiredIntimacy)
            .putString(KEY_INTIMACY_LABEL, progress.intimacyLabel)
            .putString(KEY_SUBTITLE, progress.subtitle)
            .apply()
    }

    fun loadAppearance(): AvatarAppearance = AvatarAppearance(
        baseAvatarId = preferences.getString(KEY_BASE_AVATAR_ID, null) ?: AvatarAppearance().baseAvatarId,
        outfitId = preferences.getString(KEY_OUTFIT_ID, null) ?: AvatarAppearance().outfitId,
        accessoryId = preferences.getString(KEY_ACCESSORY_ID, null) ?: AvatarAppearance().accessoryId,
        propId = preferences.getString(KEY_PROP_ID, null) ?: AvatarAppearance().propId,
        backgroundId = preferences.getString(KEY_BACKGROUND_ID, null) ?: AvatarAppearance().backgroundId,
    )

    fun saveAppearance(appearance: AvatarAppearance) {
        preferences.edit()
            .putString(KEY_BASE_AVATAR_ID, appearance.baseAvatarId)
            .putString(KEY_OUTFIT_ID, appearance.outfitId)
            .putString(KEY_ACCESSORY_ID, appearance.accessoryId)
            .putString(KEY_PROP_ID, appearance.propId)
            .putString(KEY_BACKGROUND_ID, appearance.backgroundId)
            .apply()
    }

    private companion object {
        const val PREFS_NAME = "sprite_home"
        const val KEY_SPIRIT_NAME = "spirit_name"
        const val KEY_LEVEL = "level"
        const val KEY_CURRENT_INTIMACY = "current_intimacy"
        const val KEY_REQUIRED_INTIMACY = "required_intimacy"
        const val KEY_INTIMACY_LABEL = "intimacy_label"
        const val KEY_SUBTITLE = "subtitle"
        const val KEY_BASE_AVATAR_ID = "base_avatar_id"
        const val KEY_OUTFIT_ID = "outfit_id"
        const val KEY_ACCESSORY_ID = "accessory_id"
        const val KEY_PROP_ID = "prop_id"
        const val KEY_BACKGROUND_ID = "background_id"
    }
}
