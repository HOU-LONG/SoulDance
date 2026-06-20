package com.example.shopguideagent.ui.home

sealed interface SpriteHomeAction {
    object DressUpClicked : SpriteHomeAction
    object EarnFireClicked : SpriteHomeAction
    object GuideClicked : SpriteHomeAction
    object DailyTaskClicked : SpriteHomeAction
    object NewOutfitClicked : SpriteHomeAction
    object MenuClicked : SpriteHomeAction
    object CloseClicked : SpriteHomeAction
    object ProfileClicked : SpriteHomeAction
    object SpeechBubbleClicked : SpriteHomeAction
    object ProductClicked : SpriteHomeAction
    object RetryClicked : SpriteHomeAction
}
