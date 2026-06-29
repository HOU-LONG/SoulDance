# SoulDance · 灵舞 — 设计文档

## 系统架构

```
┌──────────────────────────────────────────────────────┐
│                  Android 客户端                        │
│  Jetpack Compose + Material3 + Coil + OkHttp          │
│  · AiMessageBlock 段落-卡片交替渲染                     │
│  · WebSocket 实时流式接收 + 精灵空间首页联动             │
│  · ProductDetailBottomSheet 锚点/卡片统一入口           │
└───────────────┬──────────────────────────────────────┘
                │ HTTPS + WebSocket
                │ (Cloudflare Tunnel 公网穿透)
┌───────────────▼──────────────────────────────────────┐
│              FastAPI 后端 (Python 3.12)                │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │         ToolPlanner (LLM 决策入口)             │     │
│  │  plan_tool() → ToolPlan JSON                  │     │
│  │  7 种 tool: recommend / analysis / compare    │     │
│  │  / cart / bundle / followup / chitchat        │     │
│  └───────────────┬──────────────────────────────┘     │
│                  │ _dispatch_tool                      │
│  ┌───────────────┼──────────────────────────────┐     │
│  │  ProductMatcher  │  BM25 模糊匹配 (共享索引)   │     │
│  │  IntentCompiler  │  旧 IR 编译器 (检索流用)    │     │
│  │  QueryBuilder    │  RetrievalPlan 构建         │     │
│  │  StateReducer    │  约束状态管理               │     │
│  │  HallucinationChecker │ 幻觉检测 (安全网)      │     │
│  └──────────────────────────────────────────────┘     │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │         Retrieval Layer                       │     │
│  │  EmbeddingRetriever / BM25OnlyRetriever        │     │
│  │  BM25(jieba) + Dense(sentence-transformers)   │     │
│  │  RRF/weighted fusion + CrossEncoder rerank    │     │
│  └──────────────────────────────────────────────┘     │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │         Trace & Observability                 │     │
│  │  TraceStore ring buffer + JSONL               │     │
│  │  /dev Developer Console (Chart.js dashboard)  │     │
│  │  Prompt 热更新 (零重启)                        │     │
│  └──────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────┘
```

## 技术栈

| 层 | 技术 | 选型理由 |
|----|------|---------|
| **LLM Planner** | DeepSeek v4-pro / v4-flash | plan_tool 用 fast model 降低延迟 |
| **后端框架** | FastAPI + Uvicorn | 原生 async/await，WebSocket 内置 |
| **检索引擎** | rank-bm25 + sentence-transformers | BM25 中文分词 (jieba) + dense 语义融合 |
| **重排序** | CrossEncoder (bge-reranker-v2-m3) | 融合后二次精排，失败静默降级 |
| **分词** | jieba 0.42 | 中文分词标准方案 |
| **数据模型** | Pydantic v2 | 全链路类型校验 + JSON Schema |
| **数据库** | SQLite (购物车/订单/会话) | 嵌入式零配置，生产可迁 PostgreSQL |
| **Android UI** | Jetpack Compose + Material3 | 声明式 UI，Compose BOM 2026.04 |
| **图片加载** | Coil 2.7 | Compose 原生支持 |
| **网络层** | OkHttp 4.12 + Retrofit 2.11 | HTTP + WebSocket |
| **公网穿透** | Cloudflare Tunnel | 真机调试零配置 |
| **测试** | pytest + JUnit + MockWebServer | 后端 129 单测 / Android 178 单测 |
| **仪表盘** | Chart.js v4 (CDN) | 零依赖可视化 |

## 依赖环境

### 后端 (Python 3.12+)

```
fastapi==0.136.3
uvicorn[standard]==0.48.0
openai==2.38.0
httpx==0.28.1
websockets==16.0
pydantic==2.13.4
numpy==2.3.5
jieba==0.42.1
rank-bm25==0.2.2
sentence-transformers==5.1.2
```

### 前端 (JDK 17+, Android SDK 36)

```
Kotlin 2.3.21
Compose BOM 2026.04.01
Coil 2.7.0
OkHttp 4.12.0
Retrofit 2.11.0
minSdk 26 / targetSdk 36
```

