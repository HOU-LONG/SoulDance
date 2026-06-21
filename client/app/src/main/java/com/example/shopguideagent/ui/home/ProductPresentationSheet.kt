package com.example.shopguideagent.ui.home

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.fadeIn
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.QuickActionUiModel
import com.example.shopguideagent.ui.component.AlternativeProductCarousel
import com.example.shopguideagent.ui.component.HeroProductCard
import com.example.shopguideagent.ui.component.QuickActionChips
import com.example.shopguideagent.ui.component.quickActionsForProduct
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpritePanel
import com.example.shopguideagent.ui.theme.SpriteVoiceBarBackground
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun ProductPresentationSheet(
    primaryProduct: ProductUiModel?,
    alternatives: List<ProductUiModel>,
    expectedCount: Int,
    receivedCount: Int,
    completed: Boolean,
    quickActions: List<QuickActionUiModel>,
    onProductClick: (ProductUiModel) -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    onQuickAction: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val visible = primaryProduct != null || expectedCount > 0
    AnimatedVisibility(
        visible = visible,
        enter = slideInVertically(initialOffsetY = { it / 2 }) + fadeIn(),
        modifier = modifier,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp))
                .background(SpritePanel)
                .padding(horizontal = 16.dp, vertical = 18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            primaryProduct?.let { product ->
                HeroProductCard(
                    product = product,
                    onClick = onProductClick,
                    onAddToCart = onAddToCart,
                    onRefine = onQuickAction,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            if (primaryProduct == null && expectedCount > 0) {
                Text(
                    text = "正在为你挑选好物…",
                    style = MaterialTheme.typography.bodyLarge,
                    color = TextPrimary,
                    fontWeight = FontWeight.Medium,
                )
            }
            if (quickActions.isNotEmpty()) {
                QuickActionChips(
                    actions = quickActions,
                    onActionClick = onQuickAction,
                )
            }
            if (alternatives.isNotEmpty() || receivedCount < expectedCount) {
                AlternativeProductCarousel(
                    products = alternatives,
                    skeletonCount = (expectedCount - receivedCount - (if (primaryProduct != null) 1 else 0)).coerceAtLeast(0),
                    onProductClick = onProductClick,
                    onAddToCart = onAddToCart,
                )
            }
        }
    }
}

@Preview(showBackground = true, widthDp = 390)
@Composable
private fun ProductPresentationSheetPreview() {
    ShopGuideAgentTheme {
        ProductPresentationSheet(
            primaryProduct = null,
            alternatives = emptyList(),
            expectedCount = 1,
            receivedCount = 0,
            completed = false,
            quickActions = emptyList(),
            onProductClick = {},
            onAddToCart = {},
            onQuickAction = {},
        )
    }
}
