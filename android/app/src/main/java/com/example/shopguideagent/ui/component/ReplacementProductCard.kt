package com.example.shopguideagent.ui.component

import androidx.compose.runtime.Composable
import com.example.shopguideagent.data.model.ProductUiModel

@Composable
fun ReplacementProductCard(
    product: ProductUiModel,
    onAddToCart: (ProductUiModel) -> Unit,
) {
    ProductCard(product = product, onClick = {}, onAddToCart = onAddToCart)
}
