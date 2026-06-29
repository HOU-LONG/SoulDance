package com.example.shopguideagent.ui.component

import com.example.shopguideagent.data.model.ProductUiModel
import org.junit.Assert.assertEquals
import org.junit.Test

class InlineProductCardSubtitleTest {

    @Test
    fun subtitleCombinesPriceAndBrandWhenBrandPresent() {
        val product = ProductUiModel(
            productId = "p_001",
            name = "海澜之家 免烫衬衫",
            price = 178.0,
            brand = "海澜之家",
        )
        assertEquals("¥178 · 海澜之家", inlineProductSubtitle(product))
    }

    @Test
    fun subtitleFallsBackToPriceWhenBrandBlank() {
        val product = ProductUiModel(
            productId = "p_002",
            name = "衬衫老罗 桑蚕丝衬衫",
            price = 399.0,
            brand = "",
        )
        assertEquals("¥399", inlineProductSubtitle(product))
    }

    @Test
    fun subtitleFallsBackToPriceWhenBrandWhitespace() {
        val product = ProductUiModel(
            productId = "p_003",
            name = "测试商品",
            price = 50.0,
            brand = "   ",
        )
        assertEquals("¥50", inlineProductSubtitle(product))
    }
}
