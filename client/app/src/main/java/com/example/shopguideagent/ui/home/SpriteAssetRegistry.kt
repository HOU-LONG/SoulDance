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

    fun layersFor(appearance: AvatarAppearance, avatarState: AvatarState): SpriteLayerResources {
        val isHomeAdvisor = appearance.outfitId == OUTFIT_HOME_ADVISOR
        return SpriteLayerResources(
            baseResId = avatarDrawable(appearance.outfitId, avatarState),
            // Task 4: 当 HOME_ADVISOR 被选中时，标记 outfitResId 为非 null，
            // 供未来分离式分层渲染（base + outfit overlay）使用。
            // 当前由于所有素材都是全图（非分层），仅设置标记，不影响实际渲染。
            outfitResId = if (isHomeAdvisor) R.drawable.avatar_presenting_home_advisor else null,
            accessoryResId = null,
            propResId = null,
        )
    }

    /**
     * 按状态矩阵解析人物本体 drawable。
     *
     * 资产现状（Task 4 注释）：
     * - OUTFIT_DEFAULT: 7 个状态全覆盖（IDLE/LISTENING/THINKING/SEARCHING/PRESENTING/CELEBRATING/ERROR）
     * - OUTFIT_HOME_ADVISOR: 只有 1 个独立素材（avatar_presenting_home_advisor），
     *   对 IDLE 和 PRESENTING 使用该素材，其余状态使用同一素材作为 fallback，
     *   确保用户选择 HOME_ADVISOR 后始终看到不同的外观（而非静默回退到 DEFAULT）。
     * - 如需新增服装状态素材，在此扩展 state → drawable 映射即可。
     */
    @DrawableRes
    fun avatarDrawable(outfitId: String, state: AvatarState): Int {
        if (outfitId == OUTFIT_HOME_ADVISOR) {
            return R.drawable.avatar_presenting_home_advisor
        }
        return defaultDrawable(state)
    }

    /** Task 5: 根据背景 ID 返回对应 drawable，支持未来多背景切换。 */
    @DrawableRes
    fun backgroundDrawable(backgroundId: String): Int = when (backgroundId) {
        "warm_room" -> R.drawable.sprite_room_background
        else -> R.drawable.sprite_room_background  // 未知背景统一 fallback
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
