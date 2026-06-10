package com.example.shopguideagent.ui.component

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.QuickActionUiModel
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun ProductCarousel(
    products: List<ProductUiModel>,
    expectedCount: Int,
    onProductClick: (ProductUiModel) -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    onQuickAction: (String) -> Unit,
    quickActions: List<QuickActionUiModel> = emptyList(),
    modifier: Modifier = Modifier,
) {
    val primary = products.firstOrNull { it.isPrimary } ?: products.firstOrNull()
    val alternatives = products.filter { it.productId != primary?.productId }
    val missingCount = (expectedCount - products.size).coerceAtLeast(0)
    val actions = quickActions.ifEmpty { quickActionsForProduct(primary) }

    AnimatedVisibility(
        visible = expectedCount > 0 || products.isNotEmpty(),
        enter = fadeIn(tween(200)) + slideInVertically(tween(200)) { it / 10 },
    ) {
        Column(
            modifier = modifier
                .fillMaxWidth()
                .padding(top = 4.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            if (primary != null) {
                HeroProductCard(
                    product = primary,
                    onClick = onProductClick,
                    onAddToCart = onAddToCart,
                    onRefine = onQuickAction,
                )
            } else {
                ProductSkeletonCard(hero = true)
            }

            if (alternatives.isNotEmpty() || missingCount > 0) {
                AlternativeProductCarousel(
                    products = alternatives,
                    skeletonCount = if (primary == null) (missingCount - 1).coerceAtLeast(0) else missingCount,
                    onProductClick = onProductClick,
                    onAddToCart = onAddToCart,
                )
            }

            QuickActionChips(actions = actions, onActionClick = onQuickAction)
        }
    }
}
