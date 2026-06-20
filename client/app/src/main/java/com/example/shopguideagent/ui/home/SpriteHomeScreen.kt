package com.example.shopguideagent.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.component.clickableWithScale
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextOnBrand
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun SpriteHomeScreen(
    state: SpriteHomeUiState,
    onDressClick: () -> Unit,
    onEarnFireClick: () -> Unit,
    onGuideClick: () -> Unit,
    onDailyTaskClick: () -> Unit,
    onMenuClick: () -> Unit,
    onCloseClick: () -> Unit,
    onNewOutfitClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BoxWithConstraints(
        modifier = modifier
            .fillMaxSize()
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
                    fireValue = state.fireValue,
                    identity = state.identity,
                    identityBadge = state.identityBadge,
                    userAvatarUri = state.userAvatarUri,
                    partnerAvatarUri = state.partnerAvatarUri,
                    modifier = Modifier.weight(1f, fill = false),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    RoundIconButton(icon = Icons.Outlined.MoreHoriz, contentDescription = "\u66f4\u591a", onClick = onMenuClick)
                    RoundIconButton(icon = Icons.Outlined.Close, contentDescription = "\u5173\u95ed", onClick = onCloseClick)
                }
            }

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
            ) {
                SpriteStage(
                    avatarState = state.avatarState,
                    layers = state.spriteLayers,
                    speechText = state.speechText,
                    modifier = Modifier
                        .align(Alignment.Center)
                        .fillMaxWidth()
                        .height(if (compact) 380.dp else 460.dp),
                )
                NewOutfitCard(
                    title = state.newOutfitTitle,
                    badge = state.newOutfitBadge,
                    onClick = onNewOutfitClick,
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(top = if (compact) 18.dp else 34.dp),
                )
            }

            Column(
                modifier = Modifier.fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(if (compact) 10.dp else 14.dp),
            ) {
                IntimacyPanel(
                    spriteName = state.spriteName,
                    level = state.level,
                    intimacy = state.intimacy,
                    intimacyMax = state.intimacyMax,
                    subtitle = state.subtitle,
                    intimacyLabel = state.intimacyLabel,
                    modifier = Modifier.fillMaxWidth(),
                )
                BottomActionBar(
                    earnedStars = state.earnedStars,
                    onDressClick = onDressClick,
                    onEarnFireClick = onEarnFireClick,
                    onGuideClick = onGuideClick,
                    modifier = Modifier
                        .widthIn(max = 520.dp)
                        .fillMaxWidth(),
                )
                DailyTaskBar(
                    title = state.dailyTaskTitle,
                    description = state.dailyTaskDescription,
                    progress = state.dailyTaskProgress,
                    target = state.dailyTaskTarget,
                    onClick = onDailyTaskClick,
                    modifier = Modifier.widthIn(max = 560.dp),
                )
            }
        }
    }
}

private val RoomBackgroundBrush = Brush.verticalGradient(
    colors = listOf(Color(0xFFB87942), Color(0xFFF4C282), Color(0xFFFFE3B5), Color(0xFFE0A86C)),
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
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier.size(56.dp),
        shape = CircleShape,
        color = Color.White.copy(alpha = 0.72f),
        shadowElevation = 6.dp,
    ) {
        IconButton(onClick = onClick) {
            Icon(icon, contentDescription = contentDescription, tint = Color(0xFF4A3524), modifier = Modifier.size(30.dp))
        }
    }
}

@Composable
private fun NewOutfitCard(
    title: String,
    badge: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.clickableWithScale(onClick),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(contentAlignment = Alignment.TopEnd) {
            Surface(
                modifier = Modifier.size(82.dp),
                shape = RoundedCornerShape(24.dp),
                color = Color(0xFF8FD1FF),
                border = BorderStroke(1.dp, Color.White.copy(alpha = 0.85f)),
                shadowElevation = 9.dp,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Outlined.ShoppingCart, contentDescription = null, tint = Color.White, modifier = Modifier.size(42.dp))
                }
            }
            Text(
                text = badge,
                modifier = Modifier
                    .offset(x = 10.dp, y = (-8).dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(Color(0xFFFF4B45))
                    .padding(horizontal = 8.dp, vertical = 5.dp),
                color = TextOnBrand,
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
            )
        }
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = Color(0xFFFFF1AF),
            shadowElevation = 4.dp,
            modifier = Modifier.padding(top = 6.dp),
        ) {
            Text(
                text = title,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                color = TextPrimary,
                style = MaterialTheme.typography.labelLarge,
                textAlign = TextAlign.Center,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun SpriteHomeScreenPreview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(
            state = SpriteHomeUiState(),
            onDressClick = {},
            onEarnFireClick = {},
            onGuideClick = {},
            onDailyTaskClick = {},
            onMenuClick = {},
            onCloseClick = {},
            onNewOutfitClick = {},
        )
    }
}

@Preview(showBackground = true, widthDp = 360, heightDp = 680)
@Composable
private fun SpriteHomeScreenCompactPreview() {
    ShopGuideAgentTheme {
        SpriteHomeScreen(
            state = SpriteHomeUiState(avatarState = AvatarState.CELEBRATING, speechText = "\u52a0\u8d2d\u6210\u529f\uff0c\u4eb2\u5bc6\u5ea6\u63d0\u5347"),
            onDressClick = {},
            onEarnFireClick = {},
            onGuideClick = {},
            onDailyTaskClick = {},
            onMenuClick = {},
            onCloseClick = {},
            onNewOutfitClick = {},
        )
    }
}