## 目录结构

```
SoulDance/
├── client/                                  # Android 应用
│   └── app/src/main/java/.../
│       ├── ui/component/                    # UI 组件
│       │   ├── AiMessageBlock.kt            # 消息气泡 + 段落-卡片交替
│       │   ├── InlineProductCard.kt         # 内联商品卡片
│       │   ├── AiMessageChunking.kt         # 按空行切段 + 锚点解析
│       │   ├── MarkdownTextFormatter.kt     # Markdown → AnnotatedString
│       │   └── ProductDetailBottomSheet.kt  # 商品详情浮层
│       ├── ui/home/                         # 精灵空间首页
│       │   ├── SpriteHomeScreen.kt          # 首页布局
│       │   ├── SpriteHomeViewModel.kt       # 精灵状态 + 任务 + 升级
│       │   ├── SpriteStage.kt               # 2D 精灵渲染
│       │   ├── SpriteAssetRegistry.kt       # 外观素材映射
│       │   └── SpriteHomeUiState.kt         # 首页 UI 状态
│       ├── vm/ChatViewModel.kt              # 聊天 ViewModel
│       └── config/AppConfig.kt              # 后端地址配置
├── server/
│   ├── backend/app/
│   │   ├── agent.py                         # ★ 核心 Agent (入口 + 分发 + 采集)
│   │   ├── tool_planner.py                  # ★ LLM 决策入口
│   │   ├── tool_plan.py                     # ToolPlan Pydantic schema
│   │   ├── product_matcher.py               # ★ BM25 模糊匹配
│   │   ├── llm_client.py                    # LLM 客户端 (DeepSeek/Doubao)
│   │   ├── trace_store.py                   # 请求追踪存储
│   │   ├── dev_console.py                   # 开发者仪表盘
│   │   ├── tools/                           # 7 个 Tool 实现
│   │   │   ├── retrieval.py                 # 推荐检索
│   │   │   ├── product_analysis.py          # 单品分析
│   │   │   ├── comparison.py                # 商品对比
│   │   │   ├── followup.py                  # 焦点商品追问
│   │   │   ├── cart.py                      # 购物车
│   │   │   ├── bundle.py                    # 场景搭配
│   │   │   └── small_talk.py               # 闲聊 (chitchat)
│   │   ├── prompts/v1/                      # LLM 系统提示
│   │   │   ├── tool_planner.txt             # Planner 调度规则
│   │   │   ├── response.txt                 # 推荐回复风格
│   │   │   └── chitchat.txt                # 闲聊角色定位
│   │   ├── rag/                             # RAG 检索与排序
│   │   ├── models.py                        # 全量 Pydantic 模型
│   │   └── main.py                          # FastAPI 入口 + WebSocket
│   ├── tests/                               # 后端测试 (129 个)
│   └── scripts/                             # 启动/部署脚本
├── ecommerce_agent_dataset/                 # 商品数据 (100 款，含图片)
├── docs/                                    # 文档
├── deploy/                                  # 部署模板
└── data/                                    # 运行时数据 (git ignore)
```

## 配置说明

### LLM Provider

仓库根目录 `.env`：

```bash
LLM_PROVIDER=deepseek                  # 或 doubao
LLM_API_KEY=sk-xxx                     # API Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro             # 流式生成用
LLM_FAST_MODEL=deepseek-v4-flash      # plan_tool JSON 用 (更快)
LLM_REASONING_EFFORT=high             # 推理深度
```

### 后端

```bash
# 端口 + 内嵌模型开关
HOST=0.0.0.0 PORT=8000
RERANK_ENABLED=true                   # CrossEncoder 重排
USE_EMBEDDING=true                    # dense 向量检索
TTS_ENABLED=false                     # 语音合成
STT_ENABLED=false                     # 语音识别
SHOPGUIDE_DATABASE_URL=               # SQLite 路径 (默认 data/shopguide.db)
```

### Android

`client/.../config/AppConfig.kt`：

```kotlin
const val BASE_HTTP_URL = "https://xxx.trycloudflare.com/"
const val BASE_WS_URL = "wss://xxx.trycloudflare.com"
const val WS_CHAT_PATH = "/ws/chat"
```

