package com.example.shopguideagent.navigation

import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.shopguideagent.data.catalog.AndroidAssetProductCatalog
import com.example.shopguideagent.data.history.chatHistoryRepository
import com.example.shopguideagent.data.local.SharedPreferencesCartPersistenceStore
import com.example.shopguideagent.data.local.SpiritPreferencesDataSource
import com.example.shopguideagent.data.profile.userProfileRepository
import com.example.shopguideagent.data.repository.SharedPreferencesSpiritAppearanceRepository
import com.example.shopguideagent.data.repository.SharedPreferencesSpiritProgressRepository
import com.example.shopguideagent.ui.home.SpriteHomeEffect
import com.example.shopguideagent.ui.home.SpriteHomeRoute
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.ui.home.AvatarState
import com.example.shopguideagent.ui.home.ProductPresentationUiState
import com.example.shopguideagent.ui.home.SpriteHomeStateMapper
import com.example.shopguideagent.ui.home.SpriteHomeUiState
import com.example.shopguideagent.ui.home.SpriteHomeViewModel
import com.example.shopguideagent.ui.home.WardrobeScreen
import com.example.shopguideagent.ui.screen.CartScreen
import com.example.shopguideagent.ui.screen.ChatScreen
import com.example.shopguideagent.ui.screen.OrdersScreen
import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.remote.CartApiClient
import com.example.shopguideagent.data.remote.CartApiService
import com.example.shopguideagent.data.remote.OrderApiClient
import com.example.shopguideagent.data.remote.OrderApiService
import com.example.shopguideagent.data.remote.RealtimeChatWebSocketClient
import com.example.shopguideagent.data.remote.SttApiService
import com.example.shopguideagent.vm.CartViewModel
import com.example.shopguideagent.vm.ChatViewModel

enum class AppRoute {
    Home,
    Chat,
    Wardrobe,
    Tasks,
    Cart,
    Orders,
}

object AppRouteBackStack {
    @JvmStatic
    fun previousRoute(route: AppRoute): AppRoute? =
        when (route) {
            AppRoute.Home -> null
            AppRoute.Chat -> AppRoute.Home
            AppRoute.Wardrobe -> AppRoute.Home
            AppRoute.Tasks -> AppRoute.Home
            AppRoute.Cart -> AppRoute.Home
            AppRoute.Orders -> AppRoute.Cart
        }
}

