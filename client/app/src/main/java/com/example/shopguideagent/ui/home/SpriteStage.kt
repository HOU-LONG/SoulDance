package com.example.shopguideagent.ui.home

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme

@Composable
fun SpriteStage(
    state: AvatarStageUiState,
    modifier: Modifier = Modifier,
) {
    val avatarState = state.avatarState
    val layers = SpriteAssetRegistry.layersFor(state.appearance, avatarState)
    val infinite = rememberInfiniteTransition(label = "spriteStageLoop")
    val idleFloat by infinite.animateFloat(
        initialValue = -5f,
        targetValue = 7f,
        animationSpec = infiniteRepeatable(tween(1800), repeatMode = RepeatMode.Reverse),
        label = "idleFloat",
    )
    val glow by infinite.animateFloat(
        initialValue = 0.35f,
        targetValue = 0.9f,
        animationSpec = infiniteRepeatable(tween(850), repeatMode = RepeatMode.Reverse),
        label = "searchGlow",
    )
    val celebrateScale by animateFloatAsState(
        targetValue = if (avatarState == AvatarState.CELEBRATING || avatarState == AvatarState.LEVEL_UP) 1.06f else 1f,
        animationSpec = tween(220),
        label = "celebrateScale",
    )

    BoxWithConstraints(modifier = modifier.testTag("sprite_stage"), contentAlignment = Alignment.Center) {
        val stageSize = (maxWidth * 0.74f).coerceAtMost(330.dp)
        SpeechBubble(
            state = state.speechBubble,
            modifier = Modifier
                .align(Alignment.TopCenter)
                .offset(y = 2.dp),
        )
        Box(
            modifier = Modifier
                .align(Alignment.Center)
                .offset(y = idleFloat.dp + 28.dp)
                .size(stageSize)
                .scale(celebrateScale),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .size(width = stageSize * 0.84f, height = 42.dp)
                    .clip(CircleShape)
                    .background(Color(0x2A6A4325)),
            )
            SearchGlow(visible = avatarState == AvatarState.SEARCHING, alpha = glow)
            Crossfade(targetState = avatarState, label = "spriteBase") { target ->
                Image(
                    painter = painterResource(layers.baseResId),
                    contentDescription = "2D 精灵 $target",
                    modifier = Modifier
                        .size(stageSize * 0.68f)
                        .align(Alignment.Center),
                    contentScale = ContentScale.Fit,
                )
            }
            CelebrationParticles(
                visible = avatarState == AvatarState.CELEBRATING || avatarState == AvatarState.LEVEL_UP,
                modifier = Modifier.matchParentSize(),
            )
            PresentingCard(
                visible = avatarState == AvatarState.PRESENTING,
                modifier = Modifier
                    .align(Alignment.CenterEnd)
                    .offset(x = 8.dp, y = (-38).dp),
            )
        }
    }
}

@Composable
private fun SearchGlow(visible: Boolean, alpha: Float) {
    AnimatedVisibility(visible = visible, enter = fadeIn()) {
        Box(
            modifier = Modifier
                .size(210.dp)
                .clip(CircleShape)
                .background(
                    Brush.radialGradient(
                        listOf(Color(0xFFFFF59D).copy(alpha = alpha), Color.Transparent),
                    ),
                ),
        )
    }
}

@Composable
private fun CelebrationParticles(visible: Boolean, modifier: Modifier = Modifier) {
    AnimatedVisibility(visible = visible, modifier = modifier, enter = fadeIn()) {
        Box {
            listOf(
                Alignment.TopStart to Pair(34.dp, 36.dp),
                Alignment.TopEnd to Pair((-20).dp, 54.dp),
                Alignment.CenterStart to Pair(8.dp, (-20).dp),
                Alignment.CenterEnd to Pair((-10).dp, 6.dp),
            ).forEach { (alignment, offset) ->
                Icon(
                    Icons.Outlined.Star,
                    contentDescription = null,
                    tint = Color(0xFFFFDA47),
                    modifier = Modifier
                        .align(alignment)
                        .offset(x = offset.first, y = offset.second)
                        .size(24.dp)
                        .graphicsLayer { rotationZ = 12f },
                )
            }
        }
    }
}

@Composable
private fun PresentingCard(visible: Boolean, modifier: Modifier = Modifier) {
    AnimatedVisibility(
        visible = visible,
        enter = fadeIn(tween(220)) + slideInHorizontally(tween(260)) { it / 2 },
        modifier = modifier,
    ) {
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = Color.White.copy(alpha = 0.9f),
            shadowElevation = 8.dp,
        ) {
            Text(
                text = "好物发现",
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                style = MaterialTheme.typography.labelLarge,
                color = PriceColor,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 520)
@Composable
private fun SpriteStagePreview() {
    ShopGuideAgentTheme {
        SpriteStage(state = SpriteHomePreviewData.searching.toAvatarStageUiState())
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 520)
@Composable
private fun SpriteStageLevelUpPreview() {
    ShopGuideAgentTheme {
        SpriteStage(state = SpriteHomePreviewData.levelUp.toAvatarStageUiState())
    }
}
