package com.example.shopguideagent.ui.home

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.R
import com.example.shopguideagent.ui.theme.ShopGuideAgentTheme

/**
 * 全屏环境层：暖色房间背景（crop 铺满）+ 墙上黑板（远景装饰）。
 * 作为整页最底层，UI 浮层与中央舞台叠加其上。
 */
@Composable
fun SpriteRoomBackdrop(
    backgroundId: String = "warm_room",
    modifier: Modifier = Modifier,
) {
    BoxWithConstraints(modifier = modifier.testTag("sprite_room_backdrop")) {
        val w = maxWidth
        val h = maxHeight
        Image(
            painter = painterResource(SpriteAssetRegistry.backgroundDrawable(backgroundId)),
            contentDescription = "暖色房间背景",
            contentScale = ContentScale.Crop,
            modifier = Modifier.matchParentSize(),
        )
        PlacedAsset(
            resId = R.drawable.prop_smart_guide_blackboard,
            placement = SpritePlacement.Backdrop.Blackboard,
            containerWidth = w,
            containerHeight = h,
            contentDescription = "墙上黑板",
        )
    }
}

/**
 * 中央舞台区：水晶球、购物袋、人物本体、气泡，全部相对本区（顶栏与底部 UI 之间的 weight 区）定位。
 *
 * 人物经 [avatarStage]（[AvatarStageRenderer]）以 `fillMaxSize` 渲染，内部 Fit + BottomCenter 保证
 * 全身完整、脚底落在本区底部，不被底部 UI 浮层遮挡。水晶球与购物袋同样以 BOTTOM_CENTER 锚点与本区
 * 底部对齐，形成统一的"地面"基准线。本区不依赖 2D/3D 具体实现。
 */
@Composable
fun SpriteStageArea(
    stageState: AvatarStageUiState,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { s, m -> SpriteStage(s, m) },
) {
    BoxWithConstraints(modifier = modifier.testTag("sprite_stage_area")) {
        val w = maxWidth
        val h = maxHeight

        // 水晶球（舞台左下角，底部着地）
        PlacedAsset(
            resId = R.drawable.prop_discovery_globe,
            placement = SpritePlacement.Stage.DiscoveryGlobe,
            containerWidth = w,
            containerHeight = h,
            contentDescription = "好物发现水晶球",
        )

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
