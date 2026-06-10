package com.example.shopguideagent.data.local

import android.content.Context
import com.example.shopguideagent.data.model.CartItemUiModel
import com.example.shopguideagent.data.model.OrderUiModel
import org.json.JSONArray
import org.json.JSONObject

interface CartPersistenceStore {
    fun loadCartItems(userId: String): List<CartItemUiModel>
    fun saveCartItems(userId: String, items: List<CartItemUiModel>)
    fun loadOrders(userId: String): List<OrderUiModel>
    fun saveOrders(userId: String, items: List<OrderUiModel>)
}

class InMemoryCartPersistenceStore : CartPersistenceStore {
    override fun loadCartItems(userId: String): List<CartItemUiModel> = emptyList()
    override fun saveCartItems(userId: String, items: List<CartItemUiModel>) = Unit
    override fun loadOrders(userId: String): List<OrderUiModel> = emptyList()
    override fun saveOrders(userId: String, items: List<OrderUiModel>) = Unit
}

class SharedPreferencesCartPersistenceStore(context: Context) : CartPersistenceStore {
    private val preferences = context.applicationContext.getSharedPreferences(
        "shopguide_cart_orders",
        Context.MODE_PRIVATE,
    )

    override fun loadCartItems(userId: String): List<CartItemUiModel> =
        decodeCartItems(preferences.getString(cartKey(userId), null).orEmpty())

    override fun saveCartItems(userId: String, items: List<CartItemUiModel>) {
        preferences.edit().putString(cartKey(userId), encodeCartItems(items)).apply()
    }

    override fun loadOrders(userId: String): List<OrderUiModel> =
        decodeOrders(preferences.getString(ordersKey(userId), null).orEmpty())

    override fun saveOrders(userId: String, items: List<OrderUiModel>) {
        preferences.edit().putString(ordersKey(userId), encodeOrders(items)).apply()
    }

    private fun cartKey(userId: String): String = "cart_items_$userId"

    private fun ordersKey(userId: String): String = "orders_$userId"
}

private fun encodeCartItems(items: List<CartItemUiModel>): String {
    val array = JSONArray()
    items.forEach { item -> array.put(item.toJson()) }
    return array.toString()
}

private fun decodeCartItems(raw: String): List<CartItemUiModel> {
    if (raw.isBlank()) return emptyList()
    return runCatching {
        val array = JSONArray(raw)
        buildList {
            for (index in 0 until array.length()) {
                add(array.getJSONObject(index).toCartItem())
            }
        }
    }.getOrDefault(emptyList())
}

private fun encodeOrders(orders: List<OrderUiModel>): String {
    val array = JSONArray()
    orders.forEach { order ->
        array.put(
            JSONObject()
                .put("orderId", order.orderId)
                .put("items", JSONArray(encodeCartItems(order.items)))
                .put("totalCount", order.totalCount)
                .put("totalPrice", order.totalPrice)
                .put("createdAtMillis", order.createdAtMillis)
                .put("status", order.status),
        )
    }
    return array.toString()
}

private fun decodeOrders(raw: String): List<OrderUiModel> {
    if (raw.isBlank()) return emptyList()
    return runCatching {
        val array = JSONArray(raw)
        buildList {
            for (index in 0 until array.length()) {
                val order = array.getJSONObject(index)
                add(
                    OrderUiModel(
                        orderId = order.optString("orderId"),
                        items = decodeCartItems(order.optJSONArray("items")?.toString().orEmpty()),
                        totalCount = order.optInt("totalCount"),
                        totalPrice = order.optDouble("totalPrice"),
                        createdAtMillis = order.optLong("createdAtMillis"),
                        status = order.optString("status"),
                    ),
                )
            }
        }
    }.getOrDefault(emptyList())
}

private fun CartItemUiModel.toJson(): JSONObject =
    JSONObject()
        .put("productId", productId)
        .put("name", name)
        .put("price", price)
        .put("quantity", quantity)
        .put("selected", selected)
        .put("imageUrl", imageUrl)
        .put("tags", JSONArray(tags))
        .put("stock", stock)
        .put("reason", reason)

private fun JSONObject.toCartItem(): CartItemUiModel =
    CartItemUiModel(
        productId = optString("productId"),
        name = optString("name"),
        price = optDouble("price"),
        quantity = optInt("quantity"),
        selected = optBoolean("selected", true),
        imageUrl = optNullableString("imageUrl"),
        tags = optStringList("tags"),
        stock = if (has("stock") && !isNull("stock")) optInt("stock") else null,
        reason = optNullableString("reason"),
    )

private fun JSONObject.optStringList(name: String): List<String> {
    val array = optJSONArray(name) ?: return emptyList()
    return buildList {
        for (index in 0 until array.length()) {
            add(array.optString(index))
        }
    }
}

private fun JSONObject.optNullableString(name: String): String? =
    if (has(name) && !isNull(name)) optString(name) else null
