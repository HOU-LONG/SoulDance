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
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderColor
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.ChipBackground
import com.example.shopguideagent.ui.theme.ChipText
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary
import kotlinx.coroutines.delay

@Composable
fun AlternativeProductCard(
    product: ProductUiModel,
    index: Int,
    onClick: (ProductUiModel) -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    onProductAnchorTap: (String) -> Unit = {},  // Task 8: 锚点回调
) {
    var visible by remember(product.productId) { mutableStateOf(false) }
    var added by remember(product.productId) { mutableStateOf(false) }
    LaunchedEffect(product.productId, index) {
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
        enter = fadeIn(tween(180)) + slideInVertically(tween(180)) { it / 10 },
    ) {
        Surface(
            modifier = Modifier
                .width(208.dp)
                .clickableWithScale(
                    onClick = { onClick(product) },
                    onLongClick = {
                        val info = buildString {
                            appendLine(product.name)
                            appendLine("¥${"%.2f".format(product.price)}")
                        }
                        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                        clipboard.setPrimaryClip(ClipData.newPlainText("商品信息", info))
                        Toast.makeText(context, "商品信息已复制", Toast.LENGTH_SHORT).show()
                    },
                ),
            color = SurfacePrimary,
            shape = RoundedCornerShape(AppCornerRadius.Card),
            border = BorderStroke(1.dp, BorderLight),
            tonalElevation = 1.dp,
            shadowElevation = 4.dp,
        ) {
            Column(
                modifier = Modifier.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                ProductImage(
                    imageUrl = product.imageUrl,
                    productName = product.name,
                    modifier = Modifier.fillMaxWidth().height(104.dp),
                )
                Text(
                    text = product.name,
                    color = TextPrimary,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = "¥${"%.2f".format(product.price)}",
                    color = PriceColor,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    displayTags(
                        generatedTags = product.derivedAttributes.generatedTags.map { it.value },
                        fallbackTags = product.tags,
                        maxCount = 3,
                    ).forEach { tag ->
                        Text(
                            text = tag,
                            modifier = Modifier
                                .background(ChipBackground, RoundedCornerShape(AppCornerRadius.Pill))
                                .padding(horizontal = 8.dp, vertical = 4.dp),
                            color = ChipText,
                            style = MaterialTheme.typography.labelSmall,
                            maxLines = 1,
                        )
                    }
                }
                product.positiveFeedbackSummary.firstOrNull()?.let { summary ->
                    Text(
                        text = "优点：$summary",
                        color = TextSecondary,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                product.riskTags.ifEmpty { product.negativeFeedbackSummary }.firstOrNull()?.let { risk ->
                    Text(
                        text = "注意：$risk",
                        color = PriceColor,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Button(
                    onClick = {
                        added = true
                        onAddToCart(product)
                    },
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
                        Icons.Outlined.Add,
                        contentDescription = null,
                        tint = TextOnBrand,
                    )
                    Text(
                        text = if (added) "已加入" else "加购",
                        color = TextOnBrand,
                        style = MaterialTheme.typography.labelMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}
