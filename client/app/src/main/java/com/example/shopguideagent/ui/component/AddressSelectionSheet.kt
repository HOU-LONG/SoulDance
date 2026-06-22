package com.example.shopguideagent.ui.component

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.AddressUiModel
import com.example.shopguideagent.data.model.OrderFlowState
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.BorderColor
import com.example.shopguideagent.ui.theme.BrandPrimary
import com.example.shopguideagent.ui.theme.SurfacePrimary
import com.example.shopguideagent.ui.theme.TextOnDark
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddressSelectionSheet(
    state: OrderFlowState.AddressRequired,
    onDismiss: () -> Unit,
    onSelectAddress: (String) -> Unit,
) {
    var selectedId by remember(state.orderId, state.addresses) {
        mutableStateOf(state.addresses.firstOrNull { it.isDefault }?.addressId ?: state.addresses.firstOrNull()?.addressId)
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = SurfacePrimary,
        scrimColor = TextPrimary.copy(alpha = 0.32f),
        shape = RoundedCornerShape(topStart = AppCornerRadius.Sheet, topEnd = AppCornerRadius.Sheet),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 12.dp)
                .padding(bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                "选择收货地址",
                color = TextPrimary,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                "订单 ${state.orderId}",
                color = TextSecondary,
                style = MaterialTheme.typography.bodySmall,
            )

            state.addresses.forEach { address ->
                AddressRow(
                    address = address,
                    selected = address.addressId == selectedId,
                    onClick = { selectedId = address.addressId },
                )
            }

            if (!state.errorMessage.isNullOrBlank()) {
                Text(
                    state.errorMessage,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            Button(
                onClick = { selectedId?.let(onSelectAddress) },
                enabled = selectedId != null && !state.isLoading,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(AppCornerRadius.Control),
                colors = ButtonDefaults.buttonColors(
                    containerColor = BrandPrimary,
                    contentColor = TextOnDark,
                ),
            ) {
                if (state.isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.padding(end = 8.dp),
                        color = TextOnDark,
                        strokeWidth = 2.dp,
                    )
                }
                Text("使用该地址")
            }
        }
    }
}

@Composable
private fun AddressRow(
    address: AddressUiModel,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(AppCornerRadius.Card),
        color = SurfacePrimary,
        border = BorderStroke(1.dp, if (selected) BrandPrimary else BorderColor),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            RadioButton(selected = selected, onClick = onClick)
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(address.name, color = TextPrimary, fontWeight = FontWeight.SemiBold)
                    Text(address.phone, color = TextSecondary)
                    if (address.isDefault) {
                        Text("默认", color = BrandPrimary, style = MaterialTheme.typography.labelSmall)
                    }
                }
                Text(
                    "${address.province}${address.city}${address.detail}",
                    color = TextSecondary,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}
