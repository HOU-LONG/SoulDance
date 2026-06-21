package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ProductUiModel
import java.io.File

sealed interface SpriteHomeEffect {
    object NavigateToGuide : SpriteHomeEffect
    object NavigateToWardrobe : SpriteHomeEffect
    object NavigateToTasks : SpriteHomeEffect
    object NavigateToChat : SpriteHomeEffect
    object NavigateToCart : SpriteHomeEffect
    data class OpenProduct(val productId: String) : SpriteHomeEffect
    data class ShowProductDetail(val product: ProductUiModel) : SpriteHomeEffect
    data class SendTextMessage(val text: String) : SpriteHomeEffect
    data class SendVoiceMessage(val file: File) : SpriteHomeEffect
    object ToggleSpeaker : SpriteHomeEffect
    data class AddToCart(val product: ProductUiModel) : SpriteHomeEffect
    data class ShowMessage(val message: String) : SpriteHomeEffect
    data class ShowLevelUpReward(val newLevel: Int) : SpriteHomeEffect
}