@Composable
fun AppNavGraph() {
    val context = LocalContext.current
    var route by rememberSaveable { mutableStateOf(AppRoute.Home) }
    val userSession = remember(context) { UserSession.get(context) }
    val currentUserId by userSession.currentUserId.collectAsState()
    val userIdProvider = { currentUserId }
    // Task 1: 使用 viewModel() 替代 remember {}，确保 ChatViewModel 在屏幕旋转等配置变更后存活。
    // 此前 remember {} 会在每次重组时重新创建实例，导致 WebSocket 连接丢失、消息流中断。
    val chatViewModel: ChatViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return ChatViewModel(
                    productCatalog = AndroidAssetProductCatalog(context.assets),
                    historyRepository = chatHistoryRepository(context),
                    wsClient = RealtimeChatWebSocketClient(userIdProvider),
                    sttApi = SttApiService(userIdProvider),
                    userSession = userSession,
                    userIdProvider = userIdProvider,
                ) as T
            }
        },
    )
    val cartStore = remember { SharedPreferencesCartPersistenceStore(context) }
    val cartViewModel: CartViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return CartViewModel(
                    userIdProvider = userIdProvider,
                    persistenceStore = cartStore,
                    cartApiClient = CartApiClient(CartApiService.create(userIdProvider)),
                    orderApiClient = OrderApiClient(OrderApiService.create(userIdProvider)),
                ) as T
            }
        },
    )
    val historyRepository = remember(context) { chatHistoryRepository(context) }
    val profileRepository = remember(context) { userProfileRepository(context) }
    val historyState by historyRepository.state.collectAsState()
    val profileState by profileRepository.state.collectAsState()

    val avatarLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri != null) {
            try {
                context.contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            } catch (_: SecurityException) { }
            profileRepository.updateAvatarUri(uri.toString())
        }
    }

    val spiritPreferences = remember { SpiritPreferencesDataSource(context) }
    val debugInitialState = remember { spriteDebugInitialState(context) }
    val spriteHomeViewModel: SpriteHomeViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return SpriteHomeViewModel(
                    initialState = debugInitialState,
                    progressRepository = SharedPreferencesSpiritProgressRepository(spiritPreferences),
                    appearanceRepository = SharedPreferencesSpiritAppearanceRepository(spiritPreferences),
                ) as T
            }
        },
    )
    val chatState by chatViewModel.uiState.collectAsState()
    val cartState by cartViewModel.uiState.collectAsState()
    val spriteHomeState by spriteHomeViewModel.uiState.collectAsState()

    LaunchedEffect(chatViewModel) {
        spriteHomeViewModel.bindRealtimeEvents(chatViewModel.realtimeEvents)
    }

    LaunchedEffect(chatState) {
        // debug 截图模式（intent extra 注入初始状态）下不让聊天态覆盖注入的展示状态
        if (debugInitialState == null) {
            spriteHomeViewModel.onChatStateChanged(chatState)
        }
    }

    LaunchedEffect(chatState.sessionId, chatState.cartSyncVersion) {
        cartViewModel.switchSession(
            sessionId = chatState.sessionId,
            forceRefresh = chatState.cartSyncVersion > 0L,
        )
    }

    LaunchedEffect(cartViewModel) {
        cartViewModel.operationEvents.collect { spriteHomeViewModel.onCartOperationEvent(it) }
    }

    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    fun showSnackbar(message: String) {
        scope.launch { snackbarHostState.showSnackbar(message) }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { _ ->
        Surface(modifier = Modifier.fillMaxSize()) {
            when (route) {
            AppRoute.Home -> SpriteHomeRoute(
                viewModel = spriteHomeViewModel,
                chatUiState = chatState,
                historyState = historyState,
                currentUserId = currentUserId,
                userAvatarUri = profileState.avatarUri,
                onEffect = { effect ->
                    when (effect) {
                        SpriteHomeEffect.NavigateToGuide,
                        SpriteHomeEffect.NavigateToChat -> route = AppRoute.Chat
                        SpriteHomeEffect.NavigateToWardrobe -> route = AppRoute.Wardrobe
                        SpriteHomeEffect.NavigateToTasks -> route = AppRoute.Tasks
                        SpriteHomeEffect.NavigateToCart -> route = AppRoute.Cart
                        SpriteHomeEffect.NavigateToShare -> showSnackbar("分享功能即将开放")
                        SpriteHomeEffect.ShowTaskCenter -> Unit // handled locally in SpriteHomeRoute
                        SpriteHomeEffect.HideTaskCenter -> Unit // handled locally in SpriteHomeRoute
                        SpriteHomeEffect.OpenHistoryDrawer -> Unit // handled locally in SpriteHomeRoute
                        is SpriteHomeEffect.SwitchUser -> chatViewModel.onUserSwitched(effect.userId)
                        is SpriteHomeEffect.SelectSession -> Unit // handled locally in SpriteHomeRoute
                        SpriteHomeEffect.CreateNewSession -> Unit // handled locally in SpriteHomeRoute
                        SpriteHomeEffect.ShowEditSpiritName -> Unit // handled locally in SpriteHomeRoute
                        is SpriteHomeEffect.OpenProduct -> route = AppRoute.Chat
                        is SpriteHomeEffect.ShowProductDetail -> route = AppRoute.Chat
                        is SpriteHomeEffect.SendTextMessage -> chatViewModel.sendMessageStreaming(effect.text)
                        is SpriteHomeEffect.SendVoiceMessage -> chatViewModel.sendVoiceMessage(effect.file)
                        SpriteHomeEffect.ToggleSpeaker -> chatViewModel.setSpeakerEnabled(!chatState.isSpeakerEnabled)
                        is SpriteHomeEffect.AddToCart -> cartViewModel.addProduct(effect.product)
                        is SpriteHomeEffect.ShowMessage -> showSnackbar(effect.message)
                        is SpriteHomeEffect.ShowLevelUpReward -> Unit
                        is SpriteHomeEffect.ShowClaimedReward -> showSnackbar("任务奖励已领取：${effect.firePoints} 火星")
                    }
                },
                onSwitchUser = { userId -> chatViewModel.onUserSwitched(userId) },
                // Task 13: onUserSelected 已移除——用户切换统一走 SwitchUser effect → onSwitchUser 回调
                onAvatarChangeRequested = { avatarLauncher.launch(arrayOf("image/*")) },
                onNewSession = { chatViewModel.newSession() },
                onSelectSession = { chatViewModel.selectSession(it) },
                onDeleteSession = { chatViewModel.deleteSession(it) },
            )
            AppRoute.Chat -> ChatScreen(
                chatViewModel = chatViewModel,
                cartBadgeCount = cartState.totalCount,
                firePoints = spriteHomeState.userProfile.firePoints,
                onCartClick = { route = AppRoute.Cart },
                onAddToCart = cartViewModel::addProduct,
                onVoiceRecordingStarted = spriteHomeViewModel::onVoiceRecordingStarted,
                onMessageSubmitted = spriteHomeViewModel::onRequestSent,
                onBackToSprite = {
                    spriteHomeViewModel.onReturnedFromChat()
                    route = AppRoute.Home
                },
            )
            AppRoute.Wardrobe -> WardrobeScreen(
                currentOutfitId = spriteHomeState.appearance.outfitId,
                onOutfitSelected = { spriteHomeViewModel.onOutfitSelected(it) },
                onBackClick = { route = AppRoute.Home },
            )
            AppRoute.Tasks -> PlaceholderRoute(
                title = "任务中心",
                message = "完成一次导购对话后可回到首页领取奖励",
                onBackClick = { route = AppRoute.Home },
            )
            AppRoute.Cart -> CartScreen(
                cartViewModel = cartViewModel,
                firePoints = spriteHomeState.userProfile.firePoints,
                onBackClick = { route = AppRoute.Home },
                onOrdersClick = { route = AppRoute.Orders },
            )
            AppRoute.Orders -> OrdersScreen(
                cartViewModel = cartViewModel,
                onBackClick = { route = AppRoute.Cart },
            )
        }
        }

        BackHandler(enabled = AppRouteBackStack.previousRoute(route) != null) {
            AppRouteBackStack.previousRoute(route)?.let { route = it }
        }
    }
}