编译时 Gradle 脚本 (`ensure_tunnel.sh`) 自动检测 Cloudflare tunnel 可用性并更新 URL。
也可 `SKIP_TUNNEL_CHECK=true` 跳过。

### 版本号

`versionCode` / `versionName` 基于 `git rev-list --count HEAD` 自动生成。

---

## 关键问题与解决方案

### 问题 1："华为 Pura 90 Pro 价格" 被拒答

**现象**：用户问"华为 Pura 90 Pro 的价格是多少"，后端回复"我还没太抓到你的购物需求。你可以随便说个想买的东西、预算，或者不想要什么，我再帮你筛。"

**根因**：旧架构使用 5 层规则栈进行意图分类——`rule_semantic_frame` → `_merge_rule_guards` → `_normalize_intent` → `_apply_product_admission_gate` → `_primary_text_matches_selected`。其中第一层 `_has_shopping_signal` 用硬编码的词典匹配购物意图，词典里没有"Pura""华为"等品牌词，也没有"多少钱"等价格询问词 → 被判定为 `unclear_input` → 走固定模板拒绝回答。

更深层问题：LLM 的语义理解能力被 5 层规则完全压制。即使 LLM 正确识别了用户意图，后续规则（特别是 `_primary_text_matches_selected`）如果发现回复文本不含"主推 商品名"等模板词，会直接用 FakeLLM 的固定模板**覆盖** LLM 的输出。

**解决方案**：

1. **Phase A — 模糊商品匹配**：新增 `ProductMatcher`（`server/backend/app/product_matcher.py`），复用检索层已有的 BM25 分词索引。用户说"华为 Pura 70 Pro"、"小棕瓶"、"雀巢咖啡"等简称时，用同一套 retriever 做 `search(query, top_k=5)`，用 top1-vs-top2 的归一化分数差（gap）判断置信度——gap ≥ 0.15 视为明确命中，否则把候选透传给上层做二次判断。零额外索引、零额外模型。

2. **Phase B — LLM Agent 架构**：新增 `ToolPlanner`（`server/backend/app/tool_planner.py`）和 `ToolPlan` schema（`server/backend/app/tool_plan.py`）。LLM 直接输出结构化的工具调度 JSON（`{"tool": "product_analysis", "args": {"target_product_query": "华为 Pura 90 Pro", "analysis_aspect": "price"}}`），Agent 入口 `_do_stream_message` 改为单点分发。删除了 `_apply_product_admission_gate` 的暴力降级逻辑和 `_looks_like_single_product_analysis` 的规则 hack。

3. **Phase C — 回复自然化**：重写 `response.txt` 和 `chitchat.txt` prompt，去掉五段标签模板。弱化 `_primary_text_matches_selected`——不再用 FakeLLM 整段覆盖 LLM 输出，只记 warning 日志。幻觉检测 (`HallucinationChecker`) 保留作为安全网。

效果：真实 LLM 端到端测试，"华为 Pura 90 Pro 价格" → `tool=product_analysis, confidence=0.95, target_product_query="华为 Pura 90 Pro"` → "您提到的华为 Pura 90 Pro 目前尚未在官方渠道发布...如果您是想了解已上市的 Pura 70 系列，我可以为您做进一步对比参考。"——不拒答，不套模板。

### 问题 2："连接中断，请重试" 频繁超时

**现象**：用户发消息后等待 30 秒，Android App 显示"连接中断，请重试"。

**根因**：两条独立的超时配置互相打架——

1. Android 客户端 `STREAM_TIMEOUT_MILLIS = 30_000`（30 秒无事件则断连）
2. 后端 LLM 有两轮调用：`plan_tool()` 用 slow model (v4-pro) 做 JSON completion，耗时 15-25s；然后 `stream_response()` 做流式生成，首 chunk 耗时 10-20s。两轮合计 25-45s，超过客户端 30s 阈值。

更糟糕的是 `plan_tool()` 在 `_do_stream_message` 里是 `await` 同步等待——这期间客户端收不到任何 WebSocket 事件，连"我在干活"的信号都没有。客户端看到的就是空白气泡 + 30s 超时断连。

**解决方案**：

