# SoulDance · 灵舞 — AI 个性化动态导购精灵

SoulDance 是 **LLM Agent 驱动的智能导购助手**——聊天式的购物体验，自然语言→商品推荐→加购一条龙。与关键词搜索+筛选式电商不同，SoulDance 把"购物决策"变成了"对话体验"。

## 产品亮点

1. **精灵养成空间**：2D 虚拟精灵"灵舞"作为导购伴侣，姿态随对话实时变化（思考/搜索/推荐/庆祝），等级成长 + 火星积分 + 换装系统，让 AI 购物有温度
2. **先共情再推荐**：识别"心情不好推荐甜的"类复合需求，LLM 先安抚情绪再自然带出真实商品卡片
3. **对话即决策**：推荐→内联卡片→详情浮层→加购，全程不离开聊天界面，零页面跳转

---

SoulDance 是一个低压力 AI 购物导购体验的 monorepo 项目，包含原生 Android 客户端（Kotlin + Jetpack Compose）和 FastAPI 后端。

---

## 仓库结构

```text
SoulDance/
  client/                  Android Kotlin + Jetpack Compose 应用
    scripts/               编译辅助脚本（tunnel 自动检查等）
  server/                  FastAPI 后端、测试、脚本、依赖
    backend/app/           后端主包，按职责划分为多个子目录
      core/                核心编排（ShopGuideAgent）
      planning/            规划与状态（ToolPlanner、UnifiedPlan、StateReducer）
      pipeline/            事实锚定管道（FactContext、AnchorValidator、ConsistencyTracker）
      retrieval/           检索编排（AdaptiveRetriever、ProductMatcher、Ranker）
      rag/                 RAG 检索与排序（BM25、Dense、RRF、Reranker）
      tools/               8 个 Tool 实现
      services/            业务服务（Cart、Order、SessionStore、LLM Client）
      repositories/        数据访问层（Cart/Order/Session/Feedback/Profile）
      db/                  SQLAlchemy 模型、引擎与迁移
      memory/              上下文压缩与推荐记忆缓存
      feedback/            反馈闭环
      comparison/          商品对比引擎
      adapters/            STT/TTS/图片资源适配器
      eval/                长会话评测与检索消融
      prompts/v1/          LLM 系统提示模板
  docs/                    架构、API、实时协议、运行手册、评测文档、更新日志
  deploy/                  部署运行时说明与环境变量模板
  ecommerce_agent_dataset/ 共享商品数据集与图片资源
  data/                    运行时会话/购物车数据（git ignore）
  env/                     远程 Python/vLLM/conda 环境（git ignore）
  model/                   本地 embedding/模型资源（git ignore）
```

---

## 最近更新

### v2.1 — 代码清理、目录重组与运行稳定性（2026-06-30）

v2.1 在 v2.0 重构落定后，彻底清理过渡期兼容层，并将后端代码按职责重组为多个子目录，同时增强了运行稳定性：

- **删除 ToolPlan 旧模块** — `server/backend/app/tool_plan.py`（ToolPlan/ToolPlanArgs）已随 UnifiedPlan 统一决策完成使命，彻底移除
- **删除 IntentCompiler 残留** — `server/backend/app/intent_compiler.py` 及 `SemanticParser`、`PlannerAgent` 类正式移除
- **清理 LLM 客户端废弃方法** — `services/llm_client.py` 中的 `parse_semantic_frame()`、`classify_contextual_followup()` 移除
- **删除 UnifiedPlan 向后兼容属性** — `.intent`、`.constraint_edits`、`.cart_operation`、`.query_intent` 等兼容层属性移除
- **删除类型别名与 workaround** — `SemanticFrame` / `ShoppingIntentIR` 别名及 `_merge_tool_plan_into_ir()` 移除
- **目录重组** — `server/backend/app/` 从平铺文件重构为 `core/`、`planning/`、`pipeline/`、`retrieval/`、`rag/`、`tools/`、`services/`、`repositories/`、`db/` 等职责清晰的子目录
- **阶段超时** — `services/timeout_policy.py` 为 plan/retrieve/generate/tool 各阶段设置独立超时
- **LLM 信号量** — `services/concurrency.py` 限制并发 LLM 调用，提升突发流量下的稳定性
- **工具错误分类** — 工具异常按阶段分类，降级提示更精确
- **净删除约 1350 行死代码** — 涉及 14 个文件，架构更清晰，无冗余兼容层

