package com.example.shopguideagent.ui.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

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
    fun spriteHomeScreenDoesNotUseNegativePadding() {
        val source = findRepoFile("client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt")
            .readText()

        assertFalse("Use offset for decorative off-screen placement instead of negative padding", source.contains("padding(end = (-"))
        assertFalse("Use offset for decorative off-screen placement instead of negative padding", source.contains("top = (-"))
    }

    @Test
    fun defaultStateDoesNotExposeNewOutfitHint() {
        assertFalse(SpriteHomeUiState::class.java.declaredFields.any { it.name == "newOutfitHint" })
    }

    @Test
    fun idleStateDoesNotShowDefaultSpeechBubble() {
        val defaultBubble = SpriteHomeUiState().speechBubble
        val idleBubble = SpriteHomeStateMapper.speechFor(AvatarState.IDLE)

        assertEquals("", defaultBubble.text)
        assertFalse(defaultBubble.visible)
        assertEquals("", idleBubble.text)
        assertFalse(idleBubble.visible)
    }

    @Test
    fun spriteHomeScreenOmitsFloatingReferenceBadges() {
        val source = findRepoFile("client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt")
            .readText()

        assertFalse("Do not render the light spark floating card on the portrait home screen", source.contains("SparkCard("))
        assertFalse("Do not render the football outfit hint on the portrait home screen", source.contains("NewOutfitHintCard("))
    }

    @Test
    fun spriteStageOmitsReferenceOnlyStageDecorations() {
        val source = findRepoFile("client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteStage.kt")
            .readText()

        assertFalse("Do not render the magical toy prop on the sprite stage", source.contains("StageProps("))
        assertFalse("Do not render the blue outfit strip on the sprite stage", source.contains("OutfitLayer("))
        assertFalse("Do not render the blue accessory strip on the sprite stage", source.contains("AccessoryLayer("))
        assertFalse("Do not render the shopping cart prop on the sprite stage", source.contains("PropLayer("))
        assertFalse("Do not keep the visible magical toy copy in the stage", source.contains("神奇玩具"))
        assertFalse("Do not keep the stage shopping cart icon import", source.contains("ShoppingCart"))
        assertFalse("Do not keep the stage smart toy icon import", source.contains("SmartToy"))
    }

    @Test
    fun intimacyPanelDoesNotRenderFeedingShortcutIcon() {
        val source = findRepoFile("client/app/src/main/java/com/example/shopguideagent/ui/home/IntimacyPanel.kt")
            .readText()

        assertFalse("Do not render the tableware shortcut at the right edge of the intimacy bar", source.contains("Restaurant"))
        assertFalse("Do not render the feeding shortcut content description", source.contains("喂食可增加"))
    }

    @Test
    fun topRightControlsAreChatAndSpeakerOnly() {
        val topBar = findRepoFile("client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteTopBar.kt")
            .readText()
        val homeScreen = findRepoFile("client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeScreen.kt")
            .readText()

        assertFalse("Top right controls should not keep a menu action", topBar.contains("onMenuClick"))
        assertFalse("Top right controls should not keep a close/exit action", topBar.contains("Close"))
        assertFalse("Top right controls should not keep the overflow menu icon", topBar.contains("MoreVert"))
        assertTrue("Top right controls should render a chat button", topBar.contains("ChatBubble"))
        assertTrue("Top right controls should render a speaker-on icon", topBar.contains("VolumeUp"))
        assertTrue("Top right controls should render a speaker-off icon", topBar.contains("VolumeOff"))
        assertTrue("Top right controls should expose a speaker toggle callback", topBar.contains("onSpeakerToggle"))
        assertTrue("Home screen should wire chat navigation to the top bar", homeScreen.contains("onChatClick = { onAction(SpriteHomeAction.ChatModeClicked) }"))
        assertTrue("Home screen should wire speaker toggling to the top bar", homeScreen.contains("onSpeakerToggle = { onAction(SpriteHomeAction.SpeakerToggled) }"))
    }

    @Test
    fun spriteVoiceBarLeavesSpeakerToggleToTopBar() {
        val source = findRepoFile("client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteVoiceBar.kt")
            .readText()

        assertFalse("Input bar should be longer because the speaker toggle moved to the top right", source.contains("SpeakerToggle("))
        assertFalse("Input bar should not own the speaker enabled parameter", source.contains("speakerEnabled"))
        assertFalse("Input bar should not own the speaker toggle callback", source.contains("onSpeakerToggle"))
    }

    private fun findRepoFile(relativePath: String): File {
        var current = File(System.getProperty("user.dir")).absoluteFile
        repeat(8) {
            val candidate = File(current, relativePath)
            if (candidate.exists()) return candidate
            current = current.parentFile ?: current
        }
        throw AssertionError("Could not find $relativePath from ${System.getProperty("user.dir")}")
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

    @Test
    fun spriteHomeUiStateUsesTaskListNotDailyTask() {
        val state = SpriteHomeUiState()
        assertFalse(state.tasks.isEmpty())
        assertNull(SpriteHomeUiState::class.java.declaredFields.find { it.name == "dailyTask" })
    }

    private fun sampleProduct() = com.example.shopguideagent.data.model.ProductUiModel(
        productId = "p1",
        name = "Smart headphones",
        price = 299.0,
        isPrimary = true,
    )
}
