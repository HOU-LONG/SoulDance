package com.example.shopguideagent.data.model;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class ProductShareFormatterTest {
    @Test
    public void shareTextContainsProductDecisionContextWithoutImageUrl() {
        ProductUiModel product = new ProductUiModel(
                "p_001",
                "Daily sunscreen",
                129.0,
                "file:///android_asset/1_beauty/images/p_beauty_001_live.jpg",
                java.util.Collections.emptyList(),
                "Better fit for commuting and sensitive skin."
        );

        String text = ProductShareFormatter.shareText(product);

        assertTrue(text.contains("Daily sunscreen"));
        assertTrue(text.contains("129.00"));
        assertTrue(text.contains("Better fit for commuting and sensitive skin."));
        assertFalse(text.contains("file:///android_asset/1_beauty/images/p_beauty_001_live.jpg"));
        assertFalse(text.contains("Image:"));
    }
}