当前核心链路：**LLM 2 次/轮**（ToolPlanner → Generate），配合 **pipeline/FactContextBuilder + pipeline/AnchorValidator（流式校验）+ pipeline/ConsistencyTracker（跨轮一致性）** 构成防幻觉三层防护。

### v2.0 — 事实锚定管道（2026-06）

v2.0 以**可靠性**和**效率**为核心进行了架构升级：

- **事实锚定管道 (Fact-Grounded Pipeline)** — LLM 只能引用数据库真实商品，虚构的 product_id 在流式输出中被实时拦截替换，跨轮自动检测 focus drift 并防谎
- **UnifiedPlan 统一决策** — 合并 ToolPlan + SemanticFrame + RetrievalPlan，LLM 调用从每轮 3 次减少到 2 次，删除 IntentCompiler LLM 解析路径
- **3 阶段会话 Checkpoint** — turn_start / post_retrieve / turn_end 自动保存，服务中断恢复时不丢上下文
- **上下文感知降级** — LLM 超时 / 检索异常 / 幻觉拦截时，fallback 提示包含用户最后查询词和关注商品
- **CJK-ASCII 分词归一化** — jieba 分词前自动在中文与英文/数字之间插入空格，修复"小米17Max"无法匹配数据库"小米 17 Max"的问题
- **商品分析增强** — 匹配到的商品事实直接注入 LLM prompt，消除 BM25 正确匹配却输出"商品未找到"的假阴性

---

## 核心能力

### 事实锚定管道 (Fact-Grounded Pipeline)

端到端保证 LLM 引用真实商品，杜绝虚构：

- **FactContextBuilder** (`pipeline/fact_context.py`) — 从当前轮商品 + 跨轮缓存构建 `[[product_id]]` 锚点事实表，注入 LLM 提示词
- **AnchorValidator** (`pipeline/anchor_validator.py`) — 流式循环状态机逐 chunk 校验 LLM 输出中的 `[[...]]` 锚点：普通文本零延迟直通，`[[` 触发微缓冲 → 闭合校验 → 有效性比对 → 无效锚点实时替换
- **ConsistencyTracker** (`pipeline/consistency_tracker.py`) — 跨轮 denial cache（已否认属性不再重复推荐）+ focus drift 检测（类别漂移自动提醒）
- **HallucinationChecker** (`pipeline/hallucination_checker.py`) — 后置审计：价格偏差检测

### 导购对话引擎

- **UnifiedPlan 统一决策**：合并 ToolPlan（工具选择）+ SemanticFrame（语义槽位）+ RetrievalPlan（检索策略）为一次 LLM 调用，LLM 调用从 3 次减少到 2 次，IntentCompiler 已删除
- **ToolPlanner — LLM 优先工具调度**：替代旧的多层规则栈（`planning/tool_planner.py`），LLM 直接决定调哪个 tool + 抽取参数
- **ProductMatcher — BM25 模糊商品识别**：用户简称"华为 Pura 70 Pro" / "小棕瓶" / "雀巢咖啡" 自动匹配库内长标题商品（`retrieval/product_matcher.py`）
- **CJK-ASCII 分词归一化**：`retrieval/embedding_retriever.py` 在 jieba 分词前自动在中文与英文/数字之间插入空格，修复"小米17Max"无法匹配数据库"小米 17 Max"的问题
- **自然回复风格**：去掉五段标签模板（理解/结论/主推/评论摘要/下一步），LLM 生成自然短段落回复
- **复合需求处理**："心情不好推荐甜的" → LLM 先共情 "抱抱你～吃点甜的确实治愈"，再自然带出商品推荐 + 真实锚点
- **Chitchat 内嵌商品推荐**：闲聊流自动注入库内 top-5 相关商品摘要，LLM 可用 `[[商品名#product_id]]` 锚点直接在对话中推荐真实库存商品
- **商品分析增强**：`tools/product_analysis.py` 将匹配到的商品事实直接注入 LLM prompt，消除 BM25 正确匹配却输出"商品未找到"的假阴性

### 意图路由（8 tool）

`recommend_product` / `product_analysis` / `compare_products` / `cart_operation` / `scenario_bundle` / `product_followup` / `chitchat` / `clarification`

### 多轮对话与上下文

