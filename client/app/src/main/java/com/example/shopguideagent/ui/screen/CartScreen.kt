package com.example.shopguideagent.ui.screen

import android.annotation.SuppressLint
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material.icons.outlined.ReceiptLong
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.component.CartItemCard
import com.example.shopguideagent.ui.component.CartSummaryBar
import com.example.shopguideagent.ui.component.CheckoutBottomSheet
import com.example.shopguideagent.ui.component.AddressSelectionSheet
import com.example.shopguideagent.ui.component.EmptyCartView
import com.example.shopguideagent.data.model.OrderFlowState
import com.example.shopguideagent.ui.theme.AppBackground
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.vm.CartViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CartScreen(
    cartViewModel: CartViewModel,
    firePoints: Int,
    onBackClick: () -> Unit,
    onOrdersClick: () -> Unit,
) {
    val state by cartViewModel.uiState.collectAsState()
    val orderFlow by cartViewModel.orderFlow.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    var contentEntered by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        contentEntered = true
    }
    LaunchedEffect(state.errorMessage) {
        val message = state.errorMessage
        if (!message.isNullOrBlank()) {
            snackbarHostState.showSnackbar(message)
            cartViewModel.consumeError()
        }
    }
    LaunchedEffect(state.checkoutResult) {
        state.checkoutResult?.let {
            launch {
                snackbarHostState.showSnackbar(
                    message = "模拟下单成功：${it.orderId}",
                    duration = SnackbarDuration.Indefinite,
                )
            }
            delay(500)
            snackbarHostState.currentSnackbarData?.dismiss()
            cartViewModel.consumeCheckoutResult()
        }
    }
    LaunchedEffect(state.lastRemovedItem?.productId) {
        val removed = state.lastRemovedItem
        if (removed != null) {
            val result = snackbarHostState.showSnackbar(
                message = "Removed ${removed.name}",
                actionLabel = "Undo",
                duration = SnackbarDuration.Short,
            )
            if (result == SnackbarResult.ActionPerformed) {
                cartViewModel.undoLastRemove()
            } else {
                cartViewModel.consumeLastRemovedItem()
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = AppBackground,
                    titleContentColor = TextPrimary,
                ),
                title = {
                    Text(
                        "购物车 · 已选 ${state.selectedCount} 件",
                        fontWeight = FontWeight.SemiBold,
                        style = MaterialTheme.typography.titleMedium,
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBackClick) {
                        Icon(Icons.Outlined.ArrowBack, contentDescription = "返回", tint = BrandPrimary)
                    }
                },
                actions = {
                    IconButton(onClick = onOrdersClick) {
                        Icon(Icons.Outlined.ReceiptLong, contentDescription = "订单", tint = BrandPrimary)
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            AnimatedVisibility(
                visible = state.items.isNotEmpty(),
                enter = fadeIn(tween(250)) + slideInVertically(tween(300)) { it },
            ) {
                CartSummaryBar(
                    state = state,
                    firePoints = firePoints,
                    onToggleAll = cartViewModel::setAllSelected,
                    onCheckout = cartViewModel::showCheckout,
                )
            }
        },
        containerColor = AppBackground,
    ) { paddingValues ->
        if (state.items.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize().padding(paddingValues)) {
                EmptyCartView()
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .background(AppBackground)
                    .padding(paddingValues)
                    .padding(horizontal = 20.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                itemsIndexed(state.items, key = { _, it -> it.productId }) { index, item ->
                    val staggerDelay = (index * 60).coerceAtMost(300)
                    AnimatedVisibility(
                        visible = contentEntered,
                        enter = fadeIn(tween(300, delayMillis = staggerDelay)) +
                            slideInHorizontally(tween(350, delayMillis = staggerDelay)) { it / 4 },
                    ) {
                        CartItemCard(
                            item = item,
                            onToggle = { cartViewModel.toggleSelected(item.productId) },
                            onIncrease = { cartViewModel.increaseQuantity(item.productId) },
                            onDecrease = { cartViewModel.decreaseQuantity(item.productId) },
                            onRemove = { cartViewModel.remove(item.productId) },
                        )
                    }
                }
            }
        }
    }

    if (state.showCheckoutSheet || orderFlow is OrderFlowState.AddressRequired) {
        when (val flow = orderFlow) {
            is OrderFlowState.AddressRequired -> {
                AddressSelectionSheet(
                    state = flow,
                    onDismiss = cartViewModel::hideCheckout,
                    onSelectAddress = cartViewModel::selectAddress,
                )
            }

            is OrderFlowState.OrderPreview -> {
                CheckoutBottomSheet(
                    state = state,
                    firePoints = firePoints,
                    orderFlowState = flow,
                    onDismiss = cartViewModel::hideCheckout,
                    onConfirm = cartViewModel::confirmOrder,
                )
            }

            is OrderFlowState.Creating -> {
                CheckoutBottomSheet(
                    state = state,
                    firePoints = firePoints,
                    orderFlowState = flow,
                    onDismiss = cartViewModel::hideCheckout,
                    onConfirm = {},
                )
            }

            else -> {
                CheckoutBottomSheet(
                    state = state,
                    firePoints = firePoints,
                    onDismiss = cartViewModel::hideCheckout,
                    onConfirm = cartViewModel::checkout,
                )
            }
        }
    }
}

@SuppressLint("ViewModelConstructorInComposable")
@Preview(showBackground = true)
@Composable
private fun CartScreenPreview() {
    ShopGuideAgentTheme {
        CartScreen(cartViewModel = CartViewModel(userId = "demo_user_a"), firePoints = 886, onBackClick = {}, onOrdersClick = {})
    }
}
