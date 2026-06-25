package com.example.shopguideagent.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun DailyTaskBar(
    state: DailyTaskUiState,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .height(32.dp)
            .testTag("daily_task_bar")
            .clickableWithScale { onAction(SpriteHomeAction.EarnFireClicked) },
        shape = RoundedCornerShape(999.dp),
        color = Color.White.copy(alpha = 0.72f),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.78f)),
        shadowElevation = 2.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = state.description,
                style = MaterialTheme.typography.bodySmall,
                color = TextPrimary,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun DailyTaskBarPreview() {
    ShopGuideAgentTheme {
        DailyTaskBar(DailyTaskUiState(), onAction = {})
    }
}

@Preview(showBackground = true)
@Composable
private fun DailyTaskBarCompletedPreview() {
    ShopGuideAgentTheme {
        DailyTaskBar(DailyTaskUiState(currentCount = 1, completed = true), onAction = {})
    }
}
