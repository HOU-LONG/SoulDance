package com.example.shopguideagent.ui.component

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.example.shopguideagent.data.model.ProductUiModel

@Composable
fun ProductCard(
    product: ProductUiModel,
    onClick: (ProductUiModel) -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    modifier: Modifier = Modifier,
) {
    HeroProductCard(
        product = product,
        onClick = onClick,
        onAddToCart = onAddToCart,
        onRefine = {},
        modifier = modifier,
    )
}
