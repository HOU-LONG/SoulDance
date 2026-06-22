package com.example.shopguideagent.ui.theme

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DesignTokenTest {
    @Test
    fun cornerTokensUseOneSharedControlRadius() {
        assertEquals(AppCornerRadius.Control, AppCornerRadius.Input)
        assertEquals(AppCornerRadius.Control, AppCornerRadius.Button)
    }

    @Test
    fun primaryPaletteIsBrightAndNotRedDominant() {
        val red = BrandPrimary.red
        val blue = BrandPrimary.blue
        val green = BrandPrimary.green

        assertTrue(blue >= red)
        assertTrue(green >= red * 0.35f)
    }
}
