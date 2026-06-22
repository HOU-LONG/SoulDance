package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ProductUiModel
import java.io.File

sealed interface SpriteHomeAction {
    object DressUpClicked : SpriteHomeAction
    object EarnFireClicked : SpriteHomeAction
    data class TaskClaimed(val taskId: String) : SpriteHomeAction
    object TaskCenterClosed : SpriteHomeAction
    object ProductViewedForTask : SpriteHomeAction
    object ProductShared : SpriteHomeAction
    object ProfileClicked : SpriteHomeAction
    object SpeechBubbleClicked : SpriteHomeAction
    object ProductClicked : SpriteHomeAction
    object RetryClicked : SpriteHomeAction

    // Voice / chat interactions for the sprite space redesign
    data class TextSubmitted(val text: String) : SpriteHomeAction
    object VoiceRecordingStarted : SpriteHomeAction
    data class VoiceFileReady(val file: File) : SpriteHomeAction
    object VoiceRecordingCancelled : SpriteHomeAction
    object SpeakerToggled : SpriteHomeAction
    object ChatModeClicked : SpriteHomeAction
    object CartClicked : SpriteHomeAction
    object SettingsClicked : SpriteHomeAction
    data class AddToCartClicked(val product: ProductUiModel) : SpriteHomeAction
    data class ProductDetailClicked(val product: ProductUiModel) : SpriteHomeAction
    data class QuickActionClicked(val message: String) : SpriteHomeAction
}
