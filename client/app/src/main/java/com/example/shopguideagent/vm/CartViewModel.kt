package com.example.shopguideagent.vm

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.local.CartPersistenceStore
import com.example.shopguideagent.data.local.InMemoryCartPersistenceStore
import com.example.shopguideagent.data.model.CartItemUiModel
import com.example.shopguideagent.data.model.CartUiState
import com.example.shopguideagent.data.model.CheckoutResult
import com.example.shopguideagent.data.model.OrderFlowState
import com.example.shopguideagent.data.model.OrderUiModel
import com.example.shopguideagent.data.model.OrdersUiState
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.selectedItemCount
import com.example.shopguideagent.data.model.selectedTotalPrice
import com.example.shopguideagent.data.remote.CartApiClient
import com.example.shopguideagent.data.remote.OrderApiClient
import com.example.shopguideagent.domain.event.CartOperationEvent
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.util.UUID

class CartViewModel @JvmOverloads constructor(
    private val userIdProvider: () -> String,
    sessionId: String = UserSession.DEFAULT_SESSION_ID,
    private val persistenceStore: CartPersistenceStore = InMemoryCartPersistenceStore(),
    private val cartApiClient: CartApiClient = CartApiClient(),
    private val orderApiClient: OrderApiClient = OrderApiClient(),
    private val operationDispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
) : ViewModel() {

    @JvmOverloads
    constructor(
        userId: String,
        sessionId: String = UserSession.DEFAULT_SESSION_ID,
        persistenceStore: CartPersistenceStore = InMemoryCartPersistenceStore(),
        cartApiClient: CartApiClient = CartApiClient(),
        orderApiClient: OrderApiClient = OrderApiClient(),
        operationDispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
    ) : this(
        userIdProvider = { userId },
        sessionId = sessionId,
        persistenceStore = persistenceStore,
        cartApiClient = cartApiClient,
        orderApiClient = orderApiClient,
        operationDispatcher = operationDispatcher,
    )

    @JvmOverloads
    constructor(
        context: Context,
        sessionId: String = UserSession.DEFAULT_SESSION_ID,
        persistenceStore: CartPersistenceStore = InMemoryCartPersistenceStore(),
        cartApiClient: CartApiClient = CartApiClient(),
        orderApiClient: OrderApiClient = OrderApiClient(),
        operationDispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
    ) : this(
        userIdProvider = { UserSession.get(context).currentUserId.value },
        sessionId = sessionId,
        persistenceStore = persistenceStore,
        cartApiClient = cartApiClient,
        orderApiClient = orderApiClient,
        operationDispatcher = operationDispatcher,
    )
    private var activeSessionId: String = sessionId
    private var cartSyncJob: Job? = null
    private var cartSyncVersion: Long = 0L

    private val _uiState = MutableStateFlow(
        CartUiState(items = persistenceStore.loadCartItems(userIdProvider())).recalculate(),
    )
    val uiState: StateFlow<CartUiState> = _uiState.asStateFlow()

    private val _ordersState = MutableStateFlow(
        OrdersUiState(orders = persistenceStore.loadOrders(userIdProvider())),
    )
    val ordersState: StateFlow<OrdersUiState> = _ordersState.asStateFlow()

    private val _orderFlow = MutableStateFlow<OrderFlowState>(OrderFlowState.Idle)
    val orderFlow: StateFlow<OrderFlowState> = _orderFlow.asStateFlow()

    private val _operationEvents = MutableSharedFlow<CartOperationEvent>(extraBufferCapacity = 64)
    val operationEvents: SharedFlow<CartOperationEvent> = _operationEvents.asSharedFlow()

    init {
        loadCartFromServer()
    }

    fun refresh() {
        loadCartFromServer()
    }

    fun switchSession(sessionId: String, forceRefresh: Boolean = false) {
        if (sessionId.isBlank()) return
        if (sessionId == activeSessionId && !forceRefresh) return
        activeSessionId = sessionId
        loadCartFromServer()
    }

    private fun loadCartFromServer() {
        val sessionForRequest = activeSessionId
        val requestVersion = ++cartSyncVersion
        cartSyncJob?.cancel()
        cartSyncJob = viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, errorMessage = null).recalculate()
            try {
                val items = cartApiClient.getCart(sessionForRequest)
                if (sessionForRequest != activeSessionId || requestVersion != cartSyncVersion) return@launch
                _uiState.value = CartUiState(items = items).recalculate()
                persistenceStore.saveCartItems(userIdProvider(), items)
            } catch (e: Exception) {
                if (sessionForRequest != activeSessionId || requestVersion != cartSyncVersion) return@launch
                val fallbackItems = _uiState.value.items.ifEmpty { persistenceStore.loadCartItems(userIdProvider()) }
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    items = fallbackItems,
                    errorMessage = operationError("购物车同步失败", e),
                ).recalculate()
            }
        }
    }

    fun addProduct(product: ProductUiModel) {
        val item = CartItemUiModel(
            productId = product.productId,
            name = product.name,
            price = product.price,
            quantity = 1,
            imageUrl = product.imageUrl,
            tags = product.tags,
            reason = product.reason,
            stock = product.stock,
        )
        addItem(item)
        viewModelScope.launch(operationDispatcher) {
            try {
                cartApiClient.addToCart(activeSessionId, product)
                _operationEvents.tryEmit(CartOperationEvent.AddToCartSucceeded(product.productId, 1))
            } catch (e: Exception) {
                val message = operationError("????", e)
                _uiState.value = _uiState.value.copy(errorMessage = message).recalculate()
                _operationEvents.tryEmit(CartOperationEvent.AddToCartFailed(product.productId, e.message ?: message))
            }
        }
    }

    fun addItem(item: CartItemUiModel) {
        val current = _uiState.value.items
        val updated = if (current.any { it.productId == item.productId }) {
            current.map {
                if (it.productId == item.productId) it.copy(quantity = it.quantity + item.quantity) else it
            }
        } else {
            current + item
        }
        updateItems(updated, lastRemovedItem = null)
    }

    fun increaseQuantity(productId: String) {
        val currentItem = _uiState.value.items.firstOrNull { it.productId == productId } ?: return
        val updated = _uiState.value.items.map {
            if (it.productId == productId) it.copy(quantity = it.quantity + 1) else it
        }
        updateItems(updated, lastRemovedItem = null)
        viewModelScope.launch {
            try {
                cartApiClient.updateQuantity(activeSessionId, productId, currentItem.quantity + 1)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(errorMessage = operationError("同步失败", e)).recalculate()
            }
        }
    }

    fun decreaseQuantity(productId: String) {
        val currentItem = _uiState.value.items.firstOrNull { it.productId == productId } ?: return
        val updated = _uiState.value.items.mapNotNull {
            when {
                it.productId != productId -> it
                it.quantity > 1 -> it.copy(quantity = it.quantity - 1)
                else -> null
            }
        }
        updateItems(updated, lastRemovedItem = null)
        viewModelScope.launch {
            try {
                if (currentItem.quantity > 1) {
                    cartApiClient.updateQuantity(activeSessionId, productId, currentItem.quantity - 1)
                } else {
                    cartApiClient.removeItem(activeSessionId, productId)
                }
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(errorMessage = operationError("同步失败", e)).recalculate()
            }
        }
    }

    fun remove(productId: String) {
        val removed = _uiState.value.items.firstOrNull { it.productId == productId }
        updateItems(
            items = _uiState.value.items.filterNot { it.productId == productId },
            lastRemovedItem = removed,
        )
        viewModelScope.launch {
            try {
                cartApiClient.removeItem(activeSessionId, productId)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(errorMessage = operationError("同步失败", e)).recalculate()
            }
        }
    }

    fun undoLastRemove() {
        val removed = _uiState.value.lastRemovedItem ?: return
        updateItems(_uiState.value.items + removed, lastRemovedItem = null)
        viewModelScope.launch {
            try {
                cartApiClient.addToCart(activeSessionId, removed.toProduct(), removed.quantity)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(errorMessage = operationError("同步失败", e)).recalculate()
            }
        }
    }

    fun consumeLastRemovedItem() {
        _uiState.value = _uiState.value.copy(lastRemovedItem = null).recalculate()
    }

    fun toggleSelected(productId: String) {
        val currentItem = _uiState.value.items.firstOrNull { it.productId == productId } ?: return
        val newSelected = !currentItem.selected
        updateItems(_uiState.value.items.map {
            if (it.productId == productId) it.copy(selected = newSelected) else it
        })
        viewModelScope.launch {
            try {
                cartApiClient.selectItem(activeSessionId, productId, newSelected)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(errorMessage = operationError("同步失败", e)).recalculate()
            }
        }
    }

    fun setAllSelected(selected: Boolean) {
        updateItems(_uiState.value.items.map { it.copy(selected = selected) })
    }

    fun clear() {
        updateItems(emptyList(), lastRemovedItem = null)
        viewModelScope.launch {
            try {
                cartApiClient.clearCart(activeSessionId)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(errorMessage = operationError("同步失败", e)).recalculate()
            }
        }
    }

    fun showCheckout() {
        _orderFlow.value = OrderFlowState.Idle
        _uiState.value = _uiState.value.copy(showCheckoutSheet = true)
    }

    fun hideCheckout() {
        _uiState.value = _uiState.value.copy(showCheckoutSheet = false)
        _orderFlow.value = OrderFlowState.Idle
    }

    fun checkout() {
        startOrderFlow()
    }

    fun startOrderFlow() {
        val state = _uiState.value
        if (state.selectedCount == 0) {
            _uiState.value = state.copy(errorMessage = "请先选择要结算的商品")
            return
        }
        _uiState.value = state.copy(showCheckoutSheet = true, errorMessage = null).recalculate()
        _orderFlow.value = OrderFlowState.Creating
        viewModelScope.launch(operationDispatcher) {
            val initiated = orderApiClient.initiate(activeSessionId)
            val order = initiated.getOrElse {
                failOrderFlow("结算失败", it)
                return@launch
            }
            val orderId = order.order_id
            if (orderId.isNullOrBlank()) {
                failOrderFlow("结算失败", IllegalStateException("服务端未返回订单号"))
                return@launch
            }
            val addresses = orderApiClient.getAddresses().getOrElse {
                failOrderFlow("地址加载失败", it)
                return@launch
            }
            _orderFlow.value = OrderFlowState.AddressRequired(
                orderId = orderId,
                addresses = addresses,
            )
        }
    }

    fun selectAddress(addressId: String) {
        val current = _orderFlow.value as? OrderFlowState.AddressRequired ?: return
        val address = current.addresses.firstOrNull { it.addressId == addressId }
        if (address == null) {
            _orderFlow.value = current.copy(errorMessage = "请选择有效地址")
            return
        }
        _orderFlow.value = current.copy(isLoading = true, errorMessage = null)
        viewModelScope.launch(operationDispatcher) {
            val selected = orderApiClient.selectAddress(current.orderId, addressId).getOrElse {
                _orderFlow.value = current.copy(
                    isLoading = false,
                    errorMessage = operationError("地址选择失败", it),
                )
                return@launch
            }
            val token = selected.confirmation_token
            if (token.isNullOrBlank()) {
                _orderFlow.value = current.copy(
                    isLoading = false,
                    errorMessage = "服务端未返回确认令牌",
                )
                return@launch
            }
            _orderFlow.value = OrderFlowState.OrderPreview(
                orderId = selected.order_id ?: current.orderId,
                confirmationToken = token,
                idempotencyKey = UUID.randomUUID().toString(),
                selectedAddress = address,
                totalAmount = selected.total_amount ?: _uiState.value.totalPrice,
                itemCount = _uiState.value.selectedCount,
            )
        }
    }

    fun confirmOrder() {
        val preview = _orderFlow.value as? OrderFlowState.OrderPreview ?: return
        if (preview.isConfirming) return
        _orderFlow.value = preview.copy(isConfirming = true)
        viewModelScope.launch(operationDispatcher) {
            val confirmed = orderApiClient.confirm(
                orderId = preview.orderId,
                token = preview.confirmationToken,
                idempotencyKey = preview.idempotencyKey,
            ).getOrElse {
                _orderFlow.value = preview.copy(isConfirming = false)
                _uiState.value = _uiState.value.copy(
                    errorMessage = operationError("订单确认失败", it),
                ).recalculate()
                return@launch
            }
            if (confirmed.status != "completed") {
                _orderFlow.value = preview.copy(isConfirming = false)
                _uiState.value = _uiState.value.copy(
                    errorMessage = confirmed.message?.takeIf { it.isNotBlank() } ?: "订单未完成",
                ).recalculate()
                return@launch
            }
            completeOrderLocally(
                orderId = confirmed.order_id ?: preview.orderId,
                paidAmount = confirmed.total_amount ?: preview.totalAmount,
                successMessage = confirmed.message?.takeIf { it.isNotBlank() } ?: "结算成功。",
            )
        }
    }

    fun consumeError() {
        _uiState.value = _uiState.value.copy(errorMessage = null)
    }

    fun consumeCheckoutResult() {
        _uiState.value = _uiState.value.copy(checkoutResult = null)
    }

    private fun updateItems(
        items: List<CartItemUiModel>,
        lastRemovedItem: CartItemUiModel? = _uiState.value.lastRemovedItem,
    ) {
        _uiState.value = _uiState.value.copy(items = items, lastRemovedItem = lastRemovedItem).recalculate()
        persistenceStore.saveCartItems(userIdProvider(), items)
    }

    private fun CartItemUiModel.toProduct(): ProductUiModel = ProductUiModel(
        productId = productId,
        name = name,
        price = price,
        imageUrl = imageUrl,
        tags = tags,
        reason = reason,
        stock = stock,
    )

    private fun completeOrderLocally(orderId: String, paidAmount: Double, successMessage: String) {
        val state = _uiState.value
        val purchasedItems = state.items.filter { it.selected }
        val updatedOrders = listOf(
            OrderUiModel(
                orderId = orderId,
                items = purchasedItems,
                totalCount = selectedItemCount(purchasedItems),
                totalPrice = selectedTotalPrice(purchasedItems),
            ),
        ) + _ordersState.value.orders
        _ordersState.value = _ordersState.value.copy(orders = updatedOrders)
        persistenceStore.saveOrders(userIdProvider(), updatedOrders)
        val remainingItems = state.items.filterNot { it.selected }
        _uiState.value = state.copy(
            items = remainingItems,
            showCheckoutSheet = false,
            checkoutResult = CheckoutResult(orderId, paidAmount),
            errorMessage = null,
        ).recalculate()
        persistenceStore.saveCartItems(userIdProvider(), remainingItems)
        _orderFlow.value = OrderFlowState.OrderSuccess(orderId, successMessage)
    }

    private fun failOrderFlow(prefix: String, error: Throwable) {
        val message = operationError(prefix, error)
        _orderFlow.value = OrderFlowState.OrderError(message)
        _uiState.value = _uiState.value.copy(errorMessage = message).recalculate()
    }

    private fun operationError(prefix: String, error: Throwable): String =
        "$prefix：${error.message?.takeIf { it.isNotBlank() } ?: error.javaClass.simpleName}"
}

private fun CartUiState.recalculate(): CartUiState = CartUiState(
    isLoading = isLoading,
    items = items,
    errorMessage = errorMessage,
    lastRemovedItem = lastRemovedItem,
    showCheckoutSheet = showCheckoutSheet,
    checkoutResult = checkoutResult,
)
