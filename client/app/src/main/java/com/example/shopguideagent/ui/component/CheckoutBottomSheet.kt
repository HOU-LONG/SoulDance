package com.example.shopguideagent.ui.component

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.CartUiState
import com.example.shopguideagent.data.model.OrderFlowState
import com.example.shopguideagent.ui.home.FireRewardCalculator
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderColor
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.BrandSoft
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnDark
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CheckoutBottomSheet(
    state: CartUiState,
    orderFlowState: OrderFlowState = OrderFlowState.Idle,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
) {
    val preview = orderFlowState as? OrderFlowState.OrderPreview
    val isCreating = orderFlowState is OrderFlowState.Creating
    val isConfirming = preview?.isConfirming == true
    val totalAmount = preview?.totalAmount ?: state.totalPrice
    val itemCount = preview?.itemCount ?: state.selectedCount

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = SurfacePrimary,
        scrimColor = TextPrimary.copy(alpha = 0.32f),
        dragHandle = { SheetHandle() },
        shape = RoundedCornerShape(topStart = AppCornerRadius.Sheet, topEnd = AppCornerRadius.Sheet),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 12.dp)
                .padding(bottom = 32.dp)
                .animateContentSize(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Header
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Surface(
                    shape = RoundedCornerShape(AppCornerRadius.Small),
                    color = BrandSoft,
                    modifier = Modifier.size(44.dp),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            Icons.Outlined.ShoppingCart,
                            contentDescription = null,
                            tint = BrandPrimary,
                            modifier = Modifier.size(24.dp),
                        )
                    }
                }
                Column {
                    Text(
                        "确认订单",
                        color = TextPrimary,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        "已选 ${itemCount} 件商品",
                        color = TextSecondary,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }

            Spacer(modifier = Modifier.height(4.dp))

            if (preview != null) {
                Surface(
                    shape = RoundedCornerShape(AppCornerRadius.Card),
                    color = SurfacePrimary,
                    border = BorderStroke(1.dp, BorderColor),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(
                        modifier = Modifier.padding(horizontal = 18.dp, vertical = 14.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(
                            "收货地址",
                            color = TextSecondary,
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Text(
                            "${preview.selectedAddress.name} ${preview.selectedAddress.phone}",
                            color = TextPrimary,
                            fontWeight = FontWeight.SemiBold,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Text(
                            "${preview.selectedAddress.province}${preview.selectedAddress.city}${preview.selectedAddress.detail}",
                            color = TextSecondary,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }

            // Price row
            Surface(
                shape = RoundedCornerShape(AppCornerRadius.Card),
                color = BrandSoft.copy(alpha = 0.4f),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 18.dp, vertical = 14.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "应付金额",
                        color = TextSecondary,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            "¥${"%.2f".format(totalAmount)}",
                            color = PriceColor,
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.headlineSmall,
                        )
                        val discount = FireRewardCalculator.discountAmount(886, totalAmount)
                        if (discount > 0) {
                            Text(
                                "抵扣后 ¥${"%.2f".format(totalAmount - discount)}",
                                color = PriceColor.copy(alpha = 0.8f),
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(4.dp))

            Button(
                onClick = onConfirm,
                enabled = !isCreating && !isConfirming,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(AppCornerRadius.Control),
                colors = ButtonDefaults.buttonColors(
                    containerColor = BrandPrimary,
                    contentColor = TextOnDark,
                ),
            ) {
                if (isCreating || isConfirming) {
                    CircularProgressIndicator(
                        modifier = Modifier.padding(end = 8.dp),
                        color = TextOnDark,
                        strokeWidth = 2.dp,
                    )
                }
                Text(
                    when {
                        isCreating -> "正在创建订单"
                        isConfirming -> "正在确认"
                        preview != null -> "确认下单"
                        else -> "选择地址并确认"
                    },
                    modifier = Modifier.padding(vertical = 4.dp),
                )
            }
        }
    }
}

@Composable
private fun SheetHandle() {
    Box(
        modifier = Modifier
            .padding(top = 12.dp, bottom = 6.dp)
            .size(width = 40.dp, height = 4.dp)
            .background(BorderColor, RoundedCornerShape(999.dp)),
    )
}
