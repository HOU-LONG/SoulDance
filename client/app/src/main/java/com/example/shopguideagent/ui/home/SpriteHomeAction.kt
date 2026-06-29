package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ProductUiModel
import java.io.File

sealed interface SpriteHomeAction {
    object DressUpClicked : SpriteHomeAction
    object EarnFireClicked : SpriteHomeAction
    data class TaskClaimed(val taskId: String) : SpriteHomeAction
    object TaskCenterOpened : SpriteHomeAction
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
    data class VoiceError(val message: String) : SpriteHomeAction  // Task 3: 语音错误消息，替代 SettingsClicked 占位
    object SpeakerToggled : SpriteHomeAction
    object ChatModeClicked : SpriteHomeAction
    object CartClicked : SpriteHomeAction
    object SettingsClicked : SpriteHomeAction
    object ProductPresentationDismissed : SpriteHomeAction
    data class AddToCartClicked(val product: ProductUiModel) : SpriteHomeAction
    data class ProductDetailClicked(val product: ProductUiModel) : SpriteHomeAction
    data class PalmProductClicked(val product: ProductUiModel) : SpriteHomeAction
    object PalmProductPanelDismissed : SpriteHomeAction
    data class QuickActionClicked(val message: String) : SpriteHomeAction

    // Drawer / user switching / session history
    object HistoryDrawerOpened : SpriteHomeAction
    data class UserSelected(val userId: String) : SpriteHomeAction
    object AvatarChangeRequested : SpriteHomeAction
    data class SessionSelected(val sessionId: String) : SpriteHomeAction
    object NewSessionRequested : SpriteHomeAction

    // Spirit name editing
    object EditSpiritNameClicked : SpriteHomeAction
    data class SpiritNameChanged(val name: String) : SpriteHomeAction

    // Task 7: ProductDetailBottomSheet 交互
    data class ProductAnchorTapped(val productId: String) : SpriteHomeAction
    object DismissProductDetail : SpriteHomeAction
}
