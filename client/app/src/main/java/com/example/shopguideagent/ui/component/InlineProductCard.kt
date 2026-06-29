package com.example.shopguideagent.ui.component

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

/**
 * 内联在 AI 消息段落之间的商品卡片：左侧 64dp 缩略图 + 右侧名称/价格·品牌副标题。
 * 点击触发详情底部弹窗，与文本锚点 [[name#productId]] 同走 `onProductAnchorTap` 回调。
 */
@Composable
fun InlineProductCard(
    product: ProductUiModel,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .clickableWithScale(onClick),
        color = SurfacePrimary,
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, BorderLight),
        tonalElevation = 0.dp,
        shadowElevation = 1.dp,
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ProductImage(
                imageUrl = product.imageUrl,
                productName = product.name,
                modifier = Modifier
                    .size(64.dp)
                    .clip(RoundedCornerShape(10.dp)),
            )
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(
                    text = product.name,
                    color = TextPrimary,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = inlineProductSubtitle(product),
                    color = TextSecondary,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

/** 副标题：`¥{price} · {brand}` 形式；brand 为空时只显示价格。internal 便于单测。 */
internal fun inlineProductSubtitle(product: ProductUiModel): String {
    val price = "¥${"%.0f".format(product.price)}"
    val brand = product.brand.takeIf { it.isNotBlank() }
    return if (brand != null) "$price · $brand" else price
}
