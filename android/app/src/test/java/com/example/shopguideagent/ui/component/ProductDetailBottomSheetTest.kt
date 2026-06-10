package com.example.shopguideagent.ui.component

import org.junit.Assert.assertEquals
import org.junit.Test

class ProductDetailBottomSheetTest {
    @Test
    fun productDetailEvidenceItemsKeepsAllNonBlankEvidence() {
        val evidence = listOf(
            "续航反馈稳定",
            "拍照清晰",
            "",
            "屏幕观感好",
            "性能释放积极",
        )

        assertEquals(
            listOf("续航反馈稳定", "拍照清晰", "屏幕观感好", "性能释放积极"),
            productDetailEvidenceItems(evidence),
        )
    }
}
