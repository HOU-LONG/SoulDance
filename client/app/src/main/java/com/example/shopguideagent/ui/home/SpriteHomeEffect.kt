package com.example.shopguideagent.ui.home

sealed interface SpriteHomeEffect {
    object NavigateToGuide : SpriteHomeEffect
    object NavigateToWardrobe : SpriteHomeEffect
    object NavigateToTasks : SpriteHomeEffect
    data class OpenProduct(val productId: String) : SpriteHomeEffect
    data class ShowMessage(val message: String) : SpriteHomeEffect
    data class ShowLevelUpReward(val newLevel: Int) : SpriteHomeEffect
}
