package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ProductUiModel

object SpriteHomePreviewData {
    val product = ProductUiModel(
        productId = "preview_product",
        name = "智能降噪耳机",
        price = 299.0,
        isPrimary = true,
    )

    val idle = SpriteHomeUiState()

    val searching = SpriteHomeUiState(
        baseAvatarState = AvatarState.SEARCHING,
        speechBubble = SpriteHomeStateMapper.speechFor(AvatarState.SEARCHING),
    )

    val presenting = SpriteHomeUiState(
        baseAvatarState = AvatarState.PRESENTING,
        presentingProduct = product,
        productPresentation = ProductPresentationUiState(primaryProduct = product, expectedCount = 1, receivedCount = 1, completed = true),
        speechBubble = SpriteHomeStateMapper.speechFor(AvatarState.PRESENTING, product),
    )

    val celebrating = presenting.copy(
        transientAvatarState = AvatarState.CELEBRATING,
        speechBubble = SpriteHomeStateMapper.speechFor(AvatarState.CELEBRATING),
    )

    val levelUp = presenting.copy(
        transientAvatarState = AvatarState.LEVEL_UP,
        speechBubble = SpriteHomeStateMapper.speechFor(AvatarState.LEVEL_UP),
    )
}
