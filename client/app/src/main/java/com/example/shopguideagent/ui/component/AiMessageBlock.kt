package com.example.shopguideagent.ui.component

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.BundleUiModel
import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun AiMessageBlock(
    message: ChatMessageUiModel,
    firePoints: Int,
    onProductAnchorTap: (String) -> Unit,
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
            AiMessageText(message, onProductAnchorTap)
        }
        // F3: 移除 ProductCarousel——商品统一走锚点+Sheet
        if (message.products.isEmpty() && message.quickActions.isNotEmpty()) {
            QuickActionChips(
                actions = message.quickActions,
                onActionClick = onQuickAction,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        // Task 9: 内联商品缩略图——替代被删除的 ProductCarousel，轻量展示商品图片
        if (message.products.isNotEmpty() && !message.isStreaming) {
            InlineProductThumbnails(
                products = message.products,
                onProductClick = onProductAnchorTap,
            )
        }
        // F0: Bundle 始终由 message.bundle 非 null 驱动（不再受 expectedProductCount 门控）
        message.bundle?.let {
            InlineBundleSection(
                bundle = it,
                onAddProduct = onAddBundleProduct,
                onProductAnchorTap = onProductAnchorTap,
            )
        }
    }
}

@Composable
private fun AiMessageText(
    message: ChatMessageUiModel,
    onProductAnchorTap: (String) -> Unit,
) {
    val anchorColor = MaterialTheme.colorScheme.primary
    SelectionContainer {
        val fallback = if (message.isStreaming) "我正在帮你整理推荐..." else ""
        val annotatedString = remember(message.text) {
            renderMarkdownText(
                markdown = message.text,
                fallback = fallback,
                autoSegment = true,
                anchorColor = anchorColor,
                onAnchorClick = onProductAnchorTap,
            )
        }
        // F3: 使用 Text + LinkAnnotation（ClickableText 已 deprecated）
        Text(
            text = annotatedString,
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
    onProductAnchorTap: (String) -> Unit,
) {
    Spacer(modifier = Modifier.height(1.dp))
    BundleSection(
        bundle = bundle,
        onAddProduct = onAddProduct,
        onProductAnchorTap = onProductAnchorTap,
        modifier = Modifier.fillMaxWidth(),
    )
}

// Task 9: 聊天消息中内联展示商品缩略图，取代被删除的 ProductCarousel
@Composable
private fun InlineProductThumbnails(
    products: List<ProductUiModel>,
    onProductClick: (String) -> Unit,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.padding(top = 4.dp, bottom = 2.dp),
    ) {
        products.take(4).forEach { product ->
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.clickableWithScale { onProductClick(product.productId) },
            ) {
                ProductImage(
                    imageUrl = product.imageUrl,
                    modifier = Modifier
                        .size(64.dp)
                        .clip(RoundedCornerShape(10.dp)),
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "¥%.0f".format(product.price),
                    style = MaterialTheme.typography.labelSmall,
                    color = PriceColor,
                    maxLines = 1,
                )
            }
        }
        if (products.size > 4) {
            Text(
                text = "+${products.size - 4}",
                style = MaterialTheme.typography.bodySmall,
                color = TextSecondary,
                modifier = Modifier.align(Alignment.CenterVertically),
            )
        }
    }
}
