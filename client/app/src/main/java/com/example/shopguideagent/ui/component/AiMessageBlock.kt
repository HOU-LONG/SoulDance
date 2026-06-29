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
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
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
    @Suppress("UNUSED_PARAMETER") firePoints: Int,
    onProductAnchorTap: (String) -> Unit,
    @Suppress("UNUSED_PARAMETER") onAddToCart: (ProductUiModel) -> Unit,
    onQuickAction: (String) -> Unit,
    onAddBundleProduct: (ProductUiModel) -> Unit,
    modifier: Modifier = Modifier,
) {
    val productMap = remember(message.products) {
        message.products.associateBy { it.productId }
    }
    val chunks = remember(message.text, productMap) {
        splitAiMessageChunks(message.text, productMap)
    }
    // 主推：在段落锚点中出现过的商品（内联渲染为卡片）
    // 备选：剩下未在锚点中提及的商品（流式中先于文本到达 / 主推/备选分层时备选纯文字描述）
    val mentionedIds = remember(chunks) {
        buildSet {
            chunks.forEach { chunk -> chunk.products.forEach { add(it.productId) } }
        }
    }
    val alternativeProducts = remember(message.products, mentionedIds) {
        message.products.filterNot { it.productId in mentionedIds }
    }

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
            AiMessageBody(
                message = message,
                chunks = chunks,
                onProductAnchorTap = onProductAnchorTap,
            )
        }
        // 备选商品：在气泡下方以横向缩略图形式展示，与主推视觉层级区分开
        if (alternativeProducts.isNotEmpty() && !message.isStreaming) {
            AlternativeThumbnails(
                products = alternativeProducts,
                onProductClick = onProductAnchorTap,
            )
        }
        if (message.products.isEmpty() && message.quickActions.isNotEmpty()) {
            QuickActionChips(
                actions = message.quickActions,
                onActionClick = onQuickAction,
                modifier = Modifier.fillMaxWidth(),
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

/**
 * 消息气泡内容：按 \n\n 切段渲染。段内有锚点 → 段后插入对应内联商品卡片（主推）。
 * 备选商品（未在锚点中提及的）不在气泡内显示，由外层 [AlternativeThumbnails] 接管。
 */
@Composable
private fun AiMessageBody(
    message: ChatMessageUiModel,
    chunks: List<AiMessageChunk>,
    onProductAnchorTap: (String) -> Unit,
) {
    val anchorColor = MaterialTheme.colorScheme.primary

    Column(
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (chunks.isEmpty()) {
            // 流式开始但还没收到任何文本时的占位提示
            val fallback = if (message.isStreaming) "我正在帮你整理..." else ""
            if (fallback.isNotEmpty()) {
                Text(
                    text = fallback,
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextPrimary,
                )
            }
            return@Column
        }

        chunks.forEach { chunk ->
            ParagraphText(
                paragraph = chunk.text,
                anchorColor = anchorColor,
                onAnchorClick = onProductAnchorTap,
            )
            chunk.products.forEach { product ->
                InlineProductCard(
                    product = product,
                    onClick = { onProductAnchorTap(product.productId) },
                )
            }
        }
    }
}

@Composable
private fun ParagraphText(
    paragraph: String,
    anchorColor: androidx.compose.ui.graphics.Color,
    onAnchorClick: (String) -> Unit,
) {
    val rendered = remember(paragraph) {
        renderMarkdownText(
            markdown = paragraph,
            fallback = "",
            autoSegment = false,
            anchorColor = anchorColor,
            onAnchorClick = onAnchorClick,
        )
    }
    if (rendered.text.isEmpty()) return
    SelectionContainer {
        Text(
            text = rendered,
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

/**
 * 备选商品横向缩略图条：56dp 图 + 价格，视觉层级弱于主推卡片。
 * 点击进入 ProductDetailBottomSheet（与主推卡片共用一套展开机制）。
 */
@Composable
private fun AlternativeThumbnails(
    products: List<ProductUiModel>,
    onProductClick: (String) -> Unit,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.padding(start = 4.dp, top = 2.dp, end = 4.dp, bottom = 2.dp),
    ) {
        products.take(4).forEach { product ->
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.clickableWithScale { onProductClick(product.productId) },
            ) {
                ProductImage(
                    imageUrl = product.imageUrl,
                    productName = product.name,
                    modifier = Modifier
                        .size(56.dp)
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