- **多轮上下文记忆架构**：`dialog_turns` 对话流水（100 条滑动窗口）+ `ConstraintState` 结构化约束 + `LivingSummary` 摘要压缩（16 条触发）
- **3 阶段会话 Checkpoint**：Turn Start → Post-Retrieve → Turn End 自动保存，服务异常恢复时不丢上下文和缓存
- **上下文感知降级**：LLM 超时 / 检索错误 / LLM 错误 / 幻觉拦截 / 矛盾拦截 / 内部错误 6 种场景，fallback 提示包含用户最后查询词和关注商品
- **会话历史与用户切换**：`SessionContext.display_messages` 统一记录；REST API 按 `X-User-Id` 隔离；Android 本地最多保留 30 个会话
- **长会话锚点**：首轮品牌/类目/product_ids 存储为 `reference_anchors`，"回到第一轮" 触发品牌硬约束绑定

### 检索与排序

- **RAG 混合检索**：`rag/lexical_search.py` BM25 关键词 + `rag/vector_search.py` 向量语义检索，`rag/fusion.py` RRF/weighted 融合，`rag/reranker.py` CrossEncoder 重排（默认）+ LLM 重排（强场景兜底），失败静默降级
- **检索编排**：`retrieval/adaptive_retriever.py` 渐进放松检索，`retrieval/ranker.py` 硬约束过滤 + 多因素排序
- **Mid-Price Primary 策略**：同 tier 候选价差 ≥2× 时，中价位产品自动提升为 primary，给 cheaper-alternative 追问留空间
- **Cache 体系**：`memory/memory_cache.py` B1 推荐记忆缓存（精确+语义匹配）+ B2 排序缓存，命中可跳过 LLM selection

### 商品对比

- **命名产品解析**：品牌+标题 n-gram 匹配 → `_product_mention_score` 分层评分（品牌 45/子类目 35/别名 160+/标题 160），带 sub_category 锚点过滤防止同品牌误匹配
- **模糊引用解析**："刚才那个便宜的" → `reference_anchors[last_cheaper_alternative]`
- **硬约束旁路**：用户显式命名的产品跳过历史轮次的 `hard_filter` 约束
- **对比引擎**：`comparison/comparison_engine.py` LLM 多维度打分 + `comparison/comparison_presenter.py` 格式化输出

### 购物车

- **操作分离**：`view_cart`（只读）/ `add_to_cart` / `update_sku` / `update_quantity` / `remove` / `clear_cart` / `checkout`
- **SKU 切换**：自然语言 "换成 50ml 的" → 灵活属性匹配（`50ml in value`），未命中返回可选规格 clarification
- **双模式持久化**：`repositories/cart_repository.py` + `db/models.py` SQLite 持久化，带 `_sku_selections` 持久化与 clean/remove 清理
- **订单状态机**：`services/order_service.py` 支持 `address_required → awaiting_confirmation → completed` 三态流转

### 上下文与约束管理

- **软偏好提取**：肤质（干性/油皮/敏感肌）、季节（秋冬/春夏）、功效（保湿/修护）自动识别
- **域切换检测**：品类变更时自动清空软约束、重置推荐记忆，保留对话流水和摘要

### 语音交互

- `adapters/stt_adapter.py` 语音转文字（流式 WebSocket）+ `adapters/tts_adapter.py` 文字转语音（分块流式），支持豆包语音引擎

### 内联商品卡片（Inline Product Card）

- **段落-卡片交替布局**：AI 消息按 `\n\n` 切段渲染，含锚点的段落后自动插入内联商品卡片（左缩略图 + 右名称/价格/品牌）
- **主推/备选分层**：主推商品内联卡片嵌入气泡内，备选商品横向缩略图展示在气泡下方
- **chitchat 也支持商品卡片**：复合需求场景下，LLM 在闲聊回复中用 `[[商品名#product_id]]` 提及商品，后端自动扫描并下发 `product_item` 事件→前端渲染卡片
- **点击展开详情**：所有锚点/卡片统一唤起 `ProductDetailBottomSheet`

### 反馈闭环

- `feedback/feedback_store.py` 显式反馈（评分/操作标签）+ `feedback/feedback_aggregator.py` 隐式信号聚合，`feedback/feedback_ranker.py` 驱动个性化排序与偏好画像

### 评测体系

