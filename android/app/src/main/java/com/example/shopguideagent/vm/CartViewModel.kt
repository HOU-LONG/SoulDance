package com.example.shopguideagent.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.local.CartPersistenceStore
import com.example.shopguideagent.data.local.InMemoryCartPersistenceStore
import com.example.shopguideagent.data.model.CartItemUiModel
import com.example.shopguideagent.data.model.CartUiState
import com.example.shopguideagent.data.model.CheckoutResult
import com.example.shopguideagent.data.model.OrderUiModel
import com.example.shopguideagent.data.model.OrdersUiState
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.selectedItemCount
import com.example.shopguideagent.data.model.selectedTotalPrice
import com.example.shopguideagent.data.remote.CartApiClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

class CartViewModel @JvmOverloads constructor(
    private val userId: String = UserSession.USER_ID,
    sessionId: String = UserSession.DEFAULT_SESSION_ID,
    private val persistenceStore: CartPersistenceStore = InMemoryCartPersistenceStore(),
    private val cartApiClient: CartApiClient = CartApiClient(),
) : ViewModel() {
    private var activeSessionId: String = sessionId

    private val _uiState = MutableStateFlow(
        CartUiState(items = persistenceStore.loadCartItems(userId)).recalculate(),
    )
    val uiState: StateFlow<CartUiState> = _uiState.asStateFlow()

    private val _ordersState = MutableStateFlow(
        OrdersUiState(orders = persistenceStore.loadOrders(userId)),
    )
    val ordersState: StateFlow<OrdersUiState> = _ordersState.asStateFlow()

    init {
        loadCartFromServer()
    }

    fun refresh() {
        loadCartFromServer()
    }

    fun switchSession(sessionId: String) {
        if (sessionId.isBlank()) return
        activeSessionId = sessionId
        loadCartFromServer()
    }

    private fun loadCartFromServer() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            try {
                val items = cartApiClient.getCart(activeSessionId)
                _uiState.value = CartUiState(items = items).recalculate()
                persistenceStore.saveCartItems(userId, items)
            } catch (e: Exception) {
                val localItems = persistenceStore.loadCartItems(userId)
                _uiState.value = CartUiState(
                    items = localItems,
                    errorMessage = "购物车同步失败：${e.message}",
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
        viewModelScope.launch {
            try {
                cartApiClient.addToCart(activeSessionId, product)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(errorMessage = "同步失败：${e.message}").recalculate()
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
                _uiState.value = _uiState.value.copy(errorMessage = "同步失败：${e.message}").recalculate()
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
                _uiState.value = _uiState.value.copy(errorMessage = "同步失败：${e.message}").recalculate()
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
                _uiState.value = _uiState.value.copy(errorMessage = "同步失败：${e.message}").recalculate()
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
                _uiState.value = _uiState.value.copy(errorMessage = "同步失败：${e.message}").recalculate()
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
                _uiState.value = _uiState.value.copy(errorMessage = "同步失败：${e.message}").recalculate()
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
                _uiState.value = _uiState.value.copy(errorMessage = "同步失败：${e.message}").recalculate()
            }
        }
    }

    fun showCheckout() {
        _uiState.value = _uiState.value.copy(showCheckoutSheet = true)
    }

    fun hideCheckout() {
        _uiState.value = _uiState.value.copy(showCheckoutSheet = false)
    }

    fun checkout() {
        val state = _uiState.value
        if (state.selectedCount == 0) {
            _uiState.value = state.copy(errorMessage = "请先选择要结算的商品")
            return
        }
        viewModelScope.launch {
            try {
                val result = cartApiClient.checkout(activeSessionId)
                if (result != null) {
                    val purchasedItems = state.items.filter { it.selected }
                    val orderId = result.orderId
                    val updatedOrders = listOf(
                        OrderUiModel(
                            orderId = orderId,
                            items = purchasedItems,
                            totalCount = selectedItemCount(purchasedItems),
                            totalPrice = selectedTotalPrice(purchasedItems),
                        ),
                    ) + _ordersState.value.orders
                    _ordersState.value = _ordersState.value.copy(orders = updatedOrders)
                    persistenceStore.saveOrders(userId, updatedOrders)
                    val remainingItems = state.items.filterNot { it.selected }
                    _uiState.value = state.copy(
                        items = remainingItems,
                        showCheckoutSheet = false,
                        checkoutResult = result,
                    ).recalculate()
                    persistenceStore.saveCartItems(userId, remainingItems)
                } else {
                    _uiState.value = state.copy(errorMessage = "结算失败").recalculate()
                }
            } catch (e: Exception) {
                _uiState.value = state.copy(errorMessage = "结算失败：${e.message}").recalculate()
            }
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
        persistenceStore.saveCartItems(userId, items)
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
}

private fun CartUiState.recalculate(): CartUiState = CartUiState(
    isLoading = isLoading,
    items = items,
    errorMessage = errorMessage,
    lastRemovedItem = lastRemovedItem,
    showCheckoutSheet = showCheckoutSheet,
    checkoutResult = checkoutResult,
)
