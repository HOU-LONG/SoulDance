package com.example.shopguideagent.ui.component

import org.junit.Assert.assertEquals
import org.junit.Test

class ProductTagDisplayTest {
    @Test
    fun displayTagsPrefersGeneratedTagsAndRemovesDuplicates() {
        val tags = displayTags(
            generatedTags = listOf("敏感肌", "无酒精", "敏感肌", "清爽肤感"),
            fallbackTags = listOf("防晒", "护肤"),
            maxCount = 3,
        )

        assertEquals(listOf("敏感肌", "无酒精", "清爽肤感"), tags)
    }

    @Test
    fun displayTagsFallsBackWhenGeneratedTagsAreEmpty() {
        val tags = displayTags(
            generatedTags = emptyList(),
            fallbackTags = listOf("防晒", "防晒", "通勤"),
            maxCount = 2,
        )

        assertEquals(listOf("防晒", "通勤"), tags)
    }
}
