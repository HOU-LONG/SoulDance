package com.example.shopguideagent.ui.screen

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material.icons.outlined.SmartToy
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.MessageRole
import com.example.shopguideagent.data.model.ChatExperiencePhase
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.profile.userProfileRepository
import com.example.shopguideagent.ui.component.AiMessageBlock
import com.example.shopguideagent.ui.component.AppTopBar
import com.example.shopguideagent.ui.component.ChatHistoryDrawer
import com.example.shopguideagent.ui.component.ChatInputBar
import com.example.shopguideagent.ui.component.MessageBubble
import com.example.shopguideagent.ui.component.ProductDetailBottomSheet
import com.example.shopguideagent.ui.component.ThinkingLogoIndicator
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.AppBackground
import com.example.shopguideagent.ui.theme.AppBackgroundGradientEnd
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.BrandSoft
import com.example.shopguideagent.ui.theme.ShadowColorStrong
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnDark
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary
import com.example.shopguideagent.ui.theme.TextTertiary
import com.example.shopguideagent.vm.ChatViewModel
import com.example.shopguideagent.voice.VoiceInputManager
import com.example.shopguideagent.voice.VoiceInputResult
import com.example.shopguideagent.voice.VoiceInputStateMachine
import com.example.shopguideagent.voice.VoiceInputUiState
import kotlinx.coroutines.launch

object ChatDrawerBackBehavior {
    @JvmStatic
    fun shouldCloseDrawer(drawerOpen: Boolean): Boolean = drawerOpen
}

