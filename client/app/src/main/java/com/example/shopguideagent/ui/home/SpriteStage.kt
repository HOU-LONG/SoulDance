package com.example.shopguideagent.ui.home

import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme

/**
 * 2D 精灵舞台：只负责渲染**人物本体**，是 [AvatarStageRenderer] 的 2D 实现。
 *
 * 页面其余组件（背景、道具、特效、气泡、商品卡）不依赖本实现，未来替换 3D 时只需提供新的
 * [AvatarStageRenderer]，无需改动 [SpriteStageArea] 与 [SpriteHomeScreen]。
 *
 * 锚点：人物在给定框内 [ContentScale.Fit] + [Alignment.BottomCenter]，缩放原点固定在底部中心，
 * 保证状态切换与庆祝缩放时脚底/中心不明显跳动。
 */
@Composable
fun SpriteStage(
    state: AvatarStageUiState,
    modifier: Modifier = Modifier,
) {
    val avatarState = state.avatarState
    val infinite = rememberInfiniteTransition(label = "spriteIdleLoop")
    val breathe by infinite.animateFloat(
        initialValue = -6f,
        targetValue = 6f,
        animationSpec = infiniteRepeatable(tween(1900), repeatMode = RepeatMode.Reverse),
        label = "idleBreathe",
    )
    val celebrating = avatarState == AvatarState.CELEBRATING || avatarState == AvatarState.LEVEL_UP
    val celebrateScale by animateFloatAsState(
        targetValue = if (celebrating) 1.05f else 1f,
        animationSpec = tween(240),
        label = "celebrateScale",
    )

    Box(
        modifier = modifier.testTag("sprite_stage"),
        contentAlignment = Alignment.BottomCenter,
    ) {
        Crossfade(
            targetState = avatarState,
            animationSpec = tween(260),
            label = "spriteBase",
        ) { target ->
            val layers = SpriteAssetRegistry.layersFor(state.appearance, target)
            Image(
                painter = painterResource(layers.baseResId),
                contentDescription = "2D 精灵 $target",
                contentScale = ContentScale.Fit,
                alignment = Alignment.BottomCenter,
                modifier = Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        translationY = breathe.dp.toPx()
                        scaleX = celebrateScale
                        scaleY = celebrateScale
                        transformOrigin = TransformOrigin(0.5f, 1f)
                    },
            )
        }
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6E2C8, widthDp = 360, heightDp = 360)
@Composable
private fun SpriteStageIdlePreview() {
    ShopGuideAgentTheme {
        SpriteStage(state = SpriteHomePreviewData.idle.toAvatarStageUiState())
    }
}

@Preview(showBackground = true, backgroundColor = 0xFFF6E2C8, widthDp = 360, heightDp = 360)
@Composable
private fun SpriteStagePresentingPreview() {
    ShopGuideAgentTheme {
        SpriteStage(state = SpriteHomePreviewData.presenting.toAvatarStageUiState())
    }
}
