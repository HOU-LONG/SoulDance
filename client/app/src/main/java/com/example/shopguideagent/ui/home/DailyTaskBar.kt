package com.example.shopguideagent.ui.home

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AssignmentTurnedIn
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextOnBrand
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
            .testTag("daily_task_bar")
            .clickableWithScale { onAction(SpriteHomeAction.EarnFireClicked) },
        shape = RoundedCornerShape(34.dp),
        color = Color.White.copy(alpha = 0.72f),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.78f)),
        shadowElevation = 8.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 18.dp, vertical = 13.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(shape = RoundedCornerShape(18.dp), color = Color.White.copy(alpha = 0.9f), shadowElevation = 3.dp) {
                Icon(
                    Icons.Outlined.AssignmentTurnedIn,
                    contentDescription = null,
                    tint = PriceColor,
                    modifier = Modifier.padding(10.dp).size(30.dp),
                )
            }
            Spacer(Modifier.width(14.dp))
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(state.title, style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                Text(state.description, style = MaterialTheme.typography.titleSmall, color = TextPrimary, fontWeight = FontWeight.SemiBold)
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("${state.currentCount} / ${state.targetCount}", style = MaterialTheme.typography.titleSmall, color = TextPrimary, fontWeight = FontWeight.SemiBold)
                Box(
                    modifier = Modifier
                        .padding(top = 5.dp)
                        .size(width = 54.dp, height = 6.dp)
                        .clip(RoundedCornerShape(999.dp))
                        .background(Color(0x333B2B1D)),
                    contentAlignment = Alignment.CenterStart,
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth(state.progressFraction)
                            .height(6.dp)
                            .background(PriceColor),
                    )
                }
            }
            Spacer(Modifier.width(12.dp))
            Button(
                enabled = !state.claimed,
                onClick = { onAction(SpriteHomeAction.EarnFireClicked) },
                colors = ButtonDefaults.buttonColors(containerColor = SpriteHomeTokens.PrimaryButton, contentColor = TextOnBrand),
                shape = RoundedCornerShape(999.dp),
            ) {
                Text(state.buttonText, fontWeight = FontWeight.Bold)
            }
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
