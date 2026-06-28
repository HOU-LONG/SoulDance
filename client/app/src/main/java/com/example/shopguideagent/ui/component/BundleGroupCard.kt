package com.example.shopguideagent.ui.component

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.BundleGroupUiModel
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun BundleGroupCard(
    group: BundleGroupUiModel,
    onAddProduct: (ProductUiModel) -> Unit,
    onProductAnchorTap: (String) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = SurfacePrimary,
        shape = RoundedCornerShape(AppCornerRadius.Card),
        border = BorderStroke(1.dp, BorderLight),
        tonalElevation = 1.dp,
        shadowElevation = 4.dp,
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                group.name,
                color = TextPrimary,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            group.items.forEach { item ->
                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        // F7: 商品名改为锚点渲染
                        val anchorColor = MaterialTheme.colorScheme.primary
                        val productLine = remember(item.product.productId) {
                            buildAnnotatedString {
                                withStyle(SpanStyle(color = TextPrimary)) {
                                    append("${item.slot}: ")
                                }
                                pushLink(
                                    LinkAnnotation.Clickable(
                                        tag = item.product.productId,
                                        styles = TextLinkStyles(
                                            style = SpanStyle(color = anchorColor, textDecoration = TextDecoration.Underline)
                                        ),
                                        linkInteractionListener = { link ->
                                            val productId = (link as? LinkAnnotation.Clickable)?.tag ?: return@Clickable
                                            onProductAnchorTap(productId)
                                        },
                                    )
                                )
                                append(item.product.name)
                                pop()
                            }
                        }
                        Text(
                            text = productLine,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Text(
                            text = renderMarkdownText(item.product.reason.orEmpty(), fallback = ""),
                            color = TextSecondary,
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 2,
                        )
                    }
                    Button(
                        onClick = { onAddProduct(item.product) },
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
                        Text(
                            "加购",
                            style = MaterialTheme.typography.labelMedium,
                        )
                    }
                }
            }
        }
    }
}
