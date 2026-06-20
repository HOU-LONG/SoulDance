package com.example.shopguideagent.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.RealtimeEvent
import com.example.shopguideagent.domain.event.CartOperationEvent
import com.example.shopguideagent.data.repository.InMemorySpiritAppearanceRepository
import com.example.shopguideagent.data.repository.InMemorySpiritProgressRepository
import com.example.shopguideagent.data.repository.SpiritAppearanceRepository
import com.example.shopguideagent.data.repository.SpiritProgressRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class SpriteHomeViewModel(
    initialState: SpriteHomeUiState? = null,
    private val progressRepository: SpiritProgressRepository = InMemorySpiritProgressRepository(),
    private val appearanceRepository: SpiritAppearanceRepository = InMemorySpiritAppearanceRepository(),
) : ViewModel() {
    private val _uiState = MutableStateFlow(
        initialState ?: SpriteHomeUiState(
            spiritProgress = progressRepository.loadProgress(),
            appearance = appearanceRepository.loadAppearance(),
        ),
    )
    val uiState: StateFlow<SpriteHomeUiState> = _uiState.asStateFlow()

    private val _effects = MutableSharedFlow<SpriteHomeEffect>(extraBufferCapacity = 16)
    val effects: SharedFlow<SpriteHomeEffect> = _effects.asSharedFlow()

    private val processedCartEvents = mutableSetOf<String>()
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

    fun onAction(action: SpriteHomeAction) {
        when (action) {
            SpriteHomeAction.DressUpClicked -> {
                setSpeech("装扮功能即将开放")
                emitEffect(SpriteHomeEffect.NavigateToWardrobe)
            }
            SpriteHomeAction.EarnFireClicked -> {
                setSpeech("完成导购任务就能赚火星")
                emitEffect(SpriteHomeEffect.NavigateToTasks)
            }
            SpriteHomeAction.GuideClicked,
            SpriteHomeAction.MenuClicked,
            SpriteHomeAction.CloseClicked -> emitEffect(SpriteHomeEffect.NavigateToGuide)
            SpriteHomeAction.DailyTaskClicked -> handleDailyTaskClicked()
            SpriteHomeAction.NewOutfitClicked -> applyNewOutfit()
            SpriteHomeAction.ProfileClicked -> emitEffect(SpriteHomeEffect.ShowMessage("用户资料暂未开放"))
            SpriteHomeAction.SpeechBubbleClicked -> Unit
            SpriteHomeAction.ProductClicked -> {
                uiState.value.presentingProduct?.productId?.let { emitEffect(SpriteHomeEffect.OpenProduct(it)) }
            }
            SpriteHomeAction.RetryClicked -> setBaseState(AvatarState.SEARCHING)
        }
    }

    fun onChatStateChanged(chatState: ChatUiState) {
        val product = SpriteHomeStateMapper.latestProduct(chatState)
        val transient = SpriteHomeStateMapper.transientAvatarStateFromChatState(chatState)
        val base = SpriteHomeStateMapper.baseAvatarStateFromChatState(chatState)
        _uiState.update { current ->
            val nextTransient = transient ?: current.transientAvatarState
            val nextProduct = product ?: current.presentingProduct
            val displayed = nextTransient ?: base
            current.copy(
                baseAvatarState = base,
                transientAvatarState = nextTransient,
                presentingProduct = nextProduct,
                speechBubble = SpriteHomeStateMapper.speechFor(displayed, nextProduct),
                animationSequence = current.animationSequence + if (displayed != current.displayedAvatarState) 1 else 0,
            )
        }
    }

    fun onRealtimeEvent(event: RealtimeEvent) {
        when (event) {
            is RealtimeEvent.ProductsStart -> onProductsStart(event.expectedCount)
            is RealtimeEvent.ProductItem -> onProductItem(event.index, event.product)
            is RealtimeEvent.ProductsDone -> onProductsDone()
            is RealtimeEvent.CartUpdate -> if (event.success) {
                rewardAddToCart(cartEventKey(event))
            }
            is RealtimeEvent.Error -> setTransientState(AvatarState.ERROR, SpeechBubbleUiState(event.message, style = SpeechBubbleStyle.ERROR))
            else -> Unit
        }
    }

    fun onVoiceRecordingStarted() {
        setBaseState(AvatarState.LISTENING)
    }

    fun onRequestSent() {
        setBaseState(AvatarState.SEARCHING)
    }

    fun onCartOperationEvent(event: CartOperationEvent) {
        when (event) {
            is CartOperationEvent.AddToCartSucceeded -> rewardAddToCart(eventKey = null)
            is CartOperationEvent.AddToCartFailed -> Unit
        }
    }

    fun onLocalAddToCartSuccess() {
        // Kept for binary/source compatibility with older callers; sprite growth is driven by CartOperationEvent.
    }

    fun onDressClicked() {
        onAction(SpriteHomeAction.DressUpClicked)
    }

    fun onEarnFireClicked() {
        onAction(SpriteHomeAction.EarnFireClicked)
    }

    fun onDailyTaskClicked() {
        onAction(SpriteHomeAction.DailyTaskClicked)
    }

    fun onStageAnimationFinished() {
        _uiState.update { current ->
            val stable = current.baseAvatarState
            current.copy(
                transientAvatarState = null,
                speechBubble = SpriteHomeStateMapper.speechFor(stable, current.presentingProduct),
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun onProductsStart(expectedCount: Int) {
        _uiState.update { current ->
            val nextBase = AvatarState.SEARCHING
            current.copy(
                baseAvatarState = nextBase,
                speechBubble = SpriteHomeStateMapper.speechFor(current.transientAvatarState ?: nextBase, current.presentingProduct),
                productPresentation = ProductPresentationUiState(expectedCount = expectedCount.coerceAtLeast(0)),
                isLoading = true,
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun onProductItem(index: Int, product: ProductUiModel) {
        _uiState.update { current ->
            val currentPresentation = current.productPresentation
            val nextPrimary = when {
                product.isPrimary -> product
                currentPresentation.primaryProduct == null -> product
                else -> currentPresentation.primaryProduct
            }
            val shouldBeAlternative = nextPrimary.productId != product.productId
            val alternatives = if (shouldBeAlternative && currentPresentation.alternatives.none { it.productId == product.productId }) {
                (currentPresentation.alternatives + product).take(2)
            } else {
                currentPresentation.alternatives
            }
            val nextBase = AvatarState.PRESENTING
            val nextPresentation = currentPresentation.copy(
                primaryProduct = nextPrimary,
                alternatives = alternatives,
                receivedCount = (currentPresentation.receivedCount + 1).coerceAtLeast(index + 1),
            )
            current.copy(
                baseAvatarState = nextBase,
                presentingProduct = nextPrimary,
                productPresentation = nextPresentation,
                speechBubble = SpriteHomeStateMapper.speechFor(current.transientAvatarState ?: nextBase, nextPrimary),
                isLoading = false,
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun onProductsDone() {
        _uiState.update { current ->
            val nextBase = if (current.productPresentation.primaryProduct != null || current.presentingProduct != null) {
                AvatarState.PRESENTING
            } else {
                current.baseAvatarState
            }
            current.copy(
                baseAvatarState = nextBase,
                productPresentation = current.productPresentation.copy(completed = true),
                dailyTask = current.dailyTask.incrementProgress(),
                speechBubble = SpriteHomeStateMapper.speechFor(current.transientAvatarState ?: nextBase, current.presentingProduct),
                isLoading = false,
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun setBaseState(avatarState: AvatarState) {
        _uiState.update { current ->
            current.copy(
                baseAvatarState = avatarState,
                speechBubble = SpriteHomeStateMapper.speechFor(current.transientAvatarState ?: avatarState, current.presentingProduct),
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun setTransientState(avatarState: AvatarState, speechBubble: SpeechBubbleUiState = SpriteHomeStateMapper.speechFor(avatarState, _uiState.value.presentingProduct)) {
        _uiState.update { current ->
            current.copy(
                transientAvatarState = avatarState,
                speechBubble = speechBubble,
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun rewardAddToCart(eventKey: String?) {
        if (eventKey != null && !processedCartEvents.add(eventKey)) return
        var progressToSave: SpiritProgressUiState? = null
        _uiState.update { current ->
            val intimacyTotal = current.spiritProgress.currentIntimacy + SpriteHomeRewards.ADD_TO_CART_INTIMACY
            val levelUp = intimacyTotal >= current.spiritProgress.requiredIntimacy && current.spiritProgress.requiredIntimacy > 0
            val nextTransient = if (levelUp) AvatarState.LEVEL_UP else AvatarState.CELEBRATING
            val nextLevel = if (levelUp) current.spiritProgress.level + 1 else current.spiritProgress.level
            val nextProgress = current.spiritProgress.copy(
                level = nextLevel,
                currentIntimacy = if (levelUp) 0 else intimacyTotal,
            )
            progressToSave = nextProgress
            current.copy(
                transientAvatarState = nextTransient,
                userProfile = current.userProfile.copy(firePoints = current.userProfile.firePoints + SpriteHomeRewards.ADD_TO_CART_FIRE),
                spiritProgress = nextProgress,
                speechBubble = SpriteHomeStateMapper.speechFor(nextTransient, current.presentingProduct),
                animationSequence = current.animationSequence + 1,
            )
        }
        progressToSave?.let(progressRepository::saveProgress)
        if (_uiState.value.transientAvatarState == AvatarState.LEVEL_UP) {
            emitEffect(SpriteHomeEffect.ShowLevelUpReward(_uiState.value.spiritProgress.level))
        }
    }

    private fun handleDailyTaskClicked() {
        val task = uiState.value.dailyTask
        if (task.completed && !task.claimed) {
            _uiState.update { current ->
                current.copy(
                    dailyTask = current.dailyTask.copy(claimed = true),
                    userProfile = current.userProfile.copy(firePoints = current.userProfile.firePoints + current.dailyTask.rewardFirePoints),
                    speechBubble = SpeechBubbleUiState("任务奖励已领取", style = SpeechBubbleStyle.SUCCESS),
                    animationSequence = current.animationSequence + 1,
                )
            }
            emitEffect(SpriteHomeEffect.ShowMessage("任务奖励已领取"))
        } else {
            setSpeech("去聊天页完成一次导购吧")
            emitEffect(SpriteHomeEffect.NavigateToTasks)
        }
    }

    private fun applyNewOutfit() {
        var appearanceToSave: AvatarAppearance? = null
        _uiState.update { current ->
            val hint = current.newOutfitHint ?: return@update current
            val nextAppearance = current.appearance.copy(outfitId = hint.outfitId)
            appearanceToSave = nextAppearance
            current.copy(
                appearance = nextAppearance,
                newOutfitHint = null,
                speechBubble = SpeechBubbleUiState("已换上${hint.title}装扮", style = SpeechBubbleStyle.SUCCESS),
                animationSequence = current.animationSequence + 1,
            )
        }
        appearanceToSave?.let(appearanceRepository::saveAppearance)
    }

    private fun setSpeech(text: String) {
        _uiState.update { current -> current.copy(speechBubble = current.speechBubble.copy(text = text, visible = true)) }
    }

    private fun emitEffect(effect: SpriteHomeEffect) {
        _effects.tryEmit(effect)
    }

    private fun DailyTaskUiState.incrementProgress(): DailyTaskUiState {
        if (claimed) return this
        val nextCount = (currentCount + 1).coerceAtMost(targetCount)
        return copy(currentCount = nextCount, completed = targetCount > 0 && nextCount >= targetCount)
    }

    private fun cartEventKey(event: RealtimeEvent.CartUpdate): String =
        listOf(event.messageId, event.action, event.productId ?: "").joinToString(":")
}
