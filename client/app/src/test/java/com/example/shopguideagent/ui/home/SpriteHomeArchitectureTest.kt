package com.example.shopguideagent.ui.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SpriteHomeArchitectureTest {
    @Test
    fun defaultStateUsesSemanticAppearanceIdsInsteadOfDrawableIds() {
        val state = SpriteHomeUiState()

        assertEquals("default_avatar", state.appearance.baseAvatarId)
        assertEquals("default_outfit", state.appearance.outfitId)
        assertEquals("shopping_bag", state.appearance.propId)
        assertEquals(AvatarState.IDLE, state.displayedAvatarState)
        assertNull(state.transientAvatarState)
    }

    @Test
    fun spriteHomeUiStateDoesNotExposeDrawableResourceFields() {
        val forbiddenFields = SpriteHomeUiState::class.java.declaredFields
            .map { it.name }
            .filter { it.endsWith("ResId") || it.endsWith("DrawableId") }

        assertEquals(emptyList<String>(), forbiddenFields)
    }

    @Test
    fun assetRegistryMapsSemanticAppearanceTo2dResourcesOutsideUiState() {
        val defaultLayers = SpriteAssetRegistry.layersFor(AvatarAppearance(), AvatarState.IDLE)
        val dressedLayers = SpriteAssetRegistry.layersFor(
            AvatarAppearance(outfitId = "digital_expert", accessoryId = "visor", propId = "shopping_bag"),
            AvatarState.SEARCHING,
        )

        assertNotEquals(0, defaultLayers.baseResId)
        assertNotEquals(0, dressedLayers.baseResId)
        assertFalse(defaultLayers::class.java.declaredFields.any { it.name == "appearance" })
    }

    @Test
    fun stateBuildsRendererAgnosticAvatarStageState() {
        val state = SpriteHomeUiState(
            baseAvatarState = AvatarState.PRESENTING,
            presentingProduct = sampleProduct(),
            animationSequence = 7L,
        )

        val stage = state.toAvatarStageUiState()

        assertEquals(AvatarState.PRESENTING, stage.avatarState)
        assertEquals(state.appearance, stage.appearance)
        assertEquals(state.speechBubble, stage.speechBubble)
        assertEquals("p1", stage.presentingProduct?.productId)
        assertEquals(7L, stage.animationSequence)
    }

    private fun sampleProduct() = com.example.shopguideagent.data.model.ProductUiModel(
        productId = "p1",
        name = "Smart headphones",
        price = 299.0,
        isPrimary = true,
    )
}
