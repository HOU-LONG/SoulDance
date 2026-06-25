package com.example.shopguideagent.ui.home

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.util.lerp
import com.example.shopguideagent.R
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme

/**
 * 全屏环境层：暖色房间背景（crop 铺满）+ 远景道具（左后黑板、左侧水晶球）。
 * 作为整页最底层，UI 浮层与中央舞台叠加其上。道具位于屏幕中上部，不被底部 UI 浮层遮挡。
 */
@Composable
fun SpriteRoomBackdrop(modifier: Modifier = Modifier) {
    BoxWithConstraints(modifier = modifier.testTag("sprite_room_backdrop")) {
        val w = maxWidth
        val h = maxHeight
        Image(
            painter = painterResource(R.drawable.sprite_room_background),
            contentDescription = "暖色房间背景",
            contentScale = ContentScale.Crop,
            modifier = Modifier.matchParentSize(),
        )
        PlacedAsset(
            resId = R.drawable.prop_smart_guide_blackboard,
            placement = SpritePlacement.Backdrop.Blackboard,
            containerWidth = w,
            containerHeight = h,
            contentDescription = "智能导购黑板",
        )
        PlacedAsset(
            resId = R.drawable.prop_discovery_globe,
            placement = SpritePlacement.Backdrop.DiscoveryGlobe,
            containerWidth = w,
            containerHeight = h,
            contentDescription = "好物发现水晶球",
        )
    }
}

/**
 * 中央舞台区：购物袋、人物本体、状态特效、气泡，全部相对本区（顶栏与底部 UI 之间的 weight 区）定位。
 *
 * 人物经 [avatarStage]（[AvatarStageRenderer]）以 `fillMaxSize` 渲染，内部 Fit + BottomCenter 保证
 * 全身完整、脚底落在本区底部，不被底部 UI 浮层遮挡。本区不依赖 2D/3D 具体实现。
 */
