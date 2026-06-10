package com.example.shopguideagent.data.model

data class CartItemUiModel(
    val productId: String,
    val name: String,
    val price: Double,
    val quantity: Int,
    val selected: Boolean = true,
    val imageUrl: String? = null,
    val tags: List<String> = emptyList(),
    val stock: Int? = null,
    val reason: String? = null,
)

data class CartUiState(
    val isLoading: Boolean = false,
    val items: List<CartItemUiModel> = emptyList(),
    val selectedCount: Int = selectedItemCount(items),
    val totalCount: Int = items.sumOf { it.quantity },
    val totalPrice: Double = selectedTotalPrice(items),
    val lastRemovedItem: CartItemUiModel? = null,
    val errorMessage: String? = null,
    val showCheckoutSheet: Boolean = false,
    val checkoutResult: CheckoutResult? = null,
)

data class CheckoutResult(
    val orderId: String,
    val paidAmount: Double,
)

data class OrderUiModel(
    val orderId: String,
    val items: List<CartItemUiModel>,
    val totalCount: Int,
    val totalPrice: Double,
    val createdAtMillis: Long = System.currentTimeMillis(),
    val status: String = "已下单",
)

data class OrdersUiState(
    val orders: List<OrderUiModel> = emptyList(),
)

fun orderListKey(order: OrderUiModel): String =
    "${order.orderId}_${order.createdAtMillis}"

fun selectedItemCount(items: List<CartItemUiModel>): Int =
    items.filter { it.selected }.sumOf { it.quantity }

fun selectedTotalPrice(items: List<CartItemUiModel>): Double =
    items.filter { it.selected }.sumOf { it.price * it.quantity }
