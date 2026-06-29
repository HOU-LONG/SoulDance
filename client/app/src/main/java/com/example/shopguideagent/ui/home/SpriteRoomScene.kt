package com.example.shopguideagent.ui.home

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
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
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.R
import com.example.shopguideagent.data.model.ProductUiModel
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
 * 中央舞台区：人物本体、手掌商品与气泡，全部相对本区（顶栏与底部 UI 之间的 weight 区）定位。
 *
 * 人物经 [avatarStage]（[AvatarStageRenderer]）以 `fillMaxSize` 渲染，再整体左下偏移，为手掌商品展示
 * 留出空间。本区不依赖 2D/3D 具体实现。
 */
@Composable
fun SpriteStageArea(
    stageState: AvatarStageUiState,
    modifier: Modifier = Modifier,
    avatarStage: AvatarStageRenderer = { s, m -> SpriteStage(s, m) },
    palmProduct: ProductUiModel? = null,
    palmProductLoading: Boolean = false,
    palmProductExpanded: Boolean = false,
    onPalmProductClick: (ProductUiModel) -> Unit = {},
    onPalmProductDismiss: () -> Unit = {},
    onAddToCart: (ProductUiModel) -> Unit = {},
    onRefineProduct: (String) -> Unit = {},
) {
    BoxWithConstraints(modifier = modifier.testTag("sprite_stage_area")) {
        val w = maxWidth
        val h = maxHeight

        // 中央人物：保留 fillMaxSize + 内部 Fit/BottomCenter，再整体左下偏移。
        avatarStage(
            stageState,
            Modifier
                .fillMaxSize()
                .offset(
                    x = w * SpritePlacement.Stage.AvatarOffsetX,
                    y = h * SpritePlacement.Stage.AvatarOffsetY,
                ),
        )

        PalmProductThumbnail(
            product = palmProduct,
            loading = palmProductLoading,
            onClick = { palmProduct?.let(onPalmProductClick) },
            modifier = Modifier.placedInStage(
                placement = SpritePlacement.Stage.PalmProduct,
                containerWidth = w,
                containerHeight = h,
                fallbackAspect = 1f,
            ),
        )

        AnimatedVisibility(
            visible = palmProductExpanded && palmProduct != null,
            modifier = Modifier.placedInStage(
                placement = SpritePlacement.Stage.PalmProductPanel,
                containerWidth = w,
                containerHeight = h,
                fallbackAspect = 1.72f,
            ),
            enter = scaleIn(initialScale = 0.92f) + fadeIn(),
            exit = fadeOut(),
        ) {
            palmProduct?.let { product ->
                PalmProductMiniPanel(
                    product = product,
                    onAddToCart = onAddToCart,
                    onRefine = onRefineProduct,
                    onDismiss = onPalmProductDismiss,
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

private fun Modifier.placedInStage(
    placement: NormalizedPlacement,
    containerWidth: Dp,
    containerHeight: Dp,
    fallbackAspect: Float,
): Modifier {
    val widthDp = containerWidth * placement.width
    val heightDp = widthDp / fallbackAspect
    val anchorX = containerWidth * placement.x
    val anchorY = containerHeight * placement.y
    val offsetX: Dp
    val offsetY: Dp
    when (placement.anchor) {
        PlacementAnchor.TOP_START -> {
            offsetX = anchorX
            offsetY = anchorY
        }
        PlacementAnchor.CENTER -> {
            offsetX = anchorX - widthDp / 2
            offsetY = anchorY - heightDp / 2
        }
        PlacementAnchor.BOTTOM_CENTER -> {
            offsetX = anchorX - widthDp / 2
            offsetY = anchorY - heightDp
        }
    }
    return offset(x = offsetX, y = offsetY)
}

@Preview(name = "Backdrop + Stage SEARCHING", showBackground = true, widthDp = 393, heightDp = 620)
@Composable
private fun SpriteStageAreaSearchingPreview() {
    ShopGuideAgentTheme {
        Box(Modifier.fillMaxSize()) {
            SpriteRoomBackdrop(modifier = Modifier.fillMaxSize())
            SpriteStageArea(
                stageState = SpriteHomePreviewData.searching.toAvatarStageUiState(),
                palmProductLoading = true,
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
            SpriteRoomBackdrop(modifier = Modifier.fillMaxSize())
            SpriteStageArea(
                stageState = SpriteHomePreviewData.presenting.toAvatarStageUiState(),
                palmProduct = SpriteHomePreviewData.presenting.productPresentation.primaryProduct,
                palmProductExpanded = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .fillMaxHeight(0.78f)
                    .align(Alignment.TopCenter),
            )
        }
    }
}
