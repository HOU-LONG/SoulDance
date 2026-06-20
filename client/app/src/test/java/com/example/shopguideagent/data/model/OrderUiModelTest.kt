package com.example.shopguideagent.data.model

import org.junit.Assert.assertNotEquals
import org.junit.Test

class OrderUiModelTest {
    @Test
    fun orderListKeyDistinguishesRepeatedBackendOrderIds() {
        val first = OrderUiModel(
            orderId = "demo_order_session",
            items = emptyList(),
            totalCount = 0,
            totalPrice = 0.0,
            createdAtMillis = 1000L,
        )
        val second = first.copy(createdAtMillis = 2000L)

        assertNotEquals(orderListKey(first), orderListKey(second))
    }
}
