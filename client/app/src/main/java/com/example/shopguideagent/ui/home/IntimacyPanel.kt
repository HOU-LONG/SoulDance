package com.example.shopguideagent.ui.home

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary
import com.example.shopguideagent.ui.theme.TextOnBrand

@Composable
fun IntimacyPanel(
    spriteName: String,
    level: Int,
    intimacy: Int,
    intimacyMax: Int,
    subtitle: String,
    intimacyLabel: String,
    modifier: Modifier = Modifier,
) {
    val progress by animateFloatAsState(
        targetValue = if (intimacyMax <= 0) 0f else intimacy.toFloat() / intimacyMax.toFloat(),
        label = "intimacyProgress",
    )
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = spriteName,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = TextPrimary,
            )
            Icon(
                imageVector = Icons.Outlined.Edit,
                contentDescription = "\u7f16\u8f91\u7cbe\u7075\u540d",
                modifier = Modifier.padding(start = 8.dp),
                tint = TextSecondary,
            )
        }
        Row(
            modifier = Modifier.widthIn(max = 320.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Surface(
                shape = RoundedCornerShape(999.dp),
                color = PriceColor,
                shadowElevation = 4.dp,
            ) {
                Text(
                    text = "${level}\u7ea7",
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 5.dp),
                    style = MaterialTheme.typography.labelLarge,
                    color = TextOnBrand,
                    fontWeight = FontWeight.Bold,
                )
            }
            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(22.dp)
                    .clip(RoundedCornerShape(999.dp))
                    .background(Color(0x55FFFFFF))
                    .testTag("intimacy_progress"),
                contentAlignment = Alignment.CenterStart,
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth(progress.coerceIn(0f, 1f))
                        .height(22.dp)
                        .background(Brush.horizontalGradient(listOf(Color(0xFFFFA726), Color(0xFFFFD86B)))),
                )
                Text(
                    text = "$intimacy / $intimacyMax",
                    modifier = Modifier.align(Alignment.Center),
                    style = MaterialTheme.typography.labelLarge,
                    color = Color.White,
                    fontWeight = FontWeight.SemiBold,
                )
            }
            Surface(shape = RoundedCornerShape(999.dp), color = Color.White.copy(alpha = 0.62f)) {
                Row(
                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.Favorite, contentDescription = null, tint = Color(0xFFFF5A52))
                    Text(
                        text = intimacyLabel,
                        modifier = Modifier.padding(start = 4.dp),
                        style = MaterialTheme.typography.labelMedium,
                        color = TextSecondary,
                    )
                }
            }
        }
        Surface(shape = RoundedCornerShape(999.dp), color = Color.White.copy(alpha = 0.62f)) {
            Text(
                text = subtitle,
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 7.dp),
                style = MaterialTheme.typography.labelLarge,
                color = TextSecondary,
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun IntimacyPanelPreview() {
    ShopGuideAgentTheme {
        IntimacyPanel("\u8d2d\u8d2d\u5b9d\u5b9d", 22, 115, 2000, "\u6211\u7684\u4e13\u5c5e\u667a\u80fd\u8d2d\u7269\u5c0f\u52a9\u624b", "\u4eb2\u5bc6\u5ea6")
    }
}
