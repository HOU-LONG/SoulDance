package com.example.shopguideagent.ui.component

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.BundleUiModel
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.QuickActionUiModel
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun BundleSection(
    bundle: BundleUiModel,
    onAddProduct: (ProductUiModel) -> Unit,
    onProductAnchorTap: (String) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(top = 4.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            bundle.title,
            color = TextPrimary,
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        bundle.groups.forEach { group ->
            BundleGroupCard(group = group, onAddProduct = onAddProduct, onProductAnchorTap = onProductAnchorTap)
        }
        if (bundle.actions.isNotEmpty()) {
            QuickActionChips(
                actions = bundle.actions.map { QuickActionUiModel(it) },
                onActionClick = {},
            )
        }
    }
}