- WebSocket 实时烟雾测试（`server/scripts/demo_ws_smoke.py`），10 轮 demo 逐轮断言、非零退出
- 长会话评测框架（`eval/`）：token 预算限制、压缩效果、退化检测

---

## Demo 后端

```text
HTTP API: https://legs-committed-orange-tears.trycloudflare.com/
WebSocket: wss://legs-committed-orange-tears.trycloudflare.com/ws/chat
```

Cloudflare tunnel 为临时端点。编译 APK 时 Gradle 会自动检查 tunnel 可用性，若 hostname 变更则自动更新 `AppConfig.kt` 并重新编译。也可手动跳过检查：

```bash
SKIP_TUNNEL_CHECK=true ./gradlew :app:assembleDebug
```

---

## 构建与运行

### 前置条件

- JDK 17+、Android SDK、Kotlin / Jetpack Compose 工具链
- Python 3.12+、FastAPI 后端虚拟环境

### Android 客户端（Linux）

```bash
cd client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
chmod +x gradlew

# 单元测试
./gradlew :app:testDebugUnitTest

# 编译 APK（自动检查 tunnel + 自动更新 AppConfig URL）
./gradlew :app:assembleDebug
```

**版本号自动递增**：`versionCode` / `versionName` 基于 `git rev-list --count HEAD` 自动生成，每次新 commit 编译时自动 +1，无需手动维护。

**编译前自动检查**：Gradle 会在 `preBuild` 之前执行 `client/scripts/ensure_tunnel.sh`，自动确认后端服务和 Cloudflare tunnel 可用。若 tunnel URL 变更则自动更新 `AppConfig.kt`。整个过程在服务已运行时耗时 < 1s，不影响日常编译体验。

跳过 tunnel 检查（离线开发等场景）：

```bash
SKIP_TUNNEL_CHECK=true ./gradlew :app:assembleDebug
```

APK 输出：`client/app/build/outputs/apk/debug/app-debug.apk`

### 后端服务

首次搭建环境：

```bash
bash server/scripts/setup_backend_env.sh
```

启动后端（默认端口 8000）：

```bash
bash server/scripts/start_backend.sh
```

配置 LLM Provider：编辑仓库根目录 `.env`，设置 `LLM_PROVIDER`：

```bash
# 使用 DeepSeek（当前默认）
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
LLM_REASONING_EFFORT=high

# 或使用豆包
#LLM_PROVIDER=doubao
#ARK_API_KEY=ark-xxx
#ARK_MODEL=ep-xxx
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

### 暴露公网（Cloudflare Tunnel）

```bash
cloudflared tunnel --url http://127.0.0.1:8000 &
# URL 将打印在终端输出中
```

编译 APK 前运行 `client/scripts/ensure_tunnel.sh` 可自动完成上述全流程：检查后端 → 启动 tunnel → 更新 AppConfig。

---

## 核心 API

```text
GET  /health
GET  /api/products
GET  /api/products/{product_id}
GET  /api/sessions
GET  /api/sessions/latest
GET  /api/sessions/{session_id}
DELETE /api/sessions/{session_id}
GET  /api/cart
POST /api/cart/add
POST /api/cart/clear
POST /api/cart/checkout
POST /api/order/*            # 订单状态机（v2.1 稳定化）
POST /api/stt
WS   /ws/chat
```

WebSocket 事件类型：`text_delta`、`product_item`、`replacement_product`、`comparison_result`、`cart_update`、`quick_actions`、`audio_delta`、`done`、`error`。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| `docs/design.md` | **设计文档**：系统架构 / 技术栈 / 目录结构 / 配置 / 关键问题与方案 |
| `docs/highlights.md` | **产品与技术亮点**：精灵空间 / 复合需求 / 对话闭环 / Agent 架构 |
| `docs/deploy-and-experience.md` | **部署与体验指南**：5 分钟快速部署 / 评委体验 Checklist |
| `docs/CHANGELOG.md` | **版本升级日志**：v2.0 / v2.1 变更点与解决的问题 |
| `docs/architecture.md` | 系统架构总览 |
| `docs/api-contract.md` | API 契约 |
| `docs/realtime-protocol.md` | 实时通信协议 |
| `docs/runbook.md` | 开发运行手册 + 故障排查 |
| `deploy/README.md` | 部署说明 |
| `client/AGENTS.md` | 客户端开发指引 |
