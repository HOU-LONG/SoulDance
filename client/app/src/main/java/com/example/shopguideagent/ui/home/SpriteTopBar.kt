package com.example.shopguideagent.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.VolumeOff
import androidx.compose.material.icons.automirrored.outlined.VolumeUp
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme

@Composable
fun SpriteTopBar(
    userProfile: UserProfileUiState,
    speakerEnabled: Boolean,
    onSpeakerToggle: () -> Unit,
    onChatClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 0.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        UserProfileCard(
            fireValue = userProfile.firePoints,
            identity = userProfile.identityTitle,
            identityBadge = userProfile.identityLevel,
            userAvatarUri = userProfile.avatarUrl,
            partnerAvatarUri = userProfile.partnerAvatarUrl,
        )

        Row(
            modifier = Modifier.padding(top = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
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
                tint = Color(0xFF5B422A),
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
            userProfile = UserProfileUiState(),
            speakerEnabled = true,
            onSpeakerToggle = {},
            onChatClick = {},
        )
    }
}
