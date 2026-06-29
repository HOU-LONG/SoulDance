package com.example.shopguideagent.ui.home

import androidx.annotation.DrawableRes
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp

/** 素材在容器内的归一化锚点类型。 */
enum class PlacementAnchor { TOP_START, CENTER, BOTTOM_CENTER }

/**
 * 单个素材的归一化放置规格。
 *
 * 坐标系参考 layout/sprite_space_layout.json 的 `normalized_screen`（0.0..1.0，参考尺寸 941×1672）。
 * [x]/[y] 为锚点位置（相对容器宽高的比例），[width] 为相对容器宽度的归一化宽度，
 * 高度由素材固有宽高比决定，避免拉伸。
 */
data class NormalizedPlacement(
    val x: Float,
    val y: Float,
    val width: Float,
    val anchor: PlacementAnchor,
)

/**
 * 集中式 placement 配置：精灵空间所有美术素材的坐标唯一来源，不在各 Composable 中散落 Magic Number。
 *
 * 分两组坐标系：
 * - [Backdrop]：相对**全屏**，承载背景与远景环境道具（黑板、水晶球）。
 * - [Stage]：相对**中央舞台区**（顶栏与底部 UI 之间的 weight 区），承载购物袋、特效、气泡。
 *   人物本体不在此列——它由舞台区 `fillMaxSize` + `Fit` + `BottomCenter` 渲染，数学上保证全身完整、
 *   脚底稳定，不被底部 UI 浮层遮挡。
 */
object SpritePlacement {
    /** 全屏环境层坐标（对应 layout 的 room_background / wall_blackboard）。 */
    object Backdrop {
        // 木质黑板：挂在后墙左侧
        val Blackboard = NormalizedPlacement(0.05f, 0.18f, 0.24f, PlacementAnchor.TOP_START)
    }

    /** 中央舞台区相对坐标（0..1 相对舞台 Box）。 */
    object Stage {
        // 人物本体：整体向左下方移动，为手掌商品展示留出视觉空间。
        const val AvatarOffsetX = -0.08f
        const val AvatarOffsetY = 0.04f
        // 商品缩略图：落在人物右侧手掌附近。
        val PalmProduct = NormalizedPlacement(0.64f, 0.55f, 0.17f, PlacementAnchor.CENTER)
        // 轻量浮层：从手掌商品右上侧展开，避免遮挡底部输入区。
        val PalmProductPanel = NormalizedPlacement(0.69f, 0.35f, 0.56f, PlacementAnchor.CENTER)
        // 气泡中心：人物头顶上方，上移避免遮挡头部
        const val SpeechBubbleCenterY = 0.02f
    }
}

/**
 * 按 [NormalizedPlacement] 把一张素材放置到给定容器尺寸（[containerWidth]×[containerHeight]）内。
 * 宽度 = 容器宽 × placement.width，高度按素材固有比例换算，再依锚点平移到目标位置。
 */
@Composable
fun PlacedAsset(
    @DrawableRes resId: Int,
    placement: NormalizedPlacement,
    containerWidth: Dp,
    containerHeight: Dp,
    modifier: Modifier = Modifier,
    contentDescription: String? = null,
    contentScale: ContentScale = ContentScale.Fit,
    alpha: Float = 1f,
) {
    val painter = painterResource(resId)
    val widthDp = containerWidth * placement.width
    val intrinsic = painter.intrinsicSize
    val aspect = if (intrinsic.width > 0f && intrinsic.height > 0f) intrinsic.width / intrinsic.height else 1f
    val heightDp = widthDp / aspect

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

    Image(
        painter = painter,
        contentDescription = contentDescription,
        contentScale = contentScale,
        alpha = alpha,
        modifier = modifier
            .offset(x = offsetX, y = offsetY)
            .width(widthDp)
            .height(heightDp),
    )
}
