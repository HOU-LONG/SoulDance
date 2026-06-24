package com.example.shopguideagent.ui.home

import androidx.annotation.DrawableRes
import com.example.shopguideagent.R

data class SpriteLayerResources(
    @DrawableRes val baseResId: Int,
    @DrawableRes val outfitResId: Int? = null,
    @DrawableRes val accessoryResId: Int? = null,
    @DrawableRes val propResId: Int? = null,
)

/**
 * 语义外观 + 人物状态 → 2D drawable 资源的唯一映射点（manifest/avatar_state_matrix.json 的代码实现）。
 *
 * 边界约定：
 * - UI state 只持有语义 id（outfitId 等），drawable 解析全部集中在这里，便于未来替换 3D。
 * - 房间道具（黑板/水晶球/购物袋）属于场景布景，由 [SpritePlacement] 在场景层按归一化坐标渲染，
 *   不经过本 registry 的 propResId，因此这里 propResId/outfitResId/accessoryResId 暂为 null。
 * - 缺失服装状态按 manifest 的 _fallback=DEFAULT 处理，不伪造或误用素材。
 */
object SpriteAssetRegistry {
    const val OUTFIT_DEFAULT = "default_outfit"
    const val OUTFIT_HOME_ADVISOR = "home_advisor"

    fun layersFor(appearance: AvatarAppearance, avatarState: AvatarState): SpriteLayerResources =
        SpriteLayerResources(
            baseResId = avatarDrawable(appearance.outfitId, avatarState),
            outfitResId = null,
            accessoryResId = null,
            propResId = null,
        )

    /**
     * 按状态矩阵解析人物本体 drawable。HOME_ADVISOR 仅 IDLE/PRESENTING 有专属素材，
     * 其余状态按 manifest 的 _fallback 回落到 DEFAULT 组。
     */
    @DrawableRes
    fun avatarDrawable(outfitId: String, state: AvatarState): Int {
        if (outfitId == OUTFIT_HOME_ADVISOR) {
            when (state) {
                AvatarState.IDLE, AvatarState.PRESENTING -> return R.drawable.avatar_presenting_home_advisor
                else -> Unit // fallback to DEFAULT below
            }
        }
        return defaultDrawable(state)
    }

    @DrawableRes
    private fun defaultDrawable(state: AvatarState): Int = when (state) {
        AvatarState.IDLE -> R.drawable.avatar_idle_default
        AvatarState.LISTENING -> R.drawable.avatar_listening_default
        AvatarState.THINKING -> R.drawable.avatar_thinking_default
        AvatarState.SEARCHING -> R.drawable.avatar_searching_default
        AvatarState.PRESENTING -> R.drawable.avatar_presenting_default
        AvatarState.CELEBRATING -> R.drawable.avatar_celebrating_default
        AvatarState.LEVEL_UP -> R.drawable.avatar_celebrating_default
        AvatarState.ERROR -> R.drawable.avatar_apologizing_default
    }
}
