package com.example.shopguideagent.data.catalog;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import com.example.shopguideagent.data.model.ProductUiModel;

import org.junit.Test;

import java.util.Arrays;
import java.util.List;

public class ProductCatalogTest {
    @Test
    public void listProductCatalogPreservesSourceOrderWhenQueryWouldFavorLaterProduct() {
        ProductUiModel first = product("source-first", "Gentle cleanser", false);
        ProductUiModel second = product("source-second", "Exact query match sunscreen", false);
        ProductUiModel third = product("source-third", "Budget option", false);
        ListProductCatalog catalog = new ListProductCatalog(Arrays.asList(first, second, third));

        List<ProductUiModel> recommendations = catalog.recommend("Exact query match sunscreen", 3);

        assertEquals("source-first", recommendations.get(0).getProductId());
        assertEquals("source-second", recommendations.get(1).getProductId());
        assertEquals("source-third", recommendations.get(2).getProductId());
    }

    @Test
    public void listProductCatalogMarksOnlyFirstSourceItemAsPrimary() {
        ProductUiModel first = product("source-first", "First source item", false);
        ProductUiModel second = product("source-second", "Second source item", true);
        ProductUiModel third = product("source-third", "Third source item", true);
        ListProductCatalog catalog = new ListProductCatalog(Arrays.asList(first, second, third));

        List<ProductUiModel> recommendations = catalog.recommend("source-third", 3);

        assertTrue(recommendations.get(0).isPrimary());
        assertFalse(recommendations.get(1).isPrimary());
        assertFalse(recommendations.get(2).isPrimary());
    }

    @Test
    public void listProductCatalogReturnsEmptyListWhenLimitIsZero() {
        ProductUiModel first = product("source-first", "First source item", false);
        ListProductCatalog catalog = new ListProductCatalog(Arrays.asList(first));

        List<ProductUiModel> recommendations = catalog.recommend("anything", 0);

        assertTrue(recommendations.isEmpty());
    }

    private ProductUiModel product(String productId, String name, boolean isPrimary) {
        return new ProductUiModel(
                productId,
                name,
                99.0,
                null,
                Arrays.asList(name),
                "source order test product",
                null,
                null,
                isPrimary
        );
    }
}
