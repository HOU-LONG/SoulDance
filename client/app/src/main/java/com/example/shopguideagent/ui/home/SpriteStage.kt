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
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.R
import com.example.shopguideagent.ui.theme.PriceColor
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme
import com.example.shopguideagent.ui.theme.TextPrimary

@Composable
fun SpriteStage(
    avatarState: AvatarState,
    layers: SpriteLayerSet,
    speechText: String?,
    modifier: Modifier = Modifier,
) {
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

    BoxWithConstraints(modifier = modifier, contentAlignment = Alignment.Center) {
        val stageSize = (maxWidth * 0.74f).coerceAtMost(330.dp)
        StageProps(modifier = Modifier.matchParentSize())
        SpeechBubble(
            text = speechText,
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
            Crossfade(targetState = avatarState, label = "spriteBase") { state ->
                Image(
                    painter = painterResource(layers.baseResId ?: R.drawable.shopping),
                    contentDescription = "2D \u7cbe\u7075 $state",
                    modifier = Modifier
                        .size(stageSize * 0.68f)
                        .align(Alignment.Center),
                    contentScale = ContentScale.Fit,
                )
            }
            OutfitLayer(visible = true, modifier = Modifier.align(Alignment.Center))
            AccessoryLayer(visible = true, modifier = Modifier.align(Alignment.Center))
            PropLayer(
                visible = true,
                glowing = avatarState == AvatarState.SEARCHING,
                modifier = Modifier.align(Alignment.BottomEnd),
            )
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
private fun StageProps(modifier: Modifier = Modifier) {
    Box(modifier = modifier) {
        Surface(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .offset(x = 4.dp, y = (-18).dp)
                .size(96.dp),
            shape = CircleShape,
            color = Color.White.copy(alpha = 0.38f),
            shadowElevation = 8.dp,
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(Icons.Outlined.ShoppingCart, contentDescription = null, tint = Color(0xFF63A9F8), modifier = Modifier.size(44.dp))
            }
        }
        Surface(
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .offset(x = (-4).dp, y = (-24).dp)
                .size(width = 104.dp, height = 90.dp),
            shape = RoundedCornerShape(24.dp),
            color = Color(0xFF75BDFB).copy(alpha = 0.72f),
            shadowElevation = 10.dp,
        ) {}
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
private fun OutfitLayer(visible: Boolean, modifier: Modifier = Modifier) {
    AnimatedVisibility(visible = visible, modifier = modifier) {
        Box(
            modifier = Modifier
                .offset(y = 54.dp)
                .size(width = 130.dp, height = 54.dp)
                .clip(RoundedCornerShape(22.dp))
                .background(Color(0xAA4DA9FF)),
        )
    }
}

@Composable
private fun AccessoryLayer(visible: Boolean, modifier: Modifier = Modifier) {
    AnimatedVisibility(visible = visible, modifier = modifier) {
        Box(
            modifier = Modifier
                .offset(y = (-34).dp)
                .size(width = 160.dp, height = 24.dp)
                .clip(RoundedCornerShape(999.dp))
                .background(Color(0x8848C7FF)),
        )
    }
}

@Composable
private fun PropLayer(visible: Boolean, glowing: Boolean, modifier: Modifier = Modifier) {
    val alpha by animateFloatAsState(if (glowing) 1f else 0.78f, label = "propGlow")
    AnimatedVisibility(visible = visible, modifier = modifier) {
        Surface(
            modifier = Modifier
                .offset(x = (-42).dp, y = (-76).dp)
                .size(58.dp)
                .alpha(alpha),
            shape = RoundedCornerShape(18.dp),
            color = Color(0xFF4BCBFF),
            shadowElevation = if (glowing) 14.dp else 6.dp,
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(Icons.Outlined.ShoppingCart, contentDescription = null, tint = Color.White, modifier = Modifier.size(30.dp))
            }
        }
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
                text = "\u597d\u7269\u53d1\u73b0",
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
        SpriteStage(
            avatarState = AvatarState.SEARCHING,
            layers = SpriteLayerSet(),
            speechText = "\u6b63\u5728\u627e\u597d\u7269",
        )
    }
}
