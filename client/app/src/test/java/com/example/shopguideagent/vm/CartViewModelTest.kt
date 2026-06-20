package com.example.shopguideagent.vm

import com.example.shopguideagent.data.local.CartPersistenceStore
import com.example.shopguideagent.data.model.CartItemUiModel
import com.example.shopguideagent.data.model.CheckoutResult
import com.example.shopguideagent.data.model.OrderUiModel
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.remote.CartApiClient
import com.example.shopguideagent.domain.event.CartOperationEvent
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import com.example.shopguideagent.test.CoroutineTestHelper
import org.junit.AfterClass
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.BeforeClass
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class CartViewModelTest {
    @Test
    fun addProductUpdatesCountAndTotal() {
        val viewModel = viewModel()
        val product = product("sku_001")

        viewModel.addProduct(product)
        viewModel.increaseQuantity("sku_001")

        assertEquals(2, viewModel.uiState.value.totalCount)
        assertEquals(158.0, viewModel.uiState.value.totalPrice, 0.001)
    }

    @Test
    fun addProductEmitsSuccessEventAfterBackendSyncSucceeds() = runBlocking {
        val viewModel = viewModel()
        val event = async(start = CoroutineStart.UNDISPATCHED) { withTimeout(1_000) { viewModel.operationEvents.first() } }

        viewModel.addProduct(product("sku_001"))

        assertEquals(CartOperationEvent.AddToCartSucceeded("sku_001", 1), event.await())
    }

    @Test
    fun addProductEmitsFailureEventWhenBackendSyncFails() = runBlocking {
        val viewModel = viewModel(addError = IllegalStateException("stock empty"))
        val event = async(start = CoroutineStart.UNDISPATCHED) { withTimeout(1_000) { viewModel.operationEvents.first() } }

        viewModel.addProduct(product("sku_001"))

        assertEquals(CartOperationEvent.AddToCartFailed("sku_001", "stock empty"), event.await())
    }

    @Test
    fun deselectedItemsDoNotCountTowardCheckoutTotal() {
        val viewModel = viewModel()
        viewModel.addItem(cartItem("sku_001", "A", 100.0, 1))
        viewModel.addItem(cartItem("sku_002", "B", 50.0, 1))

        viewModel.toggleSelected("sku_002")

        assertEquals(1, viewModel.uiState.value.selectedCount)
        assertEquals(100.0, viewModel.uiState.value.totalPrice, 0.001)
    }

    @Test
    fun checkoutRemovesSelectedItemsAndKeepsUnselectedItems() {
        val viewModel = viewModel(checkoutResult = CheckoutResult("order_test", 200.0))
        viewModel.addItem(cartItem("sku_001", "A", 100.0, 2))
        viewModel.addItem(cartItem("sku_002", "B", 50.0, 1))
        viewModel.toggleSelected("sku_002")

        viewModel.checkout()

        assertEquals(1, viewModel.uiState.value.items.size)
        assertEquals("sku_002", viewModel.uiState.value.items[0].productId)
        assertEquals(1, viewModel.uiState.value.totalCount)
        assertEquals(0.0, viewModel.uiState.value.totalPrice, 0.001)
        assertEquals(200.0, viewModel.uiState.value.checkoutResult?.paidAmount ?: 0.0, 0.001)
    }

    @Test
    fun checkoutCreatesOrderWithPurchasedItems() {
        val viewModel = viewModel(checkoutResult = CheckoutResult("order_test", 200.0))
        viewModel.addItem(cartItem("sku_001", "A", 100.0, 2))
        viewModel.addItem(cartItem("sku_002", "B", 50.0, 1))
        viewModel.toggleSelected("sku_002")

        viewModel.checkout()

        assertEquals(1, viewModel.ordersState.value.orders.size)
        assertEquals(1, viewModel.ordersState.value.orders[0].items.size)
        assertEquals("sku_001", viewModel.ordersState.value.orders[0].items[0].productId)
        assertEquals(200.0, viewModel.ordersState.value.orders[0].totalPrice, 0.001)
    }

    @Test
    fun checkoutFailureShowsBackendReason() {
        val viewModel = viewModel(
            checkoutError = IllegalStateException("\u8d2d\u7269\u8f66\u4e3a\u7a7a\uff0c\u65e0\u6cd5\u7ed3\u7b97\u3002"),
        )
        viewModel.addItem(cartItem("sku_001", "A", 100.0, 1))

        viewModel.checkout()

        assertEquals(
            "\u7ed3\u7b97\u5931\u8d25\uff1a\u8d2d\u7269\u8f66\u4e3a\u7a7a\uff0c\u65e0\u6cd5\u7ed3\u7b97\u3002",
            viewModel.uiState.value.errorMessage,
        )
    }

    @Test
    fun removeStoresUndoItemAndUpdatesTotals() {
        val viewModel = viewModel()
        viewModel.addItem(cartItem("sku_001", "A", 100.0, 2))

        viewModel.remove("sku_001")

        assertEquals(0, viewModel.uiState.value.totalCount)
        assertEquals("sku_001", viewModel.uiState.value.lastRemovedItem?.productId)
    }

    @Test
    fun undoRemoveRestoresItemAndTotals() {
        val viewModel = viewModel()
        viewModel.addItem(cartItem("sku_001", "A", 100.0, 2))
        viewModel.remove("sku_001")

        viewModel.undoLastRemove()

        assertEquals(2, viewModel.uiState.value.totalCount)
        assertEquals(2, viewModel.uiState.value.selectedCount)
        assertEquals(200.0, viewModel.uiState.value.totalPrice, 0.001)
        assertNull(viewModel.uiState.value.lastRemovedItem)
    }

    @Test
    fun undoRemovePersistsRestoredCart() {
        val store = FakeCartPersistenceStore()
        val viewModel = viewModel(userId = "user_a", sessionId = "demo_session_001", store = store)
        viewModel.addItem(cartItem("sku_001", "A", 100.0, 2))
        viewModel.remove("sku_001")

        viewModel.undoLastRemove()

        val reloaded = viewModel(userId = "user_a", sessionId = "demo_session_001", store = store)
        assertEquals(1, reloaded.uiState.value.items.size)
        assertEquals(2, reloaded.uiState.value.totalCount)
    }

    @Test
    fun cartAndOrdersReloadFromStoreForSameUserOnly() {
        val store = FakeCartPersistenceStore()
        val first = viewModel(
            userId = "user_a",
            sessionId = "demo_session_001",
            store = store,
            checkoutResult = CheckoutResult("order_test", 200.0),
        )
        first.addItem(cartItem("sku_001", "A", 100.0, 2))
        first.checkout()

        val reloaded = viewModel(userId = "user_a", sessionId = "demo_session_001", store = store)
        val otherUser = viewModel(userId = "user_b", sessionId = "demo_session_002", store = store)

        assertEquals(0, reloaded.uiState.value.items.size)
        assertEquals(1, reloaded.ordersState.value.orders.size)
        assertEquals("sku_001", reloaded.ordersState.value.orders[0].items[0].productId)
        assertEquals(0, otherUser.uiState.value.items.size)
        assertEquals(0, otherUser.ordersState.value.orders.size)
    }

    @Test
    fun switchSessionRefreshesCartFromServerForChatSession() {
        val api = SessionCartApiClient(
            carts = mutableMapOf(
                "chat_session_002" to listOf(cartItem("sku_ws", "Server item", 30.0, 1)),
            ),
        )
        val viewModel = CartViewModel(
            userId = "user_a",
            sessionId = "demo_session_001",
            persistenceStore = FakeCartPersistenceStore(),
            cartApiClient = api,
        )

        viewModel.switchSession("chat_session_002")

        assertEquals("chat_session_002", api.getCartSessions.last())
        assertEquals(1, viewModel.uiState.value.items.size)
        assertEquals("sku_ws", viewModel.uiState.value.items[0].productId)
    }

    @Test
    fun switchSessionDoesNotReloadWhenSessionIsUnchanged() {
        val api = SessionCartApiClient(
            carts = mutableMapOf("chat_session_001" to emptyList()),
        )
        val viewModel = CartViewModel(
            userId = "user_a",
            sessionId = "chat_session_001",
            persistenceStore = FakeCartPersistenceStore(),
            cartApiClient = api,
        )

        viewModel.switchSession("chat_session_001")

        assertEquals(listOf("chat_session_001"), api.getCartSessions)
    }

    @Test
    fun switchSessionCanForceRefreshSameSessionAfterRealtimeCartUpdate() {
        val api = SessionCartApiClient(
            carts = mutableMapOf("chat_session_001" to emptyList()),
        )
        val store = FakeCartPersistenceStore()
        val viewModel = CartViewModel(
            userId = "user_a",
            sessionId = "chat_session_001",
            persistenceStore = store,
            cartApiClient = api,
        )
        api.carts["chat_session_001"] = listOf(cartItem("p_digital_008", "小米 17 Ultra", 7499.0, 1))

        viewModel.switchSession("chat_session_001", forceRefresh = true)

        assertEquals(listOf("chat_session_001", "chat_session_001"), api.getCartSessions)
        assertEquals("p_digital_008", viewModel.uiState.value.items.single().productId)
        assertEquals("p_digital_008", store.loadCartItems("user_a").single().productId)
    }

    @Test
    fun clearUsesActiveChatSessionAfterSwitch() {
        val api = SessionCartApiClient(
            carts = mutableMapOf(
                "chat_session_002" to listOf(cartItem("sku_ws", "Server item", 30.0, 1)),
            ),
        )
        val viewModel = CartViewModel(
            userId = "user_a",
            sessionId = "demo_session_001",
            persistenceStore = FakeCartPersistenceStore(),
            cartApiClient = api,
        )
        viewModel.switchSession("chat_session_002")

        viewModel.clear()

        assertEquals("chat_session_002", api.clearSessions.last())
        assertEquals(0, viewModel.uiState.value.items.size)
    }

    private fun viewModel(
        userId: String = "test_user",
        sessionId: String = "test_session",
        store: CartPersistenceStore = FakeCartPersistenceStore(),
        checkoutResult: CheckoutResult? = CheckoutResult("order_test", 200.0),
        checkoutError: RuntimeException? = null,
        addError: RuntimeException? = null,
    ): CartViewModel = CartViewModel(
        userId = userId,
        sessionId = sessionId,
        persistenceStore = store,
        cartApiClient = FakeCartApiClient(checkoutResult, checkoutError, addError),
        operationDispatcher = Dispatchers.Unconfined,
    )

    private fun product(productId: String): ProductUiModel = ProductUiModel(
        productId = productId,
        name = "Oil control cleanser",
        price = 79.0,
        imageUrl = null,
        tags = listOf("oil skin"),
        reason = "Fits oily skin and budget",
        rating = null,
        stock = null,
        isPrimary = true,
    )

    private fun cartItem(
        productId: String,
        name: String,
        price: Double,
        quantity: Int,
        selected: Boolean = true,
    ): CartItemUiModel = CartItemUiModel(
        productId = productId,
        name = name,
        price = price,
        quantity = quantity,
        selected = selected,
        imageUrl = null,
        tags = emptyList(),
        stock = null,
        reason = null,
    )

    private class FakeCartApiClient(
        private val checkoutResult: CheckoutResult?,
        private val checkoutError: RuntimeException?,
        private val addError: RuntimeException?,
    ) : CartApiClient() {
        override suspend fun getCart(sessionId: String): List<CartItemUiModel> {
            throw IllegalStateException("offline test cart sync")
        }

        override suspend fun addToCart(
            sessionId: String,
            product: ProductUiModel,
            quantity: Int,
        ): CartItemUiModel {
            addError?.let { throw it }
            return CartItemUiModel(
            productId = product.productId,
            name = product.name,
            price = product.price,
            quantity = quantity,
            imageUrl = product.imageUrl,
            tags = product.tags,
            stock = product.stock,
            reason = product.reason,
        )
        }

        override suspend fun updateQuantity(sessionId: String, productId: String, quantity: Int): Boolean = true

        override suspend fun removeItem(sessionId: String, productId: String): Boolean = true

        override suspend fun selectItem(sessionId: String, productId: String, selected: Boolean): Boolean = true

        override suspend fun clearCart(sessionId: String): Boolean = true

        override suspend fun checkout(sessionId: String): CheckoutResult? {
            checkoutError?.let { throw it }
            return checkoutResult
        }
    }

    private class FakeCartPersistenceStore : CartPersistenceStore {
        private val carts = mutableMapOf<String, List<CartItemUiModel>>()
        private val orders = mutableMapOf<String, List<OrderUiModel>>()

        override fun loadCartItems(userId: String): List<CartItemUiModel> =
            carts[userId]?.toList().orEmpty()

        override fun saveCartItems(userId: String, items: List<CartItemUiModel>) {
            carts[userId] = items.toList()
        }

        override fun loadOrders(userId: String): List<OrderUiModel> =
            orders[userId]?.toList().orEmpty()

        override fun saveOrders(userId: String, items: List<OrderUiModel>) {
            orders[userId] = items.toList()
        }
    }

    private class SessionCartApiClient(
        val carts: MutableMap<String, List<CartItemUiModel>>,
    ) : CartApiClient() {
        val getCartSessions = mutableListOf<String>()
        val clearSessions = mutableListOf<String>()

        override suspend fun getCart(sessionId: String): List<CartItemUiModel> {
            getCartSessions += sessionId
            return carts[sessionId].orEmpty()
        }

        override suspend fun clearCart(sessionId: String): Boolean {
            clearSessions += sessionId
            carts[sessionId] = emptyList()
            return true
        }

        override suspend fun checkout(sessionId: String): CheckoutResult? = CheckoutResult("order_test", 30.0)
    }

    companion object {
        @JvmStatic
        @BeforeClass
        fun setupClass() {
            CoroutineTestHelper.setMainDispatcher()
        }

        @JvmStatic
        @AfterClass
        fun tearDownClass() {
            CoroutineTestHelper.resetMainDispatcher()
        }
    }
}
