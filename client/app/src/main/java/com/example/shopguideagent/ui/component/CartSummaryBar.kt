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
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.CartUiState
import com.example.shopguideagent.ui.home.FireRewardCalculator
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderColor
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.DividerColor
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShadowColorStrong
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnDark
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun CartSummaryBar(
    state: CartUiState,
    onToggleAll: (Boolean) -> Unit,
    onCheckout: () -> Unit,
) {
    val allSelected = state.items.isNotEmpty() && state.items.all { it.selected }
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = SurfacePrimary,
        shape = RoundedCornerShape(
            topStart = AppCornerRadius.Sheet,
            topEnd = AppCornerRadius.Sheet,
        ),
        border = BorderStroke(1.dp, DividerColor),
        tonalElevation = 2.dp,
        shadowElevation = 8.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Checkbox(checked = allSelected, onCheckedChange = onToggleAll)
            Text("全选", color = TextPrimary, style = MaterialTheme.typography.bodyMedium)
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(
                    "合计 ¥${"%.2f".format(state.totalPrice)}",
                    color = PriceColor,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleMedium,
                )
                val discount = FireRewardCalculator.discountAmount(886, state.totalPrice)
                if (discount > 0) {
                    Text(
                        "可用 ⭐ 抵扣 ¥${"%.2f".format(discount)}",
                        color = PriceColor.copy(alpha = 0.8f),
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
            Button(
                onClick = onCheckout,
                enabled = state.selectedCount > 0,
                shape = RoundedCornerShape(AppCornerRadius.Control),
                colors = ButtonDefaults.buttonColors(
                    containerColor = BrandPrimary,
                    contentColor = TextOnDark,
                ),
            ) {
                Text("去结算 (${state.selectedCount})")
            }
        }
    }
}
