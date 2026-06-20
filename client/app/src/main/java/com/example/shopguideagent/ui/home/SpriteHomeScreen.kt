package com.example.shopguideagent.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme

@Composable
fun SpriteHomeScreen(
    state: SpriteHomeUiState,
    onAction: (SpriteHomeAction) -> Unit,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { stageState, stageModifier ->
        SpriteStage(state = stageState, modifier = stageModifier)
    },
) {
    BoxWithConstraints(
        modifier = modifier
            .fillMaxSize()
            .testTag("sprite_home")
            .background(RoomBackgroundBrush),
    ) {
        RoomBackgroundDecorations()
        val compact = maxHeight < 720.dp
        Column(
            modifier = Modifier
                .fillMaxSize()
                .safeDrawingPadding()
                .padding(horizontal = 18.dp, vertical = if (compact) 10.dp else 16.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                UserProfileCard(
                    fireValue = state.userProfile.firePoints,
                    identity = state.userProfile.identityTitle,
                    identityBadge = state.userProfile.identityLevel,
                    userAvatarUri = state.userProfile.avatarUrl,
                    partnerAvatarUri = state.userProfile.partnerAvatarUrl,
                    modifier = Modifier.weight(1f, fill = false),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    RoundIconButton(
                        icon = Icons.Outlined.MoreHoriz,
                        contentDescription = "更多",
                        onClick = { onAction(SpriteHomeAction.MenuClicked) },
                    )
                    RoundIconButton(
                        icon = Icons.Outlined.Close,
                        contentDescription = "关闭",
                        onClick = { onAction(SpriteHomeAction.CloseClicked) },
                    )
                }
            }

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
            ) {
                avatarStage(
                    state.toAvatarStageUiState(),
                    Modifier
                        .align(Alignment.Center)
                        .fillMaxWidth()
                        .height(if (compact) 380.dp else 460.dp),
                )
                state.newOutfitHint?.let { hint ->
                    NewOutfitHintCard(
                        state = hint,
                        onAction = onAction,
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(top = if (compact) 18.dp else 34.dp),
                    )
                }
            }

            Column(
                modifier = Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(if (compact) 10.dp else 14.dp),
            ) {
                IntimacyPanel(
                    spriteName = state.spiritProgress.spiritName,
                    level = state.spiritProgress.level,
                    intimacy = state.spiritProgress.currentIntimacy,
                    intimacyMax = state.spiritProgress.requiredIntimacy,
                    subtitle = state.spiritProgress.subtitle,
                    intimacyLabel = state.spiritProgress.intimacyLabel,
                    modifier = Modifier.fillMaxWidth(),
                )
                BottomActionBar(
                    earnedStars = state.earnedStars,
                    onAction = onAction,
                    modifier = Modifier
                        .widthIn(max = 520.dp)
                        .fillMaxWidth(),
                )
                DailyTaskBar(
                    state = state.dailyTask,
                    onAction = onAction,
                    modifier = Modifier.widthIn(max = 560.dp),
                )
            }
        }
    }
}

private val RoomBackgroundBrush = Brush.verticalGradient(
    colors = listOf(SpriteHomeTokens.RoomTop, SpriteHomeTokens.RoomMiddle, SpriteHomeTokens.RoomLight, SpriteHomeTokens.RoomBottom),
)

@Composable
private fun RoomBackgroundDecorations() {
    Box(modifier = Modifier.fillMaxSize()) {
        Box(
            modifier = Modifier
                .align(Alignment.TopStart)
                .offset(x = (-70).dp, y = 80.dp)
                .size(230.dp)
                .clip(CircleShape)
                .background(Color.White.copy(alpha = 0.16f)),
        )
        Box(
            modifier = Modifier
                .align(Alignment.TopCenter)
                .offset(y = 150.dp)
                .size(width = 260.dp, height = 170.dp)
                .clip(RoundedCornerShape(42.dp))
                .background(Color.White.copy(alpha = 0.12f)),
        )
        Box(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .offset(y = (-210).dp)
                .size(width = 340.dp, height = 74.dp)
                .clip(CircleShape)
                .background(Color(0x33FFF8E1)),
        )
        Box(
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .offset(x = 52.dp, y = (-40).dp)
                .size(160.dp)
                .clip(CircleShape)
                .background(Color(0x22FFFFFF)),
        )
    }
}

@Composable
private fun RoundIconButton(
    icon: ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier.size(56.dp),
        shape = CircleShape,
        color = SpriteHomeTokens.Panel,
        shadowElevation = 6.dp,
    ) {
        IconButton(onClick = onClick) {
            Icon(icon, contentDescription = contentDescription, tint = Color(0xFF4A3524), modifier = Modifier.size(30.dp))
        }
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun SpriteHomeScreenIdlePreview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(state = SpriteHomePreviewData.idle, onAction = {})
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun SpriteHomeScreenSearchingPreview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(state = SpriteHomePreviewData.searching, onAction = {})
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun SpriteHomeScreenPresentingPreview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(state = SpriteHomePreviewData.presenting, onAction = {})
    }
}

@Preview(showBackground = true, widthDp = 360, heightDp = 680)
@Composable
private fun SpriteHomeScreenCompactPreview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(state = SpriteHomePreviewData.celebrating, onAction = {})
    }
}
