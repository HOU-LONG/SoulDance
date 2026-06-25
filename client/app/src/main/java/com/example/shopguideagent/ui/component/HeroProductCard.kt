package com.example.shopguideagent.ui.component

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AddShoppingCart
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderColor
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.BrandSoft
import com.example.shopguideagent.ui.theme.ChipBackground
import com.example.shopguideagent.ui.theme.ChipText
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShadowColor
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary
import kotlinx.coroutines.delay

object HeroProductCardActionPolicy {
    const val showFavoriteAction: Boolean = false
}

@Composable
fun HeroProductCard(
    product: ProductUiModel,
    firePoints: Int,
    onClick: (ProductUiModel) -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    onRefine: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var visible by remember(product.productId) { mutableStateOf(false) }
    var added by remember(product.productId) { mutableStateOf(false) }

    LaunchedEffect(product.productId) {
        visible = true
    }
    LaunchedEffect(added) {
        if (added) {
            delay(1200)
            added = false
        }
    }

    val context = LocalContext.current
    AnimatedVisibility(
        visible = visible,
        enter = fadeIn(tween(200)) + slideInVertically(tween(200)) { it / 8 },
        modifier = modifier,
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .testTag("hero_product_card")
                .clickableWithScale(
                    onClick = { onClick(product) },
                    onLongClick = {
                        val info = buildString {
                            appendLine(product.name)
                            appendLine("¥${"%.2f".format(product.price)}")
                            product.reason?.let { appendLine(it) }
                        }
                        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                        clipboard.setPrimaryClip(ClipData.newPlainText("商品信息", info))
                        Toast.makeText(context, "商品信息已复制", Toast.LENGTH_SHORT).show()
                    },
                ),
            color = BrandSoft,
            shape = RoundedCornerShape(AppCornerRadius.LargeCard),
            border = BorderStroke(1.dp, BorderLight),
            tonalElevation = 2.dp,
            shadowElevation = 6.dp,
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                ProductImage(
                    imageUrl = product.imageUrl,
                    productName = product.name,
                    modifier = Modifier.fillMaxWidth().height(172.dp),
                )
                Text(
                    text = "AI 主推 / Best Match",
                    modifier = Modifier
                        .background(SurfacePrimary, CircleShape)
                        .padding(horizontal = 12.dp, vertical = 6.dp),
                    color = BrandPrimary,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = product.name,
                    color = TextPrimary,
                    style = MaterialTheme.typography.titleLarge,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = "¥${"%.2f".format(product.price)}",
                    color = PriceColor,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                FireDiscountLabel(
                    firePoints = firePoints,
                    price = product.price,
                )
                Text(
                    text = renderMarkdownText(
                        product.reason.orEmpty(),
                        fallback = "这款更贴近你刚才描述的需求，我先把选择范围收敛到它。",
                    ),
                    color = TextSecondary,
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                if (product.positiveFeedbackSummary.isNotEmpty()) {
                    Text(
                        text = "评论优点：" + product.positiveFeedbackSummary.take(2).joinToString("；"),
                        color = TextSecondary,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                val riskSummary = product.riskTags.ifEmpty { product.negativeFeedbackSummary }.take(2)
                if (riskSummary.isNotEmpty()) {
                    Text(
                        text = "风险提示：" + riskSummary.joinToString("；"),
                        color = PriceColor,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    displayTags(
                        generatedTags = product.derivedAttributes.generatedTags.map { it.value },
                        fallbackTags = product.tags,
                        maxCount = 4,
                    ).forEach { tag ->
                        Text(
                            text = tag,
                            modifier = Modifier
                                .background(ChipBackground, RoundedCornerShape(AppCornerRadius.Pill))
                                .padding(horizontal = 10.dp, vertical = 6.dp),
                            color = ChipText,
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(
                        onClick = {
                            added = true
                            onAddToCart(product)
                        },
                        modifier = Modifier
                            .weight(1f)
                            .testTag("product_add_to_cart"),
                        shape = RoundedCornerShape(AppCornerRadius.Button),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = BrandPrimary,
                            contentColor = TextOnBrand,
                        ),
                        elevation = ButtonDefaults.buttonElevation(
                            defaultElevation = 2.dp,
                            pressedElevation = 0.dp,
                        ),
                    ) {
                        Icon(
                            Icons.Outlined.AddShoppingCart,
                            contentDescription = null,
                            tint = TextOnBrand,
                        )
                        Text(
                            text = if (added) "已加入" else "加购",
                            modifier = Modifier.padding(start = 6.dp),
                            color = TextOnBrand,
                            style = MaterialTheme.typography.labelLarge,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    OutlinedButton(
                        onClick = { onRefine("围绕这款继续细化") },
                        shape = RoundedCornerShape(AppCornerRadius.Button),
                        border = BorderStroke(1.dp, BorderColor),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = BrandPrimary),
                    ) {
                        Icon(Icons.Outlined.Tune, contentDescription = null)
                        Text(
                            "继续细化",
                            modifier = Modifier.padding(start = 6.dp),
                            style = MaterialTheme.typography.labelLarge,
                        )
                    }
                }
            }
        }
    }
}

fun displayTags(
    generatedTags: List<String>,
    fallbackTags: List<String>,
    maxCount: Int,
): List<String> {
    val source = generatedTags.ifEmpty { fallbackTags }
    return source
        .map { it.trim() }
        .filter { it.isNotBlank() }
        .distinct()
        .take(maxCount.coerceAtLeast(0))
}
