package com.example.shopguideagent.ui.component

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.ProductUiModel
import com.example.shopguideagent.data.model.QuickActionUiModel
import com.example.shopguideagent.ui.theme.AppCornerRadius
import com.example.shopguideagent.ui.theme.ChipBackground
import com.example.shopguideagent.ui.theme.ChipText

val DefaultQuickActions = listOf(
    QuickActionUiModel("更便宜", "换个更便宜的"),
    QuickActionUiModel("换个品牌", "换个品牌看看"),
)

@Composable
fun QuickActionChips(
    actions: List<QuickActionUiModel> = DefaultQuickActions,
    onActionClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (actions.isEmpty()) return
    FlowRow(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        actions.forEach { action ->
            Text(
                text = action.label,
                modifier = Modifier
                    .background(ChipBackground, RoundedCornerShape(AppCornerRadius.Pill))
                    .clickableWithScale { onActionClick(action.message) }
                    .padding(horizontal = 14.dp, vertical = 9.dp),
                color = ChipText,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Medium,
            )
        }
    }
}

fun quickActionsForProduct(product: ProductUiModel?): List<QuickActionUiModel> {
    if (product == null) return emptyList()
    val actions = mutableListOf<QuickActionUiModel>()
    val brand = product.nameBrandHint()
    if (!brand.isNullOrBlank()) {
        actions += QuickActionUiModel("不要$brand", "不要$brand，换一款")
    }
    actions += QuickActionUiModel("更便宜", "换个更便宜的")

    displayTags(
        generatedTags = product.derivedAttributes.generatedTags.map { it.value },
        fallbackTags = product.tags,
        maxCount = 4,
    ).mapNotNullTo(actions) { tag -> actionForTag(tag) }

    return actions
        .filter { it.label.isNotBlank() && it.message.isNotBlank() }
        .distinctBy { it.label }
        .take(5)
}

private fun ProductUiModel.nameBrandHint(): String? =
    tags.firstOrNull { tag -> name.contains(tag) && tag.length in 2..8 }

private fun actionForTag(tag: String): QuickActionUiModel? =
    when {
        tag.contains("清爽") -> QuickActionUiModel("更清爽", "换一款更清爽的")
        tag.contains("防晒") || tag.contains("户外") || tag.contains("防水") ->
            QuickActionUiModel("更适合户外", "换个更适合户外的")
        tag.contains("敏感") || tag.contains("温和") ->
            QuickActionUiModel("更适合敏感肌", "换个更适合敏感肌的")
        tag.contains("保湿") || tag.contains("修护") ->
            QuickActionUiModel("更保湿修护", "换个更保湿修护的")
        tag.contains("轻薄") || tag.contains("通勤") ->
            QuickActionUiModel("更适合通勤", "换个更适合通勤的")
        tag.contains("无糖") || tag.contains("低糖") ->
            QuickActionUiModel("低糖一点", "换个低糖一点的")
        tag.contains("速溶") || tag.contains("冻干") || tag.contains("咖啡") ->
            QuickActionUiModel("换个咖啡口味", "换个咖啡口味看看")
        tag.length in 2..6 -> QuickActionUiModel("更看重${tag}", "围绕${tag}继续筛")
        else -> null
    }