1. `STREAM_TIMEOUT_MILLIS`: 30s → 90s（`ChatViewModel.kt`）
2. `DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS`: 12s → 25s（`agent.py`）
3. 在 `plan_tool()` 调用之前立即 yield 一个 `assistant_state("thinking", "正在理解你的需求")` 事件——**客户端不到 1ms 就收到反馈**，不会误判死连
4. `plan_tool()` 已经使用 `LLM_FAST_MODEL`（v4-flash）做 JSON completion，比 v4-pro 快

效果：总耗时不变（25-45s），但用户体验从"空白→超时报错"变成"立即看到'正在思考'→等待→流式输出文本"。

### 问题 3："心情不好推荐甜的" → filter_recovery "请选择类目"

**现象**：用户说"今天我心情不太好，你给我推荐一点适合我吃了以后能有好心情的"，后端回复"当前商品库里还没有能稳定匹配这个需求的类目。你可以换成现有商品类目再试。"

**根因**：这条消息同时包含情绪诉求（"心情不好"）和购物意图（"推荐好心情的食物"），但 ToolPlanner 把整条消息判为 `recommend_product`，LLM 给出的 `category_hint="零食"` 被传给 taxonomy resolver——而 taxonomy 里没有"零食"这个类目（只有"食品生活"），触发 `_looks_like_product_request` + `not taxonomy.is_known_request` → `filter_recovery_options`，让用户先去选类目。

更深层问题：单 tool 架构无法同时处理"聊天"和"推荐"——要么全聊，要么全推。

**解决方案**：

1. `tool_planner.txt` prompt 增加第 6 条优先级规则："复合需求（情绪/闲聊 + 购物）" → 路由到 `chitchat`，不再走 `recommend_product`
2. `chitchat.txt` prompt 增加复合需求处理说明：LLM 先共情再自然带出推荐，用 `[[商品名#product_id]]` 格式嵌入锚点
3. `_stream_no_retrieval_events` 改为两阶段：① 调 LLM 前用 BM25 retriever 取 top-5 相关商品注入 prompt；② LLM 流式输出后扫描文本中的 `[[name#product_id]]` → 查 product_map → 下发真实 `product_item` 事件
4. `_run_retrieval_flow` 里 taxonomy miss 时增加兜底：如果 `tool_plan.args.category_hint` 非空，直接用它做 `plan.retrieval_query` 去检索，跳过 recovery

效果："心情不好推荐甜的" → `tool=chitchat` → "抱抱你～吃点甜的确实治愈。给你挑了两款：[[百草味每日坚果#p_food_019]] 和 [[良品铺子肉松饼#p_food_010]]，看看喜不喜欢？"——既有情绪关怀，又有真实商品卡片。

### 问题 4：内联商品卡片的锚点用了虚构 product_id

**现象**：chitchat 流里 LLM 输出了"给你推荐 [[丝滑牛奶巧克力#p_choco_001]]"，但 `p_choco_001` 是 LLM 编的——库里根本没有这个 ID → `_extract_anchor_product_ids` 在 `product_map` 里找不到 → 不下发 `product_item` → 前端不显示卡片。

**根因**：LLM 不知道库里有哪些商品。它能根据通用知识推荐"巧克力""糖果"，但 product_id 必须来自 catalog。

**解决方案**：在 `_stream_no_retrieval_events` 里调用 LLM 之前，用 `self.retriever.search(user_message, top_k=5)` 取前 5 个相关商品，拼成 `[本店相关商品]` 列表注入到 LLM 的 user message 里：

```
[本店相关商品（可用 [[商品名#product_id]] 锚点提及）]
- p_food_019: 百草味 每日坚果A款 750g/30袋 ¥89 (百草味 食品生活)
- p_food_010: 良品铺子 肉松饼1000g/箱 ¥39 (良品铺子 食品生活)
- p_food_022: 雀巢咖啡 1+2原味 三合一速溶咖啡粉100条 ¥60 (雀巢 食品生活)
```

LLM 现在能看到真实的商品列表 → 输出的锚点使用真实 ID → 后端验证通过 → `product_item` 下发 → 前端渲染内联卡片。零额外 LLM 调用。
