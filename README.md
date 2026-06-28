# SoulDance · 灵舞 — AI 个性化动态导购精灵

SoulDance 是一个低压力 AI 购物导购体验的 monorepo 项目，包含原生 Android 客户端（Kotlin + Jetpack Compose）和 FastAPI 后端。后端拥有商品推荐、语义检索、多轮对话上下文管理、购物车状态、语音合成/识别、WebSocket 实时通信等完整能力。客户端只负责渲染，不实现任何推荐逻辑、不持有 LLM/TTS/STT 密钥。

---

## 仓库结构

```text
SoulDance/
  client/                  Android Kotlin + Jetpack Compose 应用
  server/                  FastAPI 后端、测试、脚本、依赖
  docs/                    架构、API、实时协议、运行手册、评测文档
  deploy/                  部署运行时说明与环境变量模板
  ecommerce_agent_dataset/ 共享商品数据集与图片资源
  data/                    运行时会话/购物车数据（git ignore）
  env/                     远程 Python/vLLM/conda 环境（git ignore）
  model/                   本地 embedding/模型资源（git ignore）
```

---

## 已实现核心能力

### 导购对话引擎
- **五场景 Demo 端到端**：护肤精华推荐 → 更便宜替代品追问 → 命名产品+模糊引用对比 → 跨域长会话锚点回溯 → 购物车添加/查看/SKU 切换，10 轮严格断言黄金回归测试全部通过
- **多轮上下文记忆架构**（2026-06 新增）：
  - 形态A：全量 `[{role, content}]` 对话流水持久化（`dialog_turns`），100 条消息滑动窗口
  - 形态B：结构化约束状态（`ConstraintState`）+ 产品参数缓存（`entity_params`）+ 长会话摘要压缩（`LivingSummary`，16 条消息阈值触发）
  - Prompt 注入：对话历史 + 约束短句实时注入 Response LLM 的 evidence payload
- **语义意图编译**：LLM + 规则双路径语义解析，置信度门控，上下文 fallback 重判
- **意图路由**：`recommend_product` / `product_followup` / `compare_products` / `cart_operation` / `scenario_bundle` / `clarification` / `small_talk` / `unclear_input` 八意图完整覆盖

### 检索与排序
- **RAG 混合检索**：BM25 关键词 + 向量语义检索，RRF / weighted 融合，CrossEncoder 重排（默认）+ LLM 重排（强场景兜底），失败静默降级
- **Mid-Price Primary 策略**：同 tier 候选价差 ≥2× 时，中价位产品自动提升为 primary，给 cheaper-alternative 追问留空间
- **Cache 体系**：B1 推荐记忆缓存（精确+语义匹配）+ B2 排序缓存，命中可跳过 LLM selection

### 商品对比
- **命名产品解析**：品牌+标题 n-gram 匹配 → `_product_mention_score` 分层评分（品牌 45/子类目 35/别名 160+/标题 160），带 sub_category 锚点过滤防止同品牌误匹配
- **模糊引用解析**："刚才那个便宜的" → `reference_anchors[last_cheaper_alternative]`
- **硬约束旁路**：用户显式命名的产品跳过历史轮次的 `hard_filter`约束

### 购物车
- **操作分离**：`view_cart`（只读）/ `add_to_cart` / `update_sku` / `update_quantity` / `remove` / `clear_cart` / `checkout`
- **SKU 切换**：自然语言 "换成 50ml 的" → 灵活属性匹配（`50ml in value`），未命中返回可选规格 clarification
- **双模式持久化**：SQLite（DB 路径）+ JSON 文件，带 `_sku_selections` 持久化与 clean/remove 清理

### 上下文与约束管理
- **软偏好提取**：肤质（干性/油皮/敏感肌）、季节（秋冬/春夏）、功效（保湿/修护）自动识别
- **域切换检测**：品类变更时自动清空软约束、重置推荐记忆，保留对话流水和摘要
- **长会话锚点**：首轮品牌/类目/product_ids 存储为 `reference_anchors`，"回到第一轮" 触发品牌硬约束绑定

### 语音交互
- STT 语音转文字（流式 WebSocket）+ TTS 文字转语音（分块流式），支持豆包语音引擎

### 行内商品锚点（Inline Product Anchor）
- **统一的文本内嵌商品入口**：AI 消息中的商品以 `[[商品名#product_id]]` 形式嵌入正文，替代独立商品卡片
- **点击展开详情**：所有锚点统一唤起 `ProductDetailBottomSheet`，覆盖推荐、对比、Bundle、追问四个流程
- **前后端协议对齐**：
  - 后端 Prompt 在主推/备选/对比/Bundle 文本中注入 `[[title#product_id]]`，并严格校验 `product_id` 来自 `allowed_products`
  - 非法或缺失锚点自动降级：去掉标记并记录 warning，避免前端解析失败
  - 历史上下文压缩时锚点自动折叠为 `[商品:product_id]`，节省 token 同时保留引用
- **实现计划**：`docs/superpowers/plans/2026-06-27-inline-product-anchor.md`

### 反馈闭环
- 显式反馈（评分/操作标签）+ 隐式信号聚合，驱动个性化排序与偏好画像

### 评测体系
- WebSocket 实时烟雾测试（`server/scripts/demo_ws_smoke.py`），10 轮 demo 逐轮断言、非零退出
- 长会话评测框架（`eval/`）：token 预算限制、压缩效果、退化检测

---

## Demo 后端

```text
HTTP API: https://missouri-traveling-seat-diverse.trycloudflare.com/
WebSocket: wss://missouri-traveling-seat-diverse.trycloudflare.com/ws/chat
```

Cloudflare tunnel 为临时端点。若 hostname 变更，更新 `client/.../AppConfig.kt` 并重新构建 APK。

---

## 构建与运行

### Android 客户端（Linux）

```bash
cd client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
chmod +x gradlew
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug
```

APK 输出：`client/app/build/outputs/apk/debug/app-debug.apk`

### 后端服务

```bash
bash server/scripts/setup_backend_env.sh
bash server/scripts/start_backend.sh
```

运行测试：

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
```

冒烟验证：

```bash
HOST=127.0.0.1 PORT=18083 USE_EMBEDDING=0 TTS_ENABLED=false STT_ENABLED=false \
  ARK_API_KEY= LLM_API_KEY= bash server/scripts/start_backend.sh
curl -fsS http://127.0.0.1:18083/health
```

---

## 核心 API

```text
GET  /health
GET  /api/products
GET  /api/products/{product_id}
GET  /api/cart
POST /api/cart/add
POST /api/cart/clear
POST /api/cart/checkout
POST /api/stt
WS   /ws/chat
```

WebSocket 事件类型：`text_delta`、`product_item`、`replacement_product`、`comparison_result`、`cart_update`、`quick_actions`、`audio_delta`、`done`、`error`。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| `docs/architecture.md` | 系统架构 |
| `docs/api-contract.md` | API 契约 |
| `docs/realtime-protocol.md` | 实时通信协议 |
| `docs/runbook.md` | 开发运行手册 |
| `docs/superpowers/specs/` | 设计规格（demo agent flow、context memory architecture 等） |
| `docs/superpowers/plans/` | 实施计划 |
| `deploy/README.md` | 部署说明 |
| `client/AGENTS.md` | 客户端开发指引 |
