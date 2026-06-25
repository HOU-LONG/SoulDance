# 精灵空间页实施提示词

请把本素材包放在 Android 项目根目录附近，并先阅读 `AGENTS.md`。

## 一、素材来源

Android 可直接使用的图片位于：

`android/app/src/main/res/drawable-nodpi/`

素材语义和状态映射位于：

- `manifest/asset_manifest.json`
- `manifest/avatar_state_matrix.json`

布局区域和建议位置位于：

- `layout/sprite_space_layout.json`

不得忽略这些文件自行猜测。

## 二、第一轮开发目标

实现 `SpriteSpaceRoute`、`SpriteSpaceScreen` 和独立 `AvatarStage`。

页面包括：

1. 房间背景；
2. 左上用户信息卡；
3. 右上菜单和关闭按钮；
4. Compose 对话气泡；
5. 左后方黑板；
6. 左侧好物发现水晶球；
7. 中央状态人物；
8. 右侧蓝色购物袋；
9. 精灵名称、等级和亲密度；
10. 装扮、成长、导购三个底部入口；
11. 每日任务卡。

第一轮不要求完整商品卡片和后端接入，但状态切换必须能通过 Preview 或假数据验证。

## 三、状态资源

严格按照 `avatar_state_matrix.json`：

- IDLE → avatar_idle_default
- LISTENING → avatar_listening_default
- THINKING → avatar_thinking_default
- SEARCHING → avatar_searching_default
- PRESENTING → avatar_presenting_default
- CELEBRATING / LEVEL_UP → avatar_celebrating_default
- ERROR → avatar_apologizing_default

SEARCHING 时叠加：

- effect_search_scan_ring_blue
- effect_search_orbit_ring_gold_blue
- 可选 effect_portal_swirl

PRESENTING 时允许叠加：

- effect_product_card_frame
- effect_product_fly_trail

## 四、布局

把 `sprite_space_layout.json` 的坐标理解为设计建议，而不是 Android 固定像素。

必须用：

- BoxWithConstraints
- Alignment
- weight
- padding
- WindowInsets
- 相对宽度

特殊素材偏移集中放入 `SpriteSpaceAssetPlacement`，不得散落 Magic Number。

## 五、Compose 动态组件

下列内容不能使用图片：

- 用户名、火焰值和身份；
- 对话气泡文字；
- 精灵名称；
- 等级和亲密度进度；
- 底部按钮背景和文字；
- 每日任务；
- 商品名称、价格、推荐理由；
- 购物车数量。

## 六、项目审计

修改代码前先搜索：

- RealtimeEvent
- ProductUiModel
- CartViewModel
- ChatViewModel
- NavHost
- StateFlow
- Room / DataStore
- SSE / WebSocket

已有实现必须复用。

## 七、第一次汇报格式

先输出：

1. 项目技术栈；
2. 素材完整性验证；
3. 实际资源名映射；
4. 准备新增和修改的文件；
5. 导航接入点；
6. 编译命令；
7. 缺失素材处理方案。

完成第一轮后输出：

1. 修改文件清单；
2. 状态流转；
3. 三个 Preview 截图或说明；
4. 编译结果；
5. 下一轮后端接入计划。
