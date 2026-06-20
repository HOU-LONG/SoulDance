package com.example.shopguideagent.ui.home

import com.example.shopguideagent.data.model.ChatExperiencePhase
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.data.model.MessageRole
import com.example.shopguideagent.data.model.ProductUiModel
import org.junit.Assert.assertEquals
import org.junit.Test

class SpriteHomeStateMapperTest {
    @Test
    fun assistantThinkingMapsToSearching() {
        val state = ChatUiState(phase = ChatExperiencePhase.AssistantThinking, isSending = true)

        assertEquals(AvatarState.SEARCHING, SpriteHomeStateMapper.avatarStateFromChatState(state))
    }

    @Test
    fun productInLatestAssistantMessageMapsToPresenting() {
        val state = ChatUiState(
            phase = ChatExperiencePhase.RecommendationReady,
            messages = listOf(
                ChatMessageUiModel(
                    id = "assistant_1",
                    role = MessageRole.Assistant,
                    products = listOf(sampleProduct()),
                ),
            ),
        )

        assertEquals(AvatarState.PRESENTING, SpriteHomeStateMapper.avatarStateFromChatState(state))
        assertEquals(sampleProduct(), SpriteHomeStateMapper.latestProduct(state))
    }

    @Test
    fun errorPhaseMapsToError() {
        val state = ChatUiState(phase = ChatExperiencePhase.Error, errorMessage = "bad network")

        assertEquals(AvatarState.ERROR, SpriteHomeStateMapper.avatarStateFromChatState(state))
    }

    private fun sampleProduct(): ProductUiModel = ProductUiModel(
        productId = "p1",
        name = "Smart headphones",
        price = 299.0,
        isPrimary = true,
    )
}
