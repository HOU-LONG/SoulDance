package com.example.shopguideagent.ui.home

import com.example.shopguideagent.R
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SpriteAssetRegistryTest {

    @Test
    fun defaultOutfitMapsEachStateToItsMatrixDrawable() {
        assertEquals(R.drawable.avatar_idle_default, drawable(AvatarState.IDLE))
        assertEquals(R.drawable.avatar_listening_default, drawable(AvatarState.LISTENING))
        assertEquals(R.drawable.avatar_thinking_default, drawable(AvatarState.THINKING))
        assertEquals(R.drawable.avatar_searching_default, drawable(AvatarState.SEARCHING))
        assertEquals(R.drawable.avatar_presenting_default, drawable(AvatarState.PRESENTING))
        assertEquals(R.drawable.avatar_celebrating_default, drawable(AvatarState.CELEBRATING))
        assertEquals(R.drawable.avatar_celebrating_default, drawable(AvatarState.LEVEL_UP))
        assertEquals(R.drawable.avatar_apologizing_default, drawable(AvatarState.ERROR))
    }

    @Test
    fun homeAdvisorUsesDedicatedAssetForIdleAndPresenting() {
        assertEquals(
            R.drawable.avatar_presenting_home_advisor,
            SpriteAssetRegistry.avatarDrawable(SpriteAssetRegistry.OUTFIT_HOME_ADVISOR, AvatarState.IDLE),
        )
        assertEquals(
            R.drawable.avatar_presenting_home_advisor,
            SpriteAssetRegistry.avatarDrawable(SpriteAssetRegistry.OUTFIT_HOME_ADVISOR, AvatarState.PRESENTING),
        )
    }

    @Test
    fun homeAdvisorFallsBackToDefaultGroupForMissingStates() {
        // manifest 中 HOME_ADVISOR._fallback = DEFAULT：缺失服装状态回落到默认组，不伪造素材
        assertEquals(
            R.drawable.avatar_searching_default,
            SpriteAssetRegistry.avatarDrawable(SpriteAssetRegistry.OUTFIT_HOME_ADVISOR, AvatarState.SEARCHING),
        )
        assertEquals(
            R.drawable.avatar_apologizing_default,
            SpriteAssetRegistry.avatarDrawable(SpriteAssetRegistry.OUTFIT_HOME_ADVISOR, AvatarState.ERROR),
        )
    }

    @Test
    fun layersForResolvesBaseAndLeavesOverlaysUnset() {
        val layers = SpriteAssetRegistry.layersFor(AvatarAppearance(), AvatarState.IDLE)
        assertEquals(R.drawable.avatar_idle_default, layers.baseResId)
        assertNotEquals(0, layers.baseResId)
        assertNull(layers.outfitResId)
        assertNull(layers.accessoryResId)
        assertNull(layers.propResId)
    }

    @Test
    fun homeAdvisorAppearanceResolvesToDedicatedIdleAsset() {
        val layers = SpriteAssetRegistry.layersFor(
            AvatarAppearance(outfitId = SpriteAssetRegistry.OUTFIT_HOME_ADVISOR),
            AvatarState.IDLE,
        )
        assertEquals(R.drawable.avatar_presenting_home_advisor, layers.baseResId)
    }

    private fun drawable(state: AvatarState): Int =
        SpriteAssetRegistry.avatarDrawable(SpriteAssetRegistry.OUTFIT_DEFAULT, state)
}
