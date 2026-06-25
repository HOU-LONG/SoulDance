package com.example.shopguideagent.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.R
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

/** 一个可选服装项的展示模型（语义 id + 文案），drawable 由 [SpriteAssetRegistry] 解析。 */
data class OutfitChoice(
    val outfitId: String,
    val name: String,
    val description: String,
)

private val WardrobeOutfits = listOf(
    OutfitChoice(SpriteAssetRegistry.OUTFIT_DEFAULT, "默认装扮", "米色长裙 · 全状态可用"),
    OutfitChoice(SpriteAssetRegistry.OUTFIT_HOME_ADVISOR, "家居顾问", "绿色家居 · 待机/展示专属"),
)

/**
 * 装扮衣橱：在 DEFAULT 与 HOME_ADVISOR 之间切换并保存当前选择。
 * 预览图直接用状态矩阵解析的真实素材；缺失状态由 registry fallback，不伪造素材。
 */
@Composable
fun WardrobeScreen(
    currentOutfitId: String,
    onOutfitSelected: (String) -> Unit,
    onBackClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val choices = remember { WardrobeOutfits }

    Box(
        modifier = modifier
            .fillMaxSize()
            .testTag("wardrobe_screen"),
    ) {
        Image(
            painter = painterResource(R.drawable.sprite_room_background),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier.matchParentSize(),
        )

        Column(
            modifier = Modifier
                .fillMaxSize()
                .safeDrawingPadding()
                .padding(horizontal = 16.dp, vertical = 8.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBackClick, modifier = Modifier.testTag("wardrobe_back")) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回首页", tint = TextPrimary)
                }
                Spacer(Modifier.size(4.dp))
                Text("装扮衣橱", style = MaterialTheme.typography.headlineSmall, color = TextPrimary, fontWeight = FontWeight.Bold)
            }

            // 当前选中服装的大预览（展示姿态）
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                contentAlignment = Alignment.Center,
            ) {
                Image(
                    painter = painterResource(
                        SpriteAssetRegistry.avatarDrawable(currentOutfitId, AvatarState.PRESENTING),
                    ),
                    contentDescription = "当前装扮预览",
                    contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxSize(),
                )
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                choices.forEach { choice ->
                    OutfitCard(
                        choice = choice,
                        selected = choice.outfitId == currentOutfitId,
                        onClick = { onOutfitSelected(choice.outfitId) },
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun OutfitCard(
    choice: OutfitChoice,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .testTag("outfit_${choice.outfitId}")
            .clickableWithScale(onClick),
        shape = RoundedCornerShape(24.dp),
        color = if (selected) androidx.compose.ui.graphics.Color(0xFFFFF0BB) else androidx.compose.ui.graphics.Color.White.copy(alpha = 0.82f),
        border = BorderStroke(
            width = if (selected) 2.dp else 1.dp,
            color = if (selected) PriceColor else androidx.compose.ui.graphics.Color.White.copy(alpha = 0.8f),
        ),
        shadowElevation = if (selected) 10.dp else 3.dp,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Image(
                painter = painterResource(
                    SpriteAssetRegistry.avatarDrawable(choice.outfitId, AvatarState.IDLE),
                ),
                contentDescription = choice.name,
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(112.dp),
            )
            Text(choice.name, style = MaterialTheme.typography.titleMedium, color = TextPrimary, fontWeight = FontWeight.Bold)
            Text(choice.description, style = MaterialTheme.typography.bodySmall, color = TextSecondary)
            Text(
                text = if (selected) "使用中" else "点击切换",
                style = MaterialTheme.typography.labelMedium,
                color = if (selected) PriceColor else TextSecondary,
                fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
            )
        }
    }
}

@Preview(name = "Wardrobe DEFAULT 393", showBackground = true, widthDp = 393, heightDp = 873)
@Composable
private fun WardrobeDefaultPreview() {
    ShopGuideAgentTheme {
        WardrobeScreen(
            currentOutfitId = SpriteAssetRegistry.OUTFIT_DEFAULT,
            onOutfitSelected = {},
            onBackClick = {},
        )
    }
}

@Preview(name = "Wardrobe HOME_ADVISOR 393", showBackground = true, widthDp = 393, heightDp = 873)
@Composable
private fun WardrobeHomeAdvisorPreview() {
    ShopGuideAgentTheme {
        WardrobeScreen(
            currentOutfitId = SpriteAssetRegistry.OUTFIT_HOME_ADVISOR,
            onOutfitSelected = {},
            onBackClick = {},
        )
    }
}
