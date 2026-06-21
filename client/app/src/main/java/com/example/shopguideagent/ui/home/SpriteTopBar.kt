package com.example.shopguideagent.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowForwardIos
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.component.CartBadge
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.SpritePanel
import com.example.shopguideagent.ui.theme.SpritePrimaryButton
import com.example.shopguideagent.ui.theme.SpriteVoiceBarBackground
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextSecondary

@Composable
fun SpriteTopBar(
    cartCount: Int,
    onSettingsClick: () -> Unit,
    onChatModeClick: () -> Unit,
    onCartClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(64.dp)
            .padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        IconButton(
            onClick = onSettingsClick,
            modifier = Modifier
                .size(48.dp)
                .clip(CircleShape)
                .background(SpritePanel),
        ) {
            Icon(
                imageVector = Icons.Outlined.Settings,
                contentDescription = "设置",
                tint = SpriteVoiceBarBackground,
                modifier = Modifier.size(24.dp),
            )
        }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = "精灵空间",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = TextPrimary,
            )
        }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Surface(
                onClick = onChatModeClick,
                shape = RoundedCornerShape(999.dp),
                color = SpritePrimaryButton,
                shadowElevation = 4.dp,
            ) {
                Row(
                    modifier = Modifier
                        .height(36.dp)
                        .padding(horizontal = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(
                        text = "聊天模式",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = Color(0xFF4A3524),
                    )
                    Icon(
                        imageVector = Icons.Outlined.ArrowForwardIos,
                        contentDescription = null,
                        tint = Color(0xFF4A3524),
                        modifier = Modifier.size(14.dp),
                    )
                }
            }

            CartBadge(count = cartCount, onClick = onCartClick)
        }
    }
}

@Preview(showBackground = true, widthDp = 390)
@Composable
private fun SpriteTopBarPreview() {
    ShopGuideAgentTheme {
        SpriteTopBar(
            cartCount = 2,
            onSettingsClick = {},
            onChatModeClick = {},
            onCartClick = {},
        )
    }
}
