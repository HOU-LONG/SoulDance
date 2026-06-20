package com.example.shopguideagent.ui.home

import androidx.annotation.DrawableRes
import com.example.shopguideagent.R

data class SpriteLayerResources(
    @DrawableRes val baseResId: Int,
    @DrawableRes val outfitResId: Int? = null,
    @DrawableRes val accessoryResId: Int? = null,
    @DrawableRes val propResId: Int? = null,
)

object SpriteAssetRegistry {
    fun layersFor(appearance: AvatarAppearance, avatarState: AvatarState): SpriteLayerResources {
        val base = when (appearance.baseAvatarId) {
            "default_avatar" -> R.drawable.shopping
            else -> R.drawable.shopping
        }
        return SpriteLayerResources(
            baseResId = base,
            outfitResId = null,
            accessoryResId = null,
            propResId = null,
        )
    }
}
