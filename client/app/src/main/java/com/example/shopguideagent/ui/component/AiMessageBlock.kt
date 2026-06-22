package com.example.shopguideagent.ui.component

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.BundleUiModel
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun AiMessageBlock(
    message: ChatMessageUiModel,
    onProductClick: (ProductUiModel) -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    onQuickAction: (String) -> Unit,
    onAddBundleProduct: (ProductUiModel) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.animateContentSize(),
        horizontalAlignment = Alignment.Start,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Surface(
            modifier = Modifier.widthIn(max = 420.dp),
            color = SurfacePrimary,
            contentColor = TextPrimary,
            shape = RoundedCornerShape(AppCornerRadius.Card),
            border = BorderStroke(1.dp, BorderLight),
            tonalElevation = 1.dp,
            shadowElevation = 3.dp,
        ) {
            AiMessageText(message)
        }
        if (message.expectedProductCount > 0 || message.products.isNotEmpty()) {
            ProductCarousel(
                products = message.products,
                expectedCount = message.expectedProductCount,
                onProductClick = onProductClick,
                onAddToCart = onAddToCart,
                onQuickAction = onQuickAction,
                quickActions = message.quickActions,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (message.products.isEmpty() && message.quickActions.isNotEmpty()) {
            QuickActionChips(
                actions = message.quickActions,
                onActionClick = onQuickAction,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        message.bundle?.let {
            InlineBundleSection(bundle = it, onAddProduct = onAddBundleProduct)
        }
    }
}

@Composable
private fun AiMessageText(message: ChatMessageUiModel) {
    SelectionContainer {
        val fallback = if (message.isStreaming) "我正在帮你整理推荐..." else ""
        Text(
            text = renderMarkdownText(message.text, fallback, autoSegment = true),
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            style = MaterialTheme.typography.bodyMedium.copy(
                lineHeightStyle = LineHeightStyle(
                    alignment = LineHeightStyle.Alignment.Center,
                    trim = LineHeightStyle.Trim.None,
                ),
            ),
        )
    }
}

@Composable
private fun InlineBundleSection(
    bundle: BundleUiModel,
    onAddProduct: (ProductUiModel) -> Unit,
) {
    Spacer(modifier = Modifier.height(1.dp))
    BundleSection(
        bundle = bundle,
        onAddProduct = onAddProduct,
        modifier = Modifier.fillMaxWidth(),
    )
}
