package com.example.shopguideagent.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.outlined.LocalMall
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.ui.component.ProductImage
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.BrandSoft
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpritePanel
import com.example.shopguideagent.ui.theme.SpritePanelBorder
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun PalmProductThumbnail(
    product: ProductUiModel?,
    loading: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (product == null && !loading) return

    Surface(
        modifier = modifier
            .size(70.dp)
            .clickableWithScale { if (product != null) onClick() },
        shape = RoundedCornerShape(22.dp),
        color = Color.White.copy(alpha = 0.86f),
        border = BorderStroke(1.5.dp, Color.White.copy(alpha = 0.92f)),
        shadowElevation = 10.dp,
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(5.dp),
            contentAlignment = Alignment.Center,
        ) {
            if (product != null) {
                ProductImage(
                    imageUrl = product.imageUrl,
                    productName = product.name,
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .clip(RoundedCornerShape(AppCornerRadius.Card))
                        .background(BrandSoft),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = Icons.Outlined.LocalMall,
                        contentDescription = "正在挑选商品",
                        tint = BrandPrimary,
                        modifier = Modifier.size(28.dp),
                    )
                }
            }
        }
    }
}

@Composable
fun PalmProductMiniPanel(
    product: ProductUiModel,
    onAddToCart: (ProductUiModel) -> Unit,
    onRefine: (String) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.widthIn(max = 232.dp),
        shape = RoundedCornerShape(AppCornerRadius.LargeCard),
        color = SpritePanel.copy(alpha = 0.9f),
        border = BorderStroke(1.dp, SpritePanelBorder),
        shadowElevation = 14.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = product.name,
                        style = MaterialTheme.typography.titleSmall,
                        color = TextPrimary,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = "¥%.0f".format(product.price),
                        style = MaterialTheme.typography.titleMedium,
                        color = PriceColor,
                        fontWeight = FontWeight.Bold,
                    )
                }
                IconButton(
                    onClick = onDismiss,
                    modifier = Modifier.size(28.dp),
                ) {
                    Icon(
                        imageVector = Icons.Filled.Close,
                        contentDescription = "收起商品浮层",
                        tint = TextSecondary,
                        modifier = Modifier.size(16.dp),
                    )
                }
            }

            val hint = product.reason?.takeIf { it.isNotBlank() } ?: product.brand.takeIf { it.isNotBlank() }
            if (!hint.isNullOrBlank()) {
                Text(
                    text = hint,
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }

            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Button(
                    onClick = { onAddToCart(product) },
                    colors = ButtonDefaults.buttonColors(containerColor = BrandPrimary),
                    shape = RoundedCornerShape(AppCornerRadius.Button),
                    modifier = Modifier.weight(1f),
                ) {
                    Text("加购")
                }
                Surface(
                    modifier = Modifier
                        .weight(1f)
                        .height(40.dp)
                        .border(1.dp, BrandPrimary.copy(alpha = 0.35f), RoundedCornerShape(AppCornerRadius.Button))
                        .clickableWithScale { onRefine("围绕${product.name}继续细化") },
                    shape = RoundedCornerShape(AppCornerRadius.Button),
                    color = Color.White.copy(alpha = 0.64f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            text = "继续细化",
                            color = BrandPrimary,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }
        }
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6E2C8)
@Composable
private fun PalmProductMiniPanelPreview() {
    ShopGuideAgentTheme {
        Column(modifier = Modifier.padding(16.dp)) {
            PalmProductThumbnail(
                product = samplePalmProduct(),
                loading = false,
                onClick = {},
            )
            Spacer(Modifier.height(12.dp))
            PalmProductMiniPanel(
                product = samplePalmProduct(),
                onAddToCart = {},
                onRefine = {},
                onDismiss = {},
            )
        }
    }
}

private fun samplePalmProduct() = ProductUiModel(
    productId = "preview",
    name = "清爽通勤防晒霜",
    price = 129.0,
    reason = "轻薄不黏，适合日常通勤",
    brand = "灵选",
    isPrimary = true,
)
