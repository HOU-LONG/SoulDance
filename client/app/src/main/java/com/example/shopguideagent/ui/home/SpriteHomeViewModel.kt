package com.example.shopguideagent.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.data.model.RealtimeEvent
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class SpriteHomeViewModel(
    initialState: SpriteHomeUiState = SpriteHomeUiState(),
) : ViewModel() {
    private val _uiState = MutableStateFlow(initialState)
    val uiState: StateFlow<SpriteHomeUiState> = _uiState.asStateFlow()
    private var realtimeEventJob: Job? = null

    fun bindRealtimeEvents(events: Flow<RealtimeEvent>) {
        realtimeEventJob?.cancel()
        realtimeEventJob = viewModelScope.launch {
            events.collect { onRealtimeEvent(it) }
        }
    }

    override fun onCleared() {
        realtimeEventJob?.cancel()
        super.onCleared()
    }

    fun onChatStateChanged(chatState: ChatUiState) {
        val mapped = SpriteHomeStateMapper.avatarStateFromChatState(chatState)
        val product = SpriteHomeStateMapper.latestProduct(chatState)
        _uiState.update { current ->
            val keepTransient = current.avatarState in TRANSIENT_STATES && mapped != AvatarState.ERROR
            val nextState = if (keepTransient) current.avatarState else mapped
            current.copy(
                avatarState = nextState,
                latestProduct = product ?: current.latestProduct,
                speechText = SpriteHomeStateMapper.speechFor(nextState, product ?: current.latestProduct),
            )
        }
    }

    fun onRealtimeEvent(event: RealtimeEvent) {
        when (event) {
            is RealtimeEvent.ProductsStart -> setState(AvatarState.SEARCHING)
            is RealtimeEvent.ProductItem -> setState(
                AvatarState.PRESENTING,
                latestProduct = event.product,
                speechText = SpriteHomeStateMapper.speechFor(AvatarState.PRESENTING, event.product),
            )
            is RealtimeEvent.ProductsDone -> setState(AvatarState.PRESENTING)
            is RealtimeEvent.CartUpdate -> if (event.success) rewardAddToCart()
            is RealtimeEvent.Error -> setState(AvatarState.ERROR, speechText = event.message)
            else -> Unit
        }
    }

    fun onVoiceRecordingStarted() {
        setState(AvatarState.LISTENING)
    }

    fun onRequestSent() {
        setState(AvatarState.SEARCHING)
    }

    fun onLocalAddToCartSuccess() {
        rewardAddToCart()
    }

    fun onDressClicked() {
        _uiState.update { current -> current.copy(speechText = "\u88c5\u626e\u529f\u80fd\u5373\u5c06\u5f00\u653e") }
    }

    fun onEarnFireClicked() {
        _uiState.update { current -> current.copy(speechText = "\u5b8c\u6210\u5bfc\u8d2d\u4efb\u52a1\u5c31\u80fd\u8d5a\u706b\u661f") }
    }

    fun onDailyTaskClicked() {
        _uiState.update { current -> current.copy(speechText = "\u53bb\u804a\u5929\u9875\u5b8c\u6210\u4e00\u6b21\u5bfc\u8d2d\u5427") }
    }

    fun onStageAnimationFinished() {
        _uiState.update { current ->
            val stable = when {
                current.latestProduct != null -> AvatarState.PRESENTING
                else -> AvatarState.IDLE
            }
            current.copy(
                avatarState = stable,
                speechText = SpriteHomeStateMapper.speechFor(stable, current.latestProduct),
            )
        }
    }

    private fun setState(
        avatarState: AvatarState,
        latestProduct: com.example.shopguideagent.data.model.ProductUiModel? = null,
        speechText: String = SpriteHomeStateMapper.speechFor(avatarState, latestProduct ?: _uiState.value.latestProduct),
    ) {
        _uiState.update { current ->
            current.copy(
                avatarState = avatarState,
                latestProduct = latestProduct ?: current.latestProduct,
                speechText = speechText,
            )
        }
    }

    private fun rewardAddToCart() {
        _uiState.update { current ->
            val intimacyTotal = current.intimacy + SpriteHomeRewards.ADD_TO_CART_INTIMACY
            val levelUp = intimacyTotal >= current.intimacyMax && current.intimacyMax > 0
            current.copy(
                avatarState = if (levelUp) AvatarState.LEVEL_UP else AvatarState.CELEBRATING,
                fireValue = current.fireValue + SpriteHomeRewards.ADD_TO_CART_FIRE,
                intimacy = if (levelUp) 0 else intimacyTotal,
                level = if (levelUp) current.level + 1 else current.level,
                dailyTaskProgress = (current.dailyTaskProgress + 1).coerceAtMost(current.dailyTaskTarget),
                speechText = if (levelUp) {
                    SpriteHomeStateMapper.speechFor(AvatarState.LEVEL_UP)
                } else {
                    SpriteHomeStateMapper.speechFor(AvatarState.CELEBRATING)
                },
            )
        }
    }

    private companion object {
        val TRANSIENT_STATES = setOf(AvatarState.CELEBRATING, AvatarState.LEVEL_UP, AvatarState.ERROR)
    }
}
