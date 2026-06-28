package com.example.shopguideagent.ui.home

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.VolumeOff
import androidx.compose.material.icons.automirrored.outlined.VolumeUp
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.Checkroom
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.example.shopguideagent.R
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextPrimary
import com.example.shopguideagent.ui.theme.TextTertiary

@Composable
fun SpriteTopBar(
    userAvatarUri: String?,
    speakerEnabled: Boolean,
    onSpeakerToggle: () -> Unit,
    onChatClick: () -> Unit,
    onHistoryClick: () -> Unit,
    modifier: Modifier = Modifier,
    // Task 12: 新增衣橱和购物车入口（替代 BottomActionBar）
    cartBadgeCount: Int = 0,
    onWardrobeClick: () -> Unit = {},
    onCartClick: () -> Unit = {},
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 0.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        HistoryAvatarButton(
            avatarUri = userAvatarUri,
            onClick = onHistoryClick,
        )

        Row(
            modifier = Modifier.padding(top = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Task 12: 衣橱按钮
            CircleIconButton(
                icon = Icons.Outlined.Checkroom,
                contentDescription = "装扮衣橱",
                onClick = onWardrobeClick,
            )
            // Task 12: 购物车按钮
            BadgedBox(
                badge = { if (cartBadgeCount > 0) Badge { Text("$cartBadgeCount") } },
            ) {
                CircleIconButton(
                    icon = Icons.Outlined.ShoppingCart,
                    contentDescription = "购物车",
                    onClick = onCartClick,
                )
            }
            CircleIconButton(
                icon = if (speakerEnabled) Icons.AutoMirrored.Outlined.VolumeUp else Icons.AutoMirrored.Outlined.VolumeOff,
                contentDescription = if (speakerEnabled) "语音播报开启" else "语音播报关闭",
                onClick = onSpeakerToggle,
            )
            CircleIconButton(
                icon = Icons.Outlined.ChatBubbleOutline,
                contentDescription = "聊天模式",
                onClick = onChatClick,
            )
        }
    }
}

@Composable
private fun HistoryAvatarButton(
    avatarUri: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.size(42.dp),
        shape = CircleShape,
        color = Color.White.copy(alpha = 0.72f),
        shadowElevation = 4.dp,
    ) {
        IconButton(
            onClick = onClick,
            modifier = Modifier.size(42.dp),
        ) {
            if (!avatarUri.isNullOrBlank()) {
                AsyncImage(
                    model = avatarUri,
                    contentDescription = "用户头像",
                    modifier = Modifier
                        .size(36.dp)
                        .clip(CircleShape)
                        .border(2.dp, Color.White, CircleShape),
                    contentScale = ContentScale.Crop,
                )
            } else {
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .clip(CircleShape)
                        .background(Color.White)
                        .border(2.dp, Color.White, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Image(
                        painter = painterResource(R.drawable.shopping),
                        contentDescription = "默认头像",
                        modifier = Modifier.size(28.dp),
                        contentScale = ContentScale.Crop,
                    )
                    Icon(
                        imageVector = Icons.Outlined.Person,
                        contentDescription = null,
                        tint = TextTertiary,
                        modifier = Modifier.size(16.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun CircleIconButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    contentDescription: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.size(34.dp),
        shape = CircleShape,
        color = Color.White.copy(alpha = 0.45f),
        shadowElevation = 3.dp,
    ) {
        IconButton(
            onClick = onClick,
            modifier = Modifier
                .size(34.dp)
                .clip(CircleShape)
                .background(Color.Transparent),
        ) {
            Icon(
                imageVector = icon,
                contentDescription = contentDescription,
                tint = TextPrimary,
                modifier = Modifier.size(22.dp),
            )
        }
    }
}

@Preview(showBackground = true, widthDp = 390)
@Composable
private fun SpriteTopBarPreview() {
    ShopGuideAgentTheme {
        SpriteTopBar(
            userAvatarUri = null,
            speakerEnabled = true,
            onSpeakerToggle = {},
            onChatClick = {},
            onHistoryClick = {},
        )
    }
}
