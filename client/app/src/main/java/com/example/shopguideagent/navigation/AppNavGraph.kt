package com.example.shopguideagent.navigation

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.shopguideagent.data.catalog.AndroidAssetProductCatalog
import com.example.shopguideagent.data.history.chatHistoryRepository
import com.example.shopguideagent.data.local.SharedPreferencesCartPersistenceStore
import com.example.shopguideagent.ui.home.SpriteHomeScreen
import com.example.shopguideagent.ui.home.SpriteHomeViewModel
import com.example.shopguideagent.ui.screen.CartScreen
import com.example.shopguideagent.ui.screen.ChatScreen
import com.example.shopguideagent.ui.screen.OrdersScreen
import com.example.shopguideagent.vm.CartViewModel
import com.example.shopguideagent.vm.ChatViewModel

enum class AppRoute {
    Home,
    Chat,
    Cart,
    Orders,
}

object AppRouteBackStack {
    @JvmStatic
    fun previousRoute(route: AppRoute): AppRoute? =
        when (route) {
            AppRoute.Home -> null
            AppRoute.Chat -> AppRoute.Home
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
    val spriteHomeViewModel: SpriteHomeViewModel = viewModel()
    val chatState by chatViewModel.uiState.collectAsState()
    val cartState by cartViewModel.uiState.collectAsState()
    val spriteHomeState by spriteHomeViewModel.uiState.collectAsState()

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

    BackHandler(enabled = AppRouteBackStack.previousRoute(route) != null) {
        AppRouteBackStack.previousRoute(route)?.let { route = it }
    }

    when (route) {
        AppRoute.Home -> SpriteHomeScreen(
            state = spriteHomeState,
            onDressClick = spriteHomeViewModel::onDressClicked,
            onEarnFireClick = spriteHomeViewModel::onEarnFireClicked,
            onGuideClick = { route = AppRoute.Chat },
            onDailyTaskClick = {
                spriteHomeViewModel.onDailyTaskClicked()
                route = AppRoute.Chat
            },
            onMenuClick = { route = AppRoute.Chat },
            onCloseClick = { route = AppRoute.Chat },
            onNewOutfitClick = spriteHomeViewModel::onDressClicked,
        )
        AppRoute.Chat -> ChatScreen(
            chatViewModel = chatViewModel,
            cartBadgeCount = cartState.totalCount,
            onCartClick = { route = AppRoute.Cart },
            onAddToCart = cartViewModel::addProduct,
            onVoiceRecordingStarted = spriteHomeViewModel::onVoiceRecordingStarted,
            onMessageSubmitted = spriteHomeViewModel::onRequestSent,
            onAddToCartSuccess = spriteHomeViewModel::onLocalAddToCartSuccess,
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