@Composable
fun SpriteStageArea(
    stageState: AvatarStageUiState,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { s, m -> SpriteStage(s, m) },
) {
    val avatarState = stageState.avatarState
    val searching = avatarState == AvatarState.SEARCHING
    val presenting = avatarState == AvatarState.PRESENTING
    val rewarding = avatarState == AvatarState.CELEBRATING || avatarState == AvatarState.LEVEL_UP

    val fx = rememberInfiniteTransition(label = "stageFx")
    val spin by fx.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(5200, easing = LinearEasing)),
        label = "spin",
    )
    val pulse by fx.animateFloat(
        initialValue = 0.84f,
        targetValue = 1.12f,
        animationSpec = infiniteRepeatable(tween(820, easing = LinearEasing), RepeatMode.Reverse),
        label = "pulse",
    )
    val swirlAlpha by fx.animateFloat(
        initialValue = 0.45f,
        targetValue = 0.85f,
        animationSpec = infiniteRepeatable(tween(1000, easing = LinearEasing), RepeatMode.Reverse),
        label = "swirlAlpha",
    )
    val twinkle by fx.animateFloat(
        initialValue = 0.55f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(720, easing = LinearEasing), RepeatMode.Reverse),
        label = "twinkle",
    )

    // 商品卡从购物袋飞向展示位的一次性进入动画（PRESENTING 触发）
    val flyProgress = remember { Animatable(0f) }
    LaunchedEffect(presenting) {
        if (presenting) {
            flyProgress.snapTo(0f)
            flyProgress.animateTo(1f, animationSpec = tween(560, easing = LinearEasing))
        } else {
            flyProgress.snapTo(0f)
        }
    }

    BoxWithConstraints(modifier = modifier.testTag("sprite_stage_area")) {
        val w = maxWidth
        val h = maxHeight

        // 购物袋（人物右侧）
        PlacedAsset(
            resId = R.drawable.prop_shopping_bag_blue,
            placement = SpritePlacement.Stage.ShoppingBag,
            containerWidth = w,
            containerHeight = h,
            contentDescription = "购物袋",
        )

        // 中央人物：fillMaxSize + 内部 Fit/BottomCenter → 全身完整、脚底稳定
        avatarStage(stageState, Modifier.fillMaxSize())

        // 搜索扫描环（顺时针）
        AnimatedVisibility(searching, Modifier.matchParentSize(), enter = fadeIn(), exit = fadeOut()) {
            Box(Modifier.fillMaxSize()) {
                PlacedAsset(
                    resId = R.drawable.effect_search_scan_ring_blue,
                    placement = SpritePlacement.Stage.SearchScanRing,
                    containerWidth = w,
                    containerHeight = h,
                    modifier = Modifier.graphicsLayer { rotationZ = spin },
                )
            }
        }
        // 金蓝轨道光环（逆时针）
        AnimatedVisibility(searching, Modifier.matchParentSize(), enter = fadeIn(), exit = fadeOut()) {
            Box(Modifier.fillMaxSize()) {
                PlacedAsset(
                    resId = R.drawable.effect_search_orbit_ring_gold_blue,
                    placement = SpritePlacement.Stage.SearchOrbitRing,
                    containerWidth = w,
                    containerHeight = h,
                    modifier = Modifier.graphicsLayer { rotationZ = -spin },
                )
            }
        }
        // 旋涡（搜索/展示前过渡）
        AnimatedVisibility(searching || presenting, Modifier.matchParentSize(), enter = fadeIn(), exit = fadeOut()) {
            Box(Modifier.fillMaxSize()) {
                PlacedAsset(
                    resId = R.drawable.effect_portal_swirl,
                    placement = SpritePlacement.Stage.PortalSwirl,
                    containerWidth = w,
                    containerHeight = h,
                    alpha = swirlAlpha,
                    modifier = Modifier.graphicsLayer { rotationZ = spin * 0.6f },
                )
            }
        }
        // 商品卡发光外框（PRESENTING）
        AnimatedVisibility(presenting, Modifier.matchParentSize(), enter = fadeIn(), exit = fadeOut()) {
            Box(Modifier.fillMaxSize()) {
                PlacedAsset(
                    resId = R.drawable.effect_product_card_frame,
                    placement = SpritePlacement.Stage.ProductCardFrame,
                    containerWidth = w,
                    containerHeight = h,
                )
            }
        }
        // 商品卡飞行拖尾（购物袋 → 展示位，一次性）
        if (presenting && flyProgress.value < 1f) {
            val p = flyProgress.value
            PlacedAsset(
                resId = R.drawable.effect_product_fly_trail,
                placement = NormalizedPlacement(
                    x = lerp(SpritePlacement.Stage.ProductFlyStart.x, SpritePlacement.Stage.ProductFlyEnd.x, p),
                    y = lerp(SpritePlacement.Stage.ProductFlyStart.y, SpritePlacement.Stage.ProductFlyEnd.y, p),
                    width = SpritePlacement.Stage.ProductFlyStart.width,
                    anchor = PlacementAnchor.CENTER,
                ),
                containerWidth = w,
                containerHeight = h,
                alpha = 1f - p * 0.35f,
            )
        }
        // 奖励星（庆祝/升级，缩放脉冲 + 闪烁）
        AnimatedVisibility(rewarding, Modifier.matchParentSize(), enter = fadeIn(), exit = fadeOut()) {
            Box(Modifier.fillMaxSize()) {
                PlacedAsset(
                    resId = R.drawable.effect_reward_star,
                    placement = SpritePlacement.Stage.RewardStar,
                    containerWidth = w,
                    containerHeight = h,
                    alpha = twinkle,
                    modifier = Modifier.graphicsLayer {
                        scaleX = pulse
                        scaleY = pulse
                    },
                )
            }
        }

        // 气泡：人物头顶上方，水平居中
        SpeechBubble(
            state = stageState.speechBubble,
            modifier = Modifier
                .align(Alignment.TopCenter)
                .offset(y = h * SpritePlacement.Stage.SpeechBubbleCenterY)
                .padding(horizontal = 24.dp),
        )
    }
}

@Preview(name = "Backdrop + Stage SEARCHING", showBackground = true, widthDp = 393, heightDp = 620)
@Composable
private fun SpriteStageAreaSearchingPreview() {
    ShopGuideAgentTheme {
        Box(Modifier.fillMaxSize()) {
            SpriteRoomBackdrop(Modifier.fillMaxSize())
            SpriteStageArea(
                stageState = SpriteHomePreviewData.searching.toAvatarStageUiState(),
                modifier = Modifier
                    .fillMaxWidth()
                    .fillMaxHeight(0.78f)
                    .align(Alignment.TopCenter),
            )
        }
    }
}

@Preview(name = "Backdrop + Stage PRESENTING", showBackground = true, widthDp = 393, heightDp = 620)
@Composable
private fun SpriteStageAreaPresentingPreview() {
    ShopGuideAgentTheme {
        Box(Modifier.fillMaxSize()) {
            SpriteRoomBackdrop(Modifier.fillMaxSize())
            SpriteStageArea(
                stageState = SpriteHomePreviewData.presenting.toAvatarStageUiState(),
                modifier = Modifier
                    .fillMaxWidth()
                    .fillMaxHeight(0.78f)
                    .align(Alignment.TopCenter),
            )
        }
    }
}
