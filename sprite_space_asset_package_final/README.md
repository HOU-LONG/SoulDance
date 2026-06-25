# 精灵空间最终素材工程包

本包根据上传的 `UI.zip` 逐张审查、归类和标准化生成，可直接交给
Codex、Claude Code、Cursor Agent 等 Coding Agent。

## Coding Agent 必读顺序

1. `AGENTS.md`
2. `manifest/asset_manifest.json`
3. `manifest/avatar_state_matrix.json`
4. `layout/sprite_space_layout.json`
5. `manifest/missing_assets.json`
6. `SPRITE_SPACE_IMPLEMENTATION_PROMPT.md`

## 最重要的事实

- 设计参考图是 `reference/design_reference.png`，只能用于比对。
- 实际背景是 `sprite_room_background.png`。
- 默认可用人物状态组是米色长裙版本。
- 参考图里的黑色半身裙人物没有出现在上传素材中。
- `IDLE` 已使用用户补充的真正中性待机素材。
- 部分原始图片没有真实透明背景，本包已经进行技术性 Alpha 清理。
- 默认人物状态图已经统一成 1200×1600 画布和脚底锚点。
- 所有动态文字、按钮、进度条和商品卡片必须由 Compose 绘制。

## Android 资源

可以将以下目录内容合并到项目：

`android/app/src/main/res/drawable-nodpi/`

不要覆盖项目中同名但用途不同的资源；先对照 manifest。

## 预览

- `reference/standardized_asset_contact_sheet.png`
- `reference/scene_asset_composite_preview.png`

场景合成预览只验证素材方向，不代表最终 Compose UI。
