package com.example.shopguideagent.ui.component

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.example.shopguideagent.data.model.ProductUiModel

@Composable
fun ProductCard(
    product: ProductUiModel,
    firePoints: Int,
    onClick: (ProductUiModel) -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    modifier: Modifier = Modifier,
) {
    HeroProductCard(
        product = product,
        firePoints = firePoints,
        onClick = onClick,
        onAddToCart = onAddToCart,
        onRefine = {},
        modifier = modifier,
    )
}
