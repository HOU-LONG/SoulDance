package com.example.shopguideagent.ui.home

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.QuickActionUiModel
import com.example.shopguideagent.ui.component.AlternativeProductCarousel
import com.example.shopguideagent.ui.component.HeroProductCard
import com.example.shopguideagent.ui.component.QuickActionChips
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpritePanel
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun ProductPresentationSheet(
    primaryProduct: ProductUiModel?,
    alternatives: List<ProductUiModel>,
    expectedCount: Int,
    receivedCount: Int,
    completed: Boolean,
    quickActions: List<QuickActionUiModel>,
    firePoints: Int,
    onProductClick: (ProductUiModel) -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    onQuickAction: (String) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val visible = primaryProduct != null || expectedCount > 0
    val transitionState = remember(visible) { MutableTransitionState(visible) }
    transitionState.targetState = visible

    AnimatedVisibility(
        visibleState = transitionState,
        modifier = modifier,
        enter = scaleIn(
            transformOrigin = TransformOrigin(0.85f, 0.1f),
            initialScale = 0.2f,
            animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = 400f),
        ) + fadeIn(),
        exit = fadeOut(),
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .clip(RoundedCornerShape(28.dp))
                .background(SpritePanel),
            shape = RoundedCornerShape(28.dp),
            color = SpritePanel,
            border = BorderStroke(1.dp, Color.White.copy(alpha = 0.78f)),
            shadowElevation = 12.dp,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 18.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                ) {
                    IconButton(
                        onClick = onDismiss,
                        modifier = Modifier.size(32.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Close,
                            contentDescription = "关闭商品卡片",
                            tint = TextPrimary,
                        )
                    }
                }
                primaryProduct?.let { product ->
                    HeroProductCard(
                        product = product,
                        firePoints = firePoints,
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
            firePoints = 886,
            onProductClick = {},
            onAddToCart = {},
            onQuickAction = {},
            onDismiss = {},
        )
    }
}
