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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun IntimacyPanel(
    spriteName: String,
    level: Int,
    intimacy: Int,
    intimacyMax: Int,
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
        Text(
            text = spriteName,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = TextPrimary,
        )
        Row(
            modifier = Modifier
                .widthIn(max = 340.dp)
                .fillMaxWidth()
                .padding(horizontal = 18.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Surface(
                shape = RoundedCornerShape(999.dp),
                color = PriceColor,
                shadowElevation = 4.dp,
            ) {
                Text(
                    text = "${level}级",
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
                    .padding(2.dp),
                contentAlignment = Alignment.CenterStart,
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth(progress.coerceIn(0f, 1f))
                        .height(18.dp)
                        .clip(RoundedCornerShape(999.dp))
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
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun IntimacyPanelPreview() {
    ShopGuideAgentTheme {
        IntimacyPanel(
            spriteName = "灵舞",
            level = 22,
            intimacy = 215,
            intimacyMax = 2000,
        )
    }
}