@Composable
fun ChatScreen(
    chatViewModel: ChatViewModel,
    cartBadgeCount: Int,
    onCartClick: () -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    onVoiceRecordingStarted: () -> Unit = {},
    onMessageSubmitted: () -> Unit = {},
    onAddToCartSuccess: () -> Unit = {},
) {
    val state by chatViewModel.uiState.collectAsState()
    val historyState by chatViewModel.historyState.collectAsState()
    val context = LocalContext.current
    val profileRepository = remember(context) { userProfileRepository(context) }
    val profileState by profileRepository.state.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()
    var selectedProduct by remember { mutableStateOf<ProductUiModel?>(null) }
    var voiceState by remember { mutableStateOf(VoiceInputUiState.Idle) }
    var voiceTranscript by remember { mutableStateOf("") }
    var contentEntered by remember { mutableStateOf(false) }
    val density = LocalDensity.current
    val voiceStateMachine = remember(density) {
        with(density) {
            VoiceInputStateMachine(cancelThresholdPx = (-80).dp.toPx())
        }
    }
    val showJumpToLatest by remember { derivedStateOf { listState.canScrollForward } }
    val latestMessage = state.messages.lastOrNull()

    val voiceManager = remember(context) {
        VoiceInputManager(
            context = context.applicationContext,
            onAmplitude = { /* 可接入波形动画 */ },
            onFinished = { file ->
                voiceState = VoiceInputUiState.Idle
                chatViewModel.sendVoiceMessage(file)
            },
            onError = { message ->
                voiceState = VoiceInputUiState.Idle
                scope.launch { snackbarHostState.showSnackbar(message) }
            },
        )
    }

    fun beginVoiceRecording() {
        onVoiceRecordingStarted()
        voiceState = voiceStateMachine.onPress()
        voiceManager.startRecording()
    }

    val avatarLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri != null) {
            try {
                context.contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            } catch (_: SecurityException) {
                // Some providers do not grant persistable access; the URI is still useful immediately.
            }
            profileRepository.updateAvatarUri(uri.toString())
        }
    }

    val voicePermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            scope.launch { snackbarHostState.showSnackbar("已授权，请重新按住说话") }
        } else {
            scope.launch { snackbarHostState.showSnackbar("需要麦克风权限才能语音输入") }
        }
    }

    fun openAvatarPicker() {
        avatarLauncher.launch(arrayOf("image/*"))
    }

    fun addToCartWithFeedback(product: ProductUiModel) {
        onAddToCart(product)
        scope.launch { snackbarHostState.showSnackbar("已加入购物车") }
    }

    LaunchedEffect(Unit) {
        contentEntered = true
    }
    LaunchedEffect(cartBadgeCount) {
        chatViewModel.updateCartBadge(cartBadgeCount)
    }
    LaunchedEffect(state.errorMessage) {
        val message = state.errorMessage
        if (!message.isNullOrBlank()) {
            snackbarHostState.showSnackbar(message)
            chatViewModel.consumeError()
        }
    }
    LaunchedEffect(
        state.messages.size,
        latestMessage?.id,
        latestMessage?.text?.length,
        latestMessage?.isStreaming,
        state.isSending,
    ) {
        if (state.messages.isNotEmpty()) {
            val shouldFollow = ChatScrollTarget.shouldAutoFollow(
                isSending = state.isSending,
                latestMessageStreaming = latestMessage?.isStreaming == true,
                userAwayFromBottom = listState.canScrollForward,
            )
            if (shouldFollow) {
                listState.animateScrollToItem(ChatScrollTarget.bottomIndex(state.messages.size))
            }
        }
    }
    DisposableEffect(voiceManager) {
        onDispose { voiceManager.release() }
    }

    BackHandler(enabled = ChatDrawerBackBehavior.shouldCloseDrawer(drawerState.isOpen)) {
        scope.launch { drawerState.close() }
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ChatHistoryDrawer(
                state = historyState,
                userAvatarUri = profileState.avatarUri,
                onNewSession = {
                    chatViewModel.newSession()
                    scope.launch { drawerState.close() }
                },
                onSelectSession = {
                    chatViewModel.selectSession(it)
                    scope.launch { drawerState.close() }
                },
                onDeleteSession = {
                    chatViewModel.deleteSession(it)
                },
                onUserAvatarClick = ::openAvatarPicker,
            )
        },
    ) {
        Scaffold(
            topBar = {
                AppTopBar(
                    cartCount = state.cartBadgeCount,
                    onCartClick = onCartClick,
                    onHistoryClick = { scope.launch { drawerState.open() } },
                )
            },
            snackbarHost = { SnackbarHost(snackbarHostState) },
            bottomBar = {
                ChatInputBar(
                    enabled = !state.isSending,
                    onSend = { text ->
                        onMessageSubmitted()
                        chatViewModel.sendMessageStreaming(text)
                    },
                    voiceState = voiceState,
                    voiceTranscript = voiceTranscript,
                    recognitionState = state.voiceRecognitionState,
                    recognitionMessage = state.voiceRecognitionMessage,
                    speakerEnabled = state.isSpeakerEnabled,
                    onSpeakerToggle = {
                        chatViewModel.setSpeakerEnabled(!state.isSpeakerEnabled)
                    },
                    onVoicePress = {
                        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                            PackageManager.PERMISSION_GRANTED
                        ) {
                            beginVoiceRecording()
                        } else {
                            voicePermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                        }
                    },
                    onVoiceDrag = { dragY ->
                        voiceState = voiceStateMachine.onDrag(dragY)
                    },
                    onVoiceRelease = {
                        when (voiceStateMachine.onRelease()) {
                            VoiceInputResult.Submit -> voiceManager.finishRecording()
                            VoiceInputResult.Cancel -> voiceManager.cancelRecording()
                            VoiceInputResult.None -> Unit
                        }
                        voiceState = VoiceInputUiState.Idle
                    },
                )
            },
            containerColor = AppBackground,
        ) { paddingValues ->
            AnimatedVisibility(
                visible = contentEntered,
                enter = fadeIn(animationSpec = tween(280)) +
                    slideInVertically(animationSpec = tween(320), initialOffsetY = { it / 10 }),
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(
                            Brush.verticalGradient(
                                colors = listOf(AppBackground, AppBackgroundGradientEnd),
                            ),
                        )
                        .padding(paddingValues)
                        .padding(horizontal = 20.dp),
                ) {
                    if (state.messages.isEmpty()) {
                        ChatEmptyState(
                            modifier = Modifier.align(Alignment.Center),
                        )
                    } else {
                        LazyColumn(
                            state = listState,
                            modifier = Modifier.fillMaxSize(),
                            verticalArrangement = Arrangement.spacedBy(16.dp),
                        ) {
                            item { Spacer(modifier = Modifier.height(8.dp)) }
                            itemsIndexed(state.messages, key = { _, it -> it.id }) { index, message ->
                                val staggerDelay = (index * 40).coerceAtMost(200)
                                val visible by remember(contentEntered, state.messages.size) {
                                    mutableStateOf(true)
                                }
                                AnimatedVisibility(
                                    visible = visible,
                                    enter = fadeIn(tween(300, delayMillis = staggerDelay)) +
                                        slideInVertically(tween(350, delayMillis = staggerDelay)) { it / 8 },
                                ) {
                                    if (message.role == MessageRole.User) {
                                        MessageBubble(
                                            message = message,
                                            userAvatarUri = profileState.avatarUri,
                                            onUserAvatarClick = ::openAvatarPicker,
                                            modifier = Modifier.fillMaxWidth(),
                                        )
                                    } else {
                                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                            AiMessageBlock(
                                                message = message,
                                                onProductClick = { selectedProduct = it },
                                                onAddToCart = ::addToCartWithFeedback,
                                                onQuickAction = { action ->
                                                    val focus = message.products.firstOrNull { it.isPrimary }
                                                        ?: message.products.firstOrNull()
                                                    onMessageSubmitted()
                                                    if (focus != null) {
                                                        chatViewModel.sendProductFollowUp(focus, action)
                                                    } else {
                                                        chatViewModel.sendMessageStreaming(action)
                                                    }
                                                },
                                                onAddBundleProduct = ::addToCartWithFeedback,
                                                modifier = Modifier.fillMaxWidth(),
                                            )
                                            if (message.isStreaming) {
                                                ThinkingLogoIndicator()
                                            }
                                            if (
                                                state.phase == ChatExperiencePhase.Error &&
                                                !state.retryMessageText.isNullOrBlank() &&
                                                message.id == latestMessage?.id
                                            ) {
                                                RetryInlineAction(
                                                    onRetry = {
                                                        onMessageSubmitted()
                                                        chatViewModel.sendMessageStreaming(state.retryMessageText.orEmpty())
                                                    },
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                            item { Spacer(modifier = Modifier.height(24.dp)) }
                        }
                    }

                    // Jump-to-bottom FAB with scale animation
                    AnimatedVisibility(
                        visible = showJumpToLatest && state.messages.isNotEmpty(),
                        modifier = Modifier
                            .align(Alignment.BottomEnd)
                            .padding(bottom = 16.dp),
                        enter = fadeIn(tween(200)) + slideInVertically(tween(250)) { it / 2 },
                    ) {
                        val fabScale by rememberInfiniteTransition(label = "fabPulse").animateFloat(
                            initialValue = 1f,
                            targetValue = 1.03f,
                            animationSpec = infiniteRepeatable(
                                animation = tween(1200),
                                repeatMode = RepeatMode.Reverse,
                            ),
                            label = "fabPulseScale",
                        )
                        Surface(
                            modifier = Modifier
                                .scale(fabScale)
                                .clickableWithScale {
                                    scope.launch {
                                        listState.animateScrollToItem(ChatScrollTarget.bottomIndex(state.messages.size))
                                    }
                                },
                            color = BrandPrimary,
                            contentColor = TextOnDark,
                            shape = CircleShape,
                            shadowElevation = 6.dp,
                            tonalElevation = 2.dp,
                        ) {
                            Icon(
                                imageVector = Icons.Outlined.KeyboardArrowDown,
                                contentDescription = "跳到底部",
                                modifier = Modifier
                                    .size(48.dp)
                                    .padding(12.dp),
                            )
                        }
                    }
                }
            }
        }
    }

    selectedProduct?.let { product ->
        ProductDetailBottomSheet(
            product = product,
            onDismiss = { selectedProduct = null },
            onAddToCart = ::addToCartWithFeedback,
            onFollowUp = { followUp ->
                onMessageSubmitted()
                chatViewModel.sendProductFollowUp(product, followUp)
                selectedProduct = null
            },
        )
    }
}

@Composable
private fun RetryInlineAction(onRetry: () -> Unit) {
    Surface(
        color = BrandSoft,
        shape = CircleShape,
        tonalElevation = 1.dp,
        modifier = Modifier.padding(start = 52.dp),
    ) {
        TextButton(onClick = onRetry) {
            Text(
                text = "Retry",
                color = BrandPrimary,
                style = MaterialTheme.typography.labelLarge,
            )
        }
    }
}

@Composable
private fun ChatEmptyState(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.padding(horizontal = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Surface(
            shape = CircleShape,
            color = BrandSoft,
            modifier = Modifier.size(80.dp),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(
                    imageVector = Icons.Outlined.SmartToy,
                    contentDescription = null,
                    tint = BrandPrimary,
                    modifier = Modifier.size(40.dp),
                )
            }
        }
        Text(
            text = "你好，我是尚评",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
            color = TextPrimary,
        )
        Text(
            text = "告诉我你想买什么，我来帮你挑选最合适的商品",
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary,
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "试试这样说：\n• 我想买一台性价比高的笔记本电脑\n• 推荐几款适合送礼的茶叶\n• 200元左右的蓝牙耳机",
            style = MaterialTheme.typography.bodySmall,
            color = TextTertiary,
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun ChatScreenPreview() {
    ShopGuideAgentTheme {
        ChatScreen(
            chatViewModel = ChatViewModel(),
            cartBadgeCount = 0,
            onCartClick = {},
            onAddToCart = {},
        )
    }
}
