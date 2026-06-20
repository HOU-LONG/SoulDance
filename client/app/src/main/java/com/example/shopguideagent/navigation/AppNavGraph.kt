package com.example.shopguideagent.navigation

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
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
import com.example.shopguideagent.data.repository.SharedPreferencesSpiritAppearanceRepository
import com.example.shopguideagent.data.repository.SharedPreferencesSpiritProgressRepository
import com.example.shopguideagent.ui.home.SpriteHomeEffect
import com.example.shopguideagent.ui.home.SpriteHomeRoute
import com.example.shopguideagent.ui.home.SpriteHomeViewModel
import com.example.shopguideagent.ui.screen.CartScreen
import com.example.shopguideagent.ui.screen.ChatScreen
import com.example.shopguideagent.ui.screen.OrdersScreen
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
            AppRoute.Cart -> AppRoute.Chat
            AppRoute.Orders -> AppRoute.Cart
        }
}

@Composable
fun AppNavGraph() {
    val context = LocalContext.current
    var route by rememberSaveable { mutableStateOf(AppRoute.Home) }
    val chatViewModel = remember {
        ChatViewModel(
            productCatalog = AndroidAssetProductCatalog(context.assets),
            historyRepository = chatHistoryRepository(context),
        )
    }
    val cartStore = remember { SharedPreferencesCartPersistenceStore(context) }
    val cartViewModel: CartViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return CartViewModel(persistenceStore = cartStore) as T
            }
        },
    )
    val spiritPreferences = remember { SpiritPreferencesDataSource(context) }
    val spriteHomeViewModel: SpriteHomeViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return SpriteHomeViewModel(
                    progressRepository = SharedPreferencesSpiritProgressRepository(spiritPreferences),
                    appearanceRepository = SharedPreferencesSpiritAppearanceRepository(spiritPreferences),
                ) as T
            }
        },
    )
    val chatState by chatViewModel.uiState.collectAsState()
    val cartState by cartViewModel.uiState.collectAsState()

    LaunchedEffect(chatViewModel) {
        spriteHomeViewModel.bindRealtimeEvents(chatViewModel.realtimeEvents)
    }

    LaunchedEffect(chatState) {
        spriteHomeViewModel.onChatStateChanged(chatState)
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

    BackHandler(enabled = AppRouteBackStack.previousRoute(route) != null) {
        AppRouteBackStack.previousRoute(route)?.let { route = it }
    }

    when (route) {
        AppRoute.Home -> SpriteHomeRoute(
            viewModel = spriteHomeViewModel,
            onEffect = { effect ->
                when (effect) {
                    SpriteHomeEffect.NavigateToGuide -> route = AppRoute.Chat
                    SpriteHomeEffect.NavigateToWardrobe -> route = AppRoute.Wardrobe
                    SpriteHomeEffect.NavigateToTasks -> route = AppRoute.Tasks
                    is SpriteHomeEffect.OpenProduct -> route = AppRoute.Chat
                    is SpriteHomeEffect.ShowMessage -> Unit
                    is SpriteHomeEffect.ShowLevelUpReward -> Unit
                }
            },
        )
        AppRoute.Chat -> ChatScreen(
            chatViewModel = chatViewModel,
            cartBadgeCount = cartState.totalCount,
            onCartClick = { route = AppRoute.Cart },
            onAddToCart = cartViewModel::addProduct,
            onVoiceRecordingStarted = spriteHomeViewModel::onVoiceRecordingStarted,
            onMessageSubmitted = spriteHomeViewModel::onRequestSent,
        )
        AppRoute.Wardrobe -> PlaceholderRoute(
            title = "装扮衣橱",
            message = "正式换装系统下一阶段接入",
            onBackClick = { route = AppRoute.Home },
        )
        AppRoute.Tasks -> PlaceholderRoute(
            title = "任务中心",
            message = "完成一次导购对话后可回到首页领取奖励",
            onBackClick = { route = AppRoute.Home },
        )
        AppRoute.Cart -> CartScreen(
            cartViewModel = cartViewModel,
            onBackClick = { route = AppRoute.Chat },
            onOrdersClick = { route = AppRoute.Orders },
        )
        AppRoute.Orders -> OrdersScreen(
            cartViewModel = cartViewModel,
            onBackClick = { route = AppRoute.Cart },
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