/**
 * Debug-only：当启动 intent 携带 `sprite_state` extra（如 SEARCHING/PRESENTING）时，注入对应初始状态，
 * 用于无加速模拟器下稳定截取各状态运行截图。正常启动（无该 extra）返回 null，行为完全不变。
 */
private fun spriteDebugInitialState(context: android.content.Context): SpriteHomeUiState? {
    val activity = context as? android.app.Activity ?: return null
    val name = activity.intent?.getStringExtra("sprite_state") ?: return null
    val state = runCatching { AvatarState.valueOf(name) }.getOrNull() ?: return null
    return if (state == AvatarState.PRESENTING) {
        val product = ProductUiModel(
            productId = "debug_preview",
            name = "智能降噪耳机",
            price = 299.0,
            reason = "贴合你的通勤降噪需求，续航与佩戴感都更稳",
            isPrimary = true,
        )
        SpriteHomeUiState(
            baseAvatarState = AvatarState.PRESENTING,
            presentingProduct = product,
            productPresentation = ProductPresentationUiState(
                primaryProduct = product,
                expectedCount = 1,
                receivedCount = 1,
                completed = true,
            ),
            speechBubble = SpriteHomeStateMapper.speechFor(AvatarState.PRESENTING, product),
        )
    } else {
        SpriteHomeUiState(
            baseAvatarState = state,
            speechBubble = SpriteHomeStateMapper.speechFor(state),
        )
    }
}

@Composable
private fun PlaceholderRoute(
    title: String,
    message: String,
    onBackClick: () -> Unit,
) {
    Surface(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            Text(
                message,
                modifier = Modifier.padding(top = 12.dp),
                style = MaterialTheme.typography.bodyLarge,
            )
            Button(
                onClick = onBackClick,
                modifier = Modifier.padding(top = 24.dp),
            ) {
                Text("返回首页")
            }
        }
    }
}
