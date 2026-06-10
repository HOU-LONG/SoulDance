package com.example.shopguideagent.ui.component

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AddShoppingCart
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Composable
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
import com.example.shopguideagent.ui.theme.AppBackground
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderColor
import com.example.shopguideagent.ui.theme.BorderLight
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary
import kotlinx.coroutines.delay

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProductDetailBottomSheet(
    product: ProductUiModel,
    onDismiss: () -> Unit,
    onAddToCart: (ProductUiModel) -> Unit,
    onFollowUp: (String) -> Unit,
) {
    val context = LocalContext.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var added by remember(product.productId) { mutableStateOf(false) }
    LaunchedEffect(added) {
        if (added) {
            delay(1200)
            added = false
        }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = SurfacePrimary,
        scrimColor = TextPrimary.copy(alpha = 0.32f),
        dragHandle = { SheetHandle() },
        shape = RoundedCornerShape(topStart = AppCornerRadius.Sheet, topEnd = AppCornerRadius.Sheet),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 10.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            ProductImage(
                imageUrl = product.imageUrl,
                productName = product.name,
                modifier = Modifier.fillMaxWidth().height(190.dp),
            )
            OutlinedButton(
                onClick = { ProductShareActions.shareProduct(context, product) },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(AppCornerRadius.Button),
                border = BorderStroke(1.dp, BorderColor),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = BrandPrimary,
                    containerColor = AppBackground,
                ),
            ) {
                Icon(Icons.Outlined.Share, contentDescription = null)
                Text(
                    text = "Share",
                    modifier = Modifier.padding(start = 6.dp),
                    style = MaterialTheme.typography.labelLarge,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            SelectionContainer {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text(
                        text = product.name,
                        color = TextPrimary,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = "¥${"%.2f".format(product.price)}",
                        color = PriceColor,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = renderMarkdownText(
                            product.reason.orEmpty(),
                            fallback = "我会围绕这款继续帮你比较价格、肤感、品牌和使用场景。",
                        ),
                        color = TextSecondary,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    ProductEvidenceSection(
                        title = "真实优点",
                        items = product.positiveFeedbackSummary,
                        isRisk = false,
                    )
                    ProductEvidenceSection(
                        title = "风险提示",
                        items = product.riskTags.ifEmpty { product.negativeFeedbackSummary },
                        isRisk = true,
                    )
                }
            }
            QuickActionChips(
                actions = quickActionsForProduct(product),
                onActionClick = onFollowUp,
            )
            ProductFocusInputBar(onSend = onFollowUp)
            Button(
                onClick = {
                    added = true
                    onAddToCart(product)
                },
                modifier = Modifier.fillMaxWidth(),
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
                    text = "加购",
                    modifier = Modifier.padding(start = 6.dp),
                    color = TextOnBrand,
                    style = MaterialTheme.typography.labelLarge,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (added) {
                Text(
                    text = "Added to cart",
                    color = BrandPrimary,
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.padding(start = 4.dp),
                )
            }
            OutlinedButton(
                onClick = { onFollowUp("围绕这款继续聊") },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(AppCornerRadius.Button),
                border = BorderStroke(1.dp, BorderColor),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = BrandPrimary,
                    containerColor = AppBackground,
                ),
            ) {
                Text(
                    "围绕这款继续聊",
                    style = MaterialTheme.typography.labelLarge,
                )
            }
        }
    }
}

@Composable
private fun ProductEvidenceSection(
    title: String,
    items: List<String>,
    isRisk: Boolean,
) {
    val visibleItems = productDetailEvidenceItems(items)
    if (visibleItems.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = title,
            color = if (isRisk) PriceColor else TextPrimary,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
        )
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 168.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            visibleItems.forEach { item ->
                Text(
                    text = item,
                    color = TextSecondary,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

internal fun productDetailEvidenceItems(items: List<String>): List<String> =
    items.map { it.trim() }.filter { it.isNotEmpty() }

@Composable
private fun SheetHandle() {
    Box(
        modifier = Modifier
            .padding(top = 12.dp, bottom = 4.dp)
            .size(width = 42.dp, height = 4.dp)
            .background(BorderColor, RoundedCornerShape(999.dp)),
    )
}
