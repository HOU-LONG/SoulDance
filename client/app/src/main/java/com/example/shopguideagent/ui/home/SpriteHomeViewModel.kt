package com.example.shopguideagent.ui.home

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.local.FirePointsStore
import com.example.shopguideagent.data.local.InMemoryFirePointsStore
import com.example.shopguideagent.data.model.ChatUiState
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.RealtimeEvent
import com.example.shopguideagent.domain.event.CartOperationEvent
import com.example.shopguideagent.data.repository.InMemorySpiritAppearanceRepository
import com.example.shopguideagent.data.repository.InMemorySpiritProgressRepository
import com.example.shopguideagent.data.repository.SpiritAppearanceRepository
import com.example.shopguideagent.data.repository.SpiritProgressRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
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
    private val firePointsStore: FirePointsStore = InMemoryFirePointsStore(),
    private val userIdProvider: () -> String = { "demo_user_a" },
    private val userSession: UserSession? = null,
) : ViewModel() {

    @JvmOverloads
    constructor(
        context: Context,
        initialState: SpriteHomeUiState? = null,
        progressRepository: SpiritProgressRepository = InMemorySpiritProgressRepository(),
        appearanceRepository: SpiritAppearanceRepository = InMemorySpiritAppearanceRepository(),
        firePointsStore: FirePointsStore = InMemoryFirePointsStore(),
    ) : this(
        initialState = initialState,
        progressRepository = progressRepository,
        appearanceRepository = appearanceRepository,
        firePointsStore = firePointsStore,
        userIdProvider = { UserSession.get(context).currentUserId.value },
        userSession = UserSession.get(context),
    )
    private val _uiState = MutableStateFlow(
        initialState ?: SpriteHomeUiState(
            spiritProgress = progressRepository.loadProgress(),
            appearance = appearanceRepository.loadAppearance(),
        ).copy(
            userProfile = UserProfileUiState(
                firePoints = firePointsStore.load(userIdProvider())
            )
        ),
    )
    val uiState: StateFlow<SpriteHomeUiState> = _uiState.asStateFlow()

    private val _effects = MutableSharedFlow<SpriteHomeEffect>(extraBufferCapacity = 16)
    val effects: SharedFlow<SpriteHomeEffect> = _effects.asSharedFlow()

    private val processedCartEvents = mutableSetOf<String>()
    private val dismissedPresentationProductIds = mutableSetOf<String>()
    private var realtimeEventJob: Job? = null
    private var transientStateResetJob: Job? = null
    private var transientStateGeneration = 0L

    init {
        userSession?.let { session ->
            viewModelScope.launch {
                session.currentUserId.collect {
                    onCurrentUserChanged()
                }
            }
        }
    }

    fun onCurrentUserChanged() {
        val userId = userIdProvider()
        _uiState.update { current ->
            current.copy(
                userProfile = current.userProfile.copy(
                    firePoints = firePointsStore.load(userId)
                )
            )
        }
    }

    fun bindRealtimeEvents(events: Flow<RealtimeEvent>) {
        realtimeEventJob?.cancel()
        realtimeEventJob = viewModelScope.launch {
            events.collect { onRealtimeEvent(it) }
        }
    }

    override fun onCleared() {
        realtimeEventJob?.cancel()
        transientStateResetJob?.cancel()
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
                emitEffect(SpriteHomeEffect.ShowTaskCenter)
            }
            is SpriteHomeAction.TaskClaimed -> handleTaskClaimed(action.taskId)
            SpriteHomeAction.TaskCenterOpened -> emitEffect(SpriteHomeEffect.ShowTaskCenter)
            SpriteHomeAction.TaskCenterClosed -> emitEffect(SpriteHomeEffect.HideTaskCenter)
            SpriteHomeAction.ProductViewedForTask -> incrementTask("browse_recommendations")
            SpriteHomeAction.ProductShared -> incrementTask("share_good_product")
            SpriteHomeAction.ProfileClicked -> emitEffect(SpriteHomeEffect.ShowMessage("用户资料暂未开放"))
            SpriteHomeAction.SpeechBubbleClicked -> Unit
            SpriteHomeAction.ProductClicked -> {
                uiState.value.presentingProduct?.productId?.let { emitEffect(SpriteHomeEffect.OpenProduct(it)) }
            }
            SpriteHomeAction.RetryClicked -> setBaseState(AvatarState.SEARCHING)
            is SpriteHomeAction.TextSubmitted -> emitEffect(SpriteHomeEffect.SendTextMessage(action.text))
            SpriteHomeAction.VoiceRecordingStarted -> onVoiceRecordingStarted()
            is SpriteHomeAction.VoiceFileReady -> emitEffect(SpriteHomeEffect.SendVoiceMessage(action.file))
            SpriteHomeAction.VoiceRecordingCancelled -> setBaseState(AvatarState.IDLE)
            SpriteHomeAction.SpeakerToggled -> emitEffect(SpriteHomeEffect.ToggleSpeaker)
            SpriteHomeAction.ChatModeClicked -> emitEffect(SpriteHomeEffect.NavigateToChat)
            SpriteHomeAction.CartClicked -> emitEffect(SpriteHomeEffect.NavigateToCart)
            SpriteHomeAction.SettingsClicked -> emitEffect(SpriteHomeEffect.ShowMessage("设置暂未开放"))
            SpriteHomeAction.ProductPresentationDismissed -> dismissProductPresentation()
            is SpriteHomeAction.AddToCartClicked -> emitEffect(SpriteHomeEffect.AddToCart(action.product))
            is SpriteHomeAction.ProductDetailClicked -> emitEffect(SpriteHomeEffect.ShowProductDetail(action.product))
            is SpriteHomeAction.QuickActionClicked -> emitEffect(SpriteHomeEffect.SendTextMessage(action.message))
            SpriteHomeAction.HistoryDrawerOpened -> emitEffect(SpriteHomeEffect.OpenHistoryDrawer)
            is SpriteHomeAction.UserSelected -> {
                userSession?.setCurrentUserId(action.userId)
                onCurrentUserChanged()
            }
            SpriteHomeAction.AvatarChangeRequested -> emitEffect(SpriteHomeEffect.OpenHistoryDrawer)
            is SpriteHomeAction.SessionSelected -> emitEffect(SpriteHomeEffect.SelectSession(action.sessionId))
            SpriteHomeAction.NewSessionRequested -> emitEffect(SpriteHomeEffect.CreateNewSession)
            SpriteHomeAction.EditSpiritNameClicked -> emitEffect(SpriteHomeEffect.ShowEditSpiritName)
            is SpriteHomeAction.SpiritNameChanged -> updateSpiritName(action.name)
        }
    }

    fun onChatStateChanged(chatState: ChatUiState) {
        val latestProduct = SpriteHomeStateMapper.latestProduct(chatState)
        val product = latestProduct?.takeUnless { dismissedPresentationProductIds.contains(it.productId) }
        val transient = SpriteHomeStateMapper.transientAvatarStateFromChatState(chatState)
        val mappedBase = SpriteHomeStateMapper.baseAvatarStateFromChatState(chatState)
        val base = if (product == null && mappedBase == AvatarState.PRESENTING) {
            AvatarState.IDLE
        } else {
            mappedBase
        }
        _uiState.update { current ->
            val nextTransient = transient ?: current.transientAvatarState
            val nextProduct = product ?: current.presentingProduct?.takeUnless {
                dismissedPresentationProductIds.contains(it.productId)
            }
            val nextPresentation = if (
                current.productPresentation.primaryProduct?.productId?.let(dismissedPresentationProductIds::contains) == true
            ) {
                ProductPresentationUiState()
            } else {
                current.productPresentation
            }
            val displayed = nextTransient ?: base
            current.copy(
                baseAvatarState = base,
                transientAvatarState = nextTransient,
                presentingProduct = nextProduct,
                productPresentation = nextPresentation,
                speechBubble = SpriteHomeStateMapper.speechFor(displayed, nextProduct),
                animationSequence = current.animationSequence + if (displayed != current.displayedAvatarState) 1 else 0,
            )
        }
    }

    fun onReturnedFromChat() {
        dismissProductPresentation()
    }

    fun onRealtimeEvent(event: RealtimeEvent) {
        when (event) {
            is RealtimeEvent.TextDelta -> onTextDelta()
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

    /**
     * 流式回复文本片段到达：精灵进入思考姿态。已在展示商品时不打断展示。
     * 完整流式气泡文本累积在事件接入阶段(P3)处理。
     */
    private fun onTextDelta() {
        _uiState.update { current ->
            if (current.baseAvatarState == AvatarState.PRESENTING) return@update current
            val nextBase = AvatarState.THINKING
            current.copy(
                baseAvatarState = nextBase,
                speechBubble = SpriteHomeStateMapper.speechFor(current.transientAvatarState ?: nextBase, current.presentingProduct),
                animationSequence = current.animationSequence + if (current.displayedAvatarState != nextBase) 1 else 0,
            )
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
            is CartOperationEvent.AddToCartFailed -> onAddToCartFailed(event.message)
        }
    }

    /**
     * 本地加购失败：精灵进入道歉姿态并提示，base 状态保持不变（商品卡仍在），动画结束后可重试。
     */
    private fun onAddToCartFailed(message: String) {
        val text = message.ifBlank { "加购失败，请重试" }
        setTransientState(AvatarState.ERROR, SpeechBubbleUiState(text, style = SpeechBubbleStyle.ERROR))
        scheduleTransientStateReset()
        emitEffect(SpriteHomeEffect.ShowMessage(text))
    }

    fun onOutfitSelected(outfitId: String) {
        var saved: AvatarAppearance? = null
        _uiState.update { current ->
            if (current.appearance.outfitId == outfitId) return@update current
            val next = current.appearance.copy(outfitId = outfitId)
            saved = next
            current.copy(
                appearance = next,
                speechBubble = SpeechBubbleUiState("换上新装扮啦", style = SpeechBubbleStyle.SUCCESS),
                animationSequence = current.animationSequence + 1,
            )
        }
        saved?.let(appearanceRepository::saveAppearance)
    }

    /** 用户修改精灵名字：更新 UI 状态并持久化。 */
    fun updateSpiritName(name: String) {
        val trimmed = name.trim()
        if (trimmed.isBlank()) return
        var saved: SpiritProgressUiState? = null
        _uiState.update { current ->
            val next = current.spiritProgress.copy(spiritName = trimmed)
            saved = next
            current.copy(
                spiritProgress = next,
                speechBubble = SpeechBubbleUiState("以后叫我 $trimmed 吧", style = SpeechBubbleStyle.SUCCESS),
                animationSequence = current.animationSequence + 1,
            )
        }
        saved?.let(progressRepository::saveProgress)
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
        onAction(SpriteHomeAction.EarnFireClicked)
    }

    fun onStageAnimationFinished() {
        transientStateResetJob?.cancel()
        transientStateGeneration += 1
        _uiState.update { current ->
            val stable = current.baseAvatarState
            current.copy(
                transientAvatarState = null,
                speechBubble = SpriteHomeStateMapper.speechFor(stable, current.presentingProduct),
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun clearTransientAvatarState(expectedGeneration: Long) {
        if (expectedGeneration != transientStateGeneration) return
        _uiState.update { current ->
            val stable = current.baseAvatarState
            current.copy(
                transientAvatarState = null,
                speechBubble = SpriteHomeStateMapper.speechFor(stable, current.presentingProduct),
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun scheduleTransientStateReset(delayMs: Long = 2000L) {
        transientStateResetJob?.cancel()
        transientStateGeneration += 1
        val generation = transientStateGeneration
        transientStateResetJob = viewModelScope.launch(Dispatchers.Main) {
            delay(delayMs)
            clearTransientAvatarState(generation)
        }
    }

    private fun handleTaskClaimed(taskId: String) {
        val task = uiState.value.tasks.find { it.taskId == taskId }
        if (task == null || !task.claimable) return
        val reward = FireRewardCalculator.reward(task.baseFireReward, uiState.value.spiritProgress.level)
        val newFirePoints = uiState.value.userProfile.firePoints + reward
        firePointsStore.save(userIdProvider(), newFirePoints)
        _uiState.update { current ->
            current.copy(
                tasks = current.tasks.map { t ->
                    if (t.taskId == taskId) t.copy(claimed = true) else t
                },
                userProfile = current.userProfile.copy(firePoints = newFirePoints),
                speechBubble = SpeechBubbleUiState("任务奖励已领取", style = SpeechBubbleStyle.SUCCESS),
                animationSequence = current.animationSequence + 1,
            )
        }
        emitEffect(SpriteHomeEffect.ShowClaimedReward(taskId, reward))
    }

    private fun onProductsStart(expectedCount: Int) {
        _uiState.update { current ->
            val nextBase = AvatarState.SEARCHING
            current.copy(
                baseAvatarState = nextBase,
                presentingProduct = null,
                speechBubble = SpriteHomeStateMapper.speechFor(current.transientAvatarState ?: nextBase, null),
                productPresentation = ProductPresentationUiState(expectedCount = expectedCount.coerceAtLeast(0)),
                isLoading = true,
                animationSequence = current.animationSequence + 1,
            )
        }
    }

    private fun onProductItem(index: Int, product: ProductUiModel) {
        dismissedPresentationProductIds.remove(product.productId)
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
                tasks = current.tasks.incrementById("daily_guide_chat"),
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
        transientStateResetJob?.cancel()
        transientStateGeneration += 1
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
        val currentState = uiState.value
        val fireReward = FireRewardCalculator.reward(
            SpriteHomeRewards.ADD_TO_CART_FIRE,
            currentState.spiritProgress.level,
        )
        val newFirePoints = currentState.userProfile.firePoints + fireReward
        firePointsStore.save(userIdProvider(), newFirePoints)
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
                userProfile = current.userProfile.copy(firePoints = newFirePoints),
                spiritProgress = nextProgress,
                tasks = current.tasks.incrementById("add_to_cart"),
                speechBubble = SpriteHomeStateMapper.speechFor(nextTransient, current.presentingProduct),
                animationSequence = current.animationSequence + 1,
            )
        }
        progressToSave?.let(progressRepository::saveProgress)
        if (_uiState.value.transientAvatarState == AvatarState.LEVEL_UP) {
            emitEffect(SpriteHomeEffect.ShowLevelUpReward(_uiState.value.spiritProgress.level))
        }
        scheduleTransientStateReset()
    }

    private fun incrementTask(taskId: String) {
        _uiState.update { current ->
            current.copy(tasks = current.tasks.incrementById(taskId))
        }
    }

    private fun List<TaskUiState>.incrementById(taskId: String): List<TaskUiState> =
        map { if (it.taskId == taskId) it.increment() else it }

    private fun setSpeech(text: String) {
        _uiState.update { current -> current.copy(speechBubble = current.speechBubble.copy(text = text, visible = true)) }
    }

    private fun dismissProductPresentation() {
        val current = _uiState.value
        val productIds = buildSet {
            current.presentingProduct?.productId?.let(::add)
            current.productPresentation.primaryProduct?.productId?.let(::add)
            current.productPresentation.alternatives.forEach { add(it.productId) }
        }
        dismissedPresentationProductIds.addAll(productIds)
        _uiState.update { state ->
            val nextBase = if (state.baseAvatarState == AvatarState.PRESENTING) {
                AvatarState.IDLE
            } else {
                state.baseAvatarState
            }
            val displayed = state.transientAvatarState ?: nextBase
            state.copy(
                baseAvatarState = nextBase,
                presentingProduct = null,
                productPresentation = ProductPresentationUiState(),
                speechBubble = SpriteHomeStateMapper.speechFor(displayed, null),
                animationSequence = state.animationSequence + 1,
            )
        }
    }

    private fun emitEffect(effect: SpriteHomeEffect) {
        _effects.tryEmit(effect)
    }

    private fun cartEventKey(event: RealtimeEvent.CartUpdate): String =
        listOf(event.messageId, event.action, event.productId ?: "").joinToString(":")
}
