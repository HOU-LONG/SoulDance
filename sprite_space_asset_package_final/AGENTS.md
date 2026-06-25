# AGENTS.md

## 精灵空间开发强制规则

在修改代码前，必须完整阅读：

- `manifest/asset_manifest.json`
- `manifest/avatar_state_matrix.json`
- `layout/sprite_space_layout.json`
- `manifest/missing_assets.json`
- `SPRITE_SPACE_IMPLEMENTATION_PROMPT.md`

## 禁止事项

1. 禁止把 `reference/design_reference.png` 作为整页背景。
2. 禁止根据图片外观自行猜用途。
3. 禁止使用未在 `asset_manifest.json` 中登记的图片。
4. 禁止把文字、等级、亲密度、商品信息烘焙进图片。
5. 禁止大量使用基于 941×1672 的固定像素坐标。
6. 禁止重复创建已有的网络层、RealtimeEvent、商品模型和购物车系统。
7. 缺失素材必须按 `missing_assets.json` 处理，不得自行找相似图片替代。

## 第一轮目标

- 合并 `drawable-nodpi` 资源；
- 用 Compose 重建静态精灵空间；
- 接假 `SpriteSpaceUiState`；
- 实现人物状态切换；
- 实现三种屏幕宽度 Preview；
- 编译通过；
- 暂不连接完整后端。

## 2D/3D 边界

中央人物必须通过独立 `AvatarStage` 渲染。页面其余组件不能依赖人物是
PNG、Live2D 还是 3D 模型。
