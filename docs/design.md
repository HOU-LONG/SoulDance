# SoulDance -- 灵舞 -- 设计文档

## 系统架构

```
┌──────────────────────────────────────────────────────┐
│                  Android 客户端                        │
│  Jetpack Compose + Material3 + Coil + OkHttp          │
│  - AiMessageBlock 段落-卡片交替渲染                     │
│  - WebSocket 实时流式接收 + 精灵空间首页联动             │
│  - ProductDetailBottomSheet 锚点/卡片统一入口           │
└───────────────┬──────────────────────────────────────┘
                │ HTTPS + WebSocket
                │ (Cloudflare Tunnel 公网穿透)
┌───────────────▼──────────────────────────────────────┐
│              FastAPI 后端 (Python 3.13)                │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │  ToolPlanner.plan() -> UnifiedPlan            │     │
│  │  单次 LLM 调用，扁平字段携带全部决策信息          │     │
│  │  合并 ToolPlan + SemanticFrame + RetrievalPlan │     │
│  └───────────────┬──────────────────────────────┘     │
│                  │ _dispatch_tool (按 tool 字段分发)    │
│  ┌───────────────▼──────────────────────────────┐     │
│  │  事实锚定管道 (Fact-Grounded Pipeline)         │     │
│  │  FactContextBuilder  ->  构建 [[pid]] 事实表    │     │
│  │  AnchorValidator     ->  流式校验 + 锚点展开    │     │
│  │  HallucinationChecker -> 价格偏差兜底 (deferred)│     │
│  │  ConsistencyTracker  -> 跨轮 denial/focus drift│     │
│  └──────────────────────────────────────────────┘     │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │  核心组件层                                     │     │
│  │  StateReducer.apply_unified() 直接消费 UnifiedPlan │  │
│  │  QueryBuilder.build_from_unified()  构建检索计划 │     │
│  │  ProductMatcher     BM25 gap 置信度模糊匹配     │     │
│  │  rule_semantic_frame 纯规则引擎 (返回 UnifiedPlan) │   │
│  └──────────────────────────────────────────────┘     │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │  检索层 (Retrieval)                            │     │
│  │  EmbeddingRetriever / BM25OnlyRetriever        │     │
│  │  BM25(jieba) + _normalize_cjk_ascii() 预处理   │     │
│  │  RRF/weighted fusion + CrossEncoder rerank    │     │
│  └──────────────────────────────────────────────┘     │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │  SessionStore + 3-stage Checkpoint             │     │
│  │  degradation 上下文感知降级                      │     │
│  └──────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────┘
```

### 关键调用链

```
用户消息
  -> _do_stream_message()
     1. yield assistant_state("thinking")             # 立即反馈 (<1ms)
     2. ToolPlanner.plan() -> UnifiedPlan              # LLM 调用1: JSON completion (fast model)
     3. StateReducer.apply_unified(context, plan)
     4. _dispatch_tool() 按 plan.tool 分发
        |
        +-- product_analysis -> ProductAnalysisTool    # 单品分析 (含 ProductMatcher 模糊匹配)
        +-- chitchat         -> SmallTalkTool          # 闲聊 (注入 top-5 库内商品供锚点引用)
        +-- cart_operation   -> CartTool               # 购物车操作
        +-- product_followup -> ProductFollowupTool    # 追问
        +-- recommend_product/compare/scenario_bundle  # 走检索流
              -> QueryBuilder.build_from_unified()
              -> AdaptiveRetriever.search_async()
              -> FactContextBuilder.build()            # 构建事实表
              -> ConsistencyTracker.check_before_output()
              -> LLM 流式生成 (stream_response)        # LLM 调用2: 流式文本
              -> AnchorValidator.stream_process()      # 实时锚点校验
              -> HallucinationChecker.verify()         # deferred 价格检测
```

## 技术栈

| 层 | 技术 | 选型理由 |
|----|------|---------|
| **LLM Planner** | DeepSeek v4-pro / v4-flash | plan_tool 用 flash 降延迟；stream_response 用 pro |
| **后端框架** | FastAPI + Uvicorn | 原生 async/await，WebSocket 内置 |
| **检索引擎** | rank-bm25 + sentence-transformers | BM25 中文分词 (jieba) + dense 语义融合 |
| **重排序** | CrossEncoder (bge-reranker-v2-m3) | 融合后二次精排，失败静默降级 |
| **分词** | jieba 0.42 + CJK-ASCII 边界归一化 | 中文分词标准方案 + 修复"小米17Max"分词断裂 |
| **数据模型** | Pydantic v2 | 全链路类型校验 + JSON Schema |
| **数据库** | SQLite (购物车/订单/会话) | 嵌入式零配置，生产可迁 PostgreSQL |
| **Android UI** | Jetpack Compose + Material3 | 声明式 UI，Compose BOM 2026.04 |
| **图片加载** | Coil 2.7 | Compose 原生支持 |
| **网络层** | OkHttp 4.12 + Retrofit 2.11 | HTTP + WebSocket |
| **公网穿透** | Cloudflare Tunnel | 真机调试零配置 |
| **测试** | pytest + JUnit + MockWebServer | 后端 ~600 单测 / Android ~180 单测 |
| **仪表盘** | Chart.js v4 (CDN) | 零依赖可视化 |

## 事实锚定管道 (Fact-Grounded Pipeline)

为解决 LLM 幻觉（虚构不存在的商品型号/价格）和前后回答矛盾，引入事实锚定管道——LLM 只能引用检索层验证过的真实商品数据。

### 设计理念

管道将 LLM 生成过程分为三个阶段：事实注入（生成前）、锚点校验（生成中）、价格审计（生成后）。每个阶段都有明确的校验规则和降级策略，确保最终输出不会包含虚构的商品信息。

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **FactContextBuilder** | `fact_context.py` | 将检索排序结果组装为 LLM 唯一事实来源——`prompt_block` 含 `[[product_id]]` 锚点格式，LLM 只能引用库内真实商品 |
| **AnchorValidator** | `anchor_validator.py` | 流式循环状态机：逐 chunk 透传普通文本（零延迟），遇到 `[[pid]]` 锚点时微缓冲校验，命中则展开为商品名，未命中则替换为「该商品」 |
| **ConsistencyTracker** | `consistency_tracker.py` | 跨轮一致性校验：denial cache（已声明"不存在"的查询不重复出现）、focus drift 检测（用户确认的商品不被后续推荐遗忘） |
| **HallucinationChecker** | `hallucination_checker.py` | 价格偏差兜底检测——AnchorValidator 已覆盖虚构 ID/名称检测，本组件仅保留价格偏差审计 |

### FactContextBuilder

在 LLM 流式生成之前，将检索结果（`list[RankedProduct]`）组装为 `FactContext`：

- **`prompt_block`**: 注入 LLM system prompt 末尾，列出每个商品的 `[[product_id]]`、名称、品牌、价格、核心卖点，并附带规则约束——"引用时必须使用 `[[product_id]]` 锚点格式，任何未列在此库中的商品名称视为不存在"
- **`product_index`**: `dict[product_id, FactRecord]`，供 AnchorValidator 流式校验查询
- **`brand_index`**: `dict[brand, list[product_id]]`，供 ConsistencyTracker 跨轮品牌一致性校验
- **`denied_queries`**: 由 ConsistencyTracker 提供的已声明不存在查询列表，注入 prompt 防止 LLM 绕过高亮检测

### AnchorValidator 流式校验

```
LLM 逐 token 输出
  -> 普通文本: 立即透传 (零延迟)
  -> 遇到 [[ : 进入锚点缓冲 -> 收集到 ]] -> 查 product_index
      -> 命中: 展开为 **商品名** -> 立即透传
      -> 未命中: 替换为「该商品」+ yield anchor_warning 事件
  -> 同 chunk 内多锚点: 循环状态机处理（while '[[' in text）
  -> 跨 chunk 保护: 如果 chunk 以 '[' 结尾，缓冲到下一个 chunk
  -> 流结束后: deferred 裸奔名检测（未被 [[...]] 包裹的真实商品名 = stray_warning）
```

关键设计决策：
- **循环而非递归**：使用 `while '[[' in text` 循环消费同一 chunk 内的多个锚点，避免递归开销
- **`[` 后缀保护**：当 chunk 以 `[` 结尾时将其保留到 pending，防止 `[[` 被跨 chunk 分割
- **deferred 检测**：裸奔名检测在完整的原始文本上执行（而非展开后），避免已展开的锚点干扰检测

### HallucinationChecker（价格兜底）

在 AnchorValidator 流处理完成后，对流式输出收集的完整文本执行延迟的价格偏差检测：

- 用正则匹配文本中的所有 `¥xxx` / `xxx元` 价格提及
- 与 `FactContext.product_index` 中对应商品的真实价格对比
- 偏差超过 10% 则记录 `price_mismatch` 并下发给客户端

### ConsistencyTracker 跨轮校验

3 条纯规则（不调 LLM），在每次推荐生成前执行：

| 规则 | 检查内容 | 失败处理 |
|------|---------|---------|
| **Rule 1 (Denial Cache)** | 已声明「不存在」的查询词不重新出现在后续检索中 | 注入 `denied_queries` 到 FactContext prompt，阻止 LLM 重提旧查询 |
| **Rule 2 (Price Consistency)** | 同一 `product_id` 的报价与 FactContext 一致 | 由 AnchorValidator + HallucinationChecker 双层保证 |
| **Rule 3 (Focus Drift)** | `confirmed_product_id`（用户明确关注的商品）未出现在新推荐中 | 调用被 `check_before_output` 拦截，返回 `consistency_blocked` 事件 + 降级提示 |

### 3 阶段 Session Checkpoint

在 `SessionStore` 中实现回合级自动保存，支持异常恢复：

| 阶段 | 触发点 | 保存内容 |
|------|--------|---------|
| **turn_start** | `stream_message` 入口，追加用户消息后 | `dialog_turns` 已包含本次用户消息 |
| **post_retrieve** | 检索完成、`RetrievalPlan` 构建后 | `context.last_plan` 已写入 |
| **turn_end** | 流结束后 | 完整 `SessionContext`（含 `display_messages`、`recommendations`） |

`SessionStore.recover()` 根据 `checkpoint_stage` 返回不同级别的恢复提示：
- `turn_start` → 「你刚才的消息我已收到，正在重新理解...」
- `post_retrieve` → 「刚才的检索结果已恢复，我继续为你分析...」
- `turn_end` → 无需特殊提示

### 上下文感知降级

`degradation.py` 的 `fallback_text_for_failure()` 根据 `reason` 和当前 `SessionContext` 动态生成降级文案：

| reason | 行为 |
|--------|------|
| `llm_timeout` | 若存在关注商品则提示用户直接查看卡片，而非仅重新等待 |
| `retrieval_error` | 提示检索不稳定，但保留已知商品名供参考 |
| `llm_error` | 注入最后用户查询词和关注商品信息 |
| `contradiction_blocked` | 说明回复被拦截、建议换方式提问，保留商品上下文 |

## Stage 2: UnifiedPlan 统一决策载体

LLM 调用从 3 次减少到 2 次：`plan_tool` 的 JSON completion 合并了原来 `SemanticParser` + `IntentCompiler` + `PlannerAgent` 三轮 LLM 调用的信息。

### UnifiedPlan 模型

`models.py` 中的 `UnifiedPlan(BaseModel)` 是单次 LLM 调用的完整决策输出，扁平字段覆盖三类信息：

| 类别 | 字段 | 来源 |
|------|------|------|
| **工具路由** | `tool`, `confidence` | ToolPlan |
| **意图 + 澄清** | `need_clarification`, `clarification_question` | SemanticFrame |
| **硬约束** | `category`, `sub_category`, `price_min`, `price_max`, `include_brands`, `exclude_brands` | HardConstraints |
| **软偏好** | `soft_preferences` | RetrievalPlan |
| **检索参数** | `retrieval_query`, `retrieval_mode` | RetrievalPlan |
| **商品识别** | `target_product_query`, `category_hint` | ToolPlanArgs |
| **对比/分析/追问** | `compare_targets`, `analysis_aspect`, `followup_kind` | ToolPlanArgs + SemanticFrame |
| **购物车** | `cart_action`, `cart_target_product_id`, `cart_quantity` | CartOperation |

### 兼容层

为保持向后兼容，提供以下 alias 和 property：

```python
SemanticFrame = UnifiedPlan      # models.py 行 334
ShoppingIntentIR = UnifiedPlan   # models.py 行 335

# UnifiedPlan 的 compat property:
plan.intent          -> plan.tool           # 属性映射
plan.constraint_edits -> ConstraintEdits    # 自动从扁平字段构造
plan.cart_operation  -> CartOperation       # 自动从扁平字段构造
plan.query_intent    -> QueryIntent         # 自动从扁平字段构造
```

### 删除的模块和函数

| 删除项 | 说明 |
|--------|------|
| `intent_compiler.py` | LLM 语义解析路径完全废弃，由 UnifiedPlan 扁平字段 + `rule_semantic_frame()` 替代 |
| `_merge_tool_plan_into_ir()` | workaround 不再需要，UnifiedPlan 已包含全部字段 |
| `agent.plan()` 中的 `IntentCompiler` 调用 | `_dispatch_tool` + `_run_retrieval_flow` 走 UnifiedPlan 路径 |

### 被改写的函数

| 函数 | 变更 |
|------|------|
| `rule_semantic_frame()` | 直接返回 `UnifiedPlan`（不再返回 `SemanticFrame`），使用扁平字段设值 |
| `_merge_rule_guards()` | 操作 `UnifiedPlan` 扁平字段，不再操作嵌套 `ConstraintEdits` |
| `_parse_frame()` | 解析 LLM JSON 后返回 `UnifiedPlan`，自动将旧格式 `constraint_edits` 展开为扁平字段 |
| `_contextual_rule_followup()` | 返回 `UnifiedPlan`，使用 `followup_kind` + `response_goal` 扁平字段 |
| `StateReducer.apply_unified()` | 新增方法，直接消费 `UnifiedPlan` 扁平字段写入 `SessionContext` |
| `QueryBuilder.build_from_unified()` | 新增方法，从 `UnifiedPlan` 直接构建 `RetrievalPlan` |

## 依赖环境

### 后端 (Python 3.13+)

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
│       │   ├── MarkdownTextFormatter.kt     # Markdown -> AnnotatedString
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
│   │   ├── agent.py                         # * 核心 Agent (入口 + 分发 + 采集)
│   │   ├── tool_planner.py                  # * LLM 单一决策入口 -> UnifiedPlan
│   │   ├── tool_plan.py                     # ToolPlan + ToolPlanArgs (LLM 输出 schema)
│   │   ├── fact_context.py                  # * FactContextBuilder (事实表构建)
│   │   ├── anchor_validator.py              # * AnchorValidator (流式锚点校验)
│   │   ├── consistency_tracker.py           # * ConsistencyTracker (跨轮一致性)
│   │   ├── hallucination_checker.py         # 价格偏差检测 (兜底)
│   │   ├── session_store.py                 # SessionStore + 3-stage checkpoint
│   │   ├── degradation.py                   # 上下文感知降级文案
│   │   ├── product_matcher.py               # * BM25 模糊匹配 (gap 置信度)
│   │   ├── embedding_retriever.py           # BM25 + dense 检索 (_normalize_cjk_ascii)
│   │   ├── semantic_layer.py                # rule_semantic_frame + SemanticParser
│   │   ├── query_builder.py                 # build_from_unified / build
│   │   ├── state_reducer.py                 # apply_unified / apply
│   │   ├── reference_resolver.py            # 指代消解 (ReferenceResolver)
│   │   ├── models.py                        # 全量 Pydantic 模型 (含 UnifiedPlan)
│   │   ├── llm_client.py                    # LLM 客户端 (DeepSeek/Doubao + 熔断)
│   │   ├── trace_store.py                   # 请求追踪存储
│   │   ├── dev_console.py                   # 开发者仪表盘
│   │   ├── tools/                           # 8 个 Tool 实现
│   │   │   ├── retrieval.py                 # 推荐检索
│   │   │   ├── product_analysis.py          # 单品分析 (含 ProductMatcher 匹配)
│   │   │   ├── comparison.py                # 商品对比
│   │   │   ├── followup.py                  # 焦点商品追问
│   │   │   ├── cart.py                      # 购物车
│   │   │   ├── bundle.py                    # 场景搭配
│   │   │   ├── small_talk.py               # 闲聊 (含 chitchat 商品注入)
│   │   │   └── clarify.py                  # 澄清
│   │   ├── prompts/v1/                      # LLM 系统提示
│   │   │   ├── tool_planner.txt             # Planner 调度规则 (含 UnifiedPlan JSON schema)
│   │   │   ├── response.txt                 # 推荐回复风格
│   │   │   └── chitchat.txt                # 闲聊角色定位
│   │   ├── rag/                             # RAG 检索与排序 (HybridRetriever + Reranker)
│   │   └── main.py                          # FastAPI 入口 + WebSocket
│   ├── tests/                               # 后端测试 (~600 个)
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

### 问题 1：「华为 Pura 90 Pro 价格」被拒答

**现象**：用户问「华为 Pura 90 Pro 的价格是多少」，后端回复「我还没太抓到你的购物需求。你可以随便说个想买的东西、预算，或者不想要什么，我再帮你筛。」

**根因**：旧架构使用 5 层规则栈进行意图分类——`rule_semantic_frame` -> `_merge_rule_guards` -> `_normalize_intent` -> `_apply_product_admission_gate` -> `_primary_text_matches_selected`。其中第一层 `_has_shopping_signal` 用硬编码的词典匹配购物意图，词典里没有「Pura」「华为」等品牌词，也没有「多少钱」等价格询问词 -> 被判定为 `unclear_input` -> 走固定模板拒绝回答。

更深层问题：LLM 的语义理解能力被 5 层规则完全压制。即使 LLM 正确识别了用户意图，后续规则（特别是 `_primary_text_matches_selected`）如果发现回复文本不含「主推 商品名」等模板词，会直接用 FakeLLM 的固定模板**覆盖** LLM 的输出。

**解决方案**：

1. **Phase A -- 模糊商品匹配**：新增 `ProductMatcher`（`server/backend/app/product_matcher.py`），复用检索层已有的 BM25 分词索引。用户说「华为 Pura 70 Pro」、「小棕瓶」、「雀巢咖啡」等简称时，用同一套 retriever 做 `search(query, top_k=5)`，用 top1-vs-top2 的归一化分数差（gap）判断置信度——gap >= 0.15 视为明确命中，否则把候选透传给上层做二次判断。零额外索引、零额外模型。

2. **Phase B -- LLM Agent 架构**：新增 `ToolPlanner`（`server/backend/app/tool_planner.py`）和 `ToolPlan` schema（`server/backend/app/tool_plan.py`）。LLM 直接输出结构化的工具调度 JSON（`{"tool": "product_analysis", "args": {"target_product_query": "华为 Pura 90 Pro", "analysis_aspect": "price"}}`），Agent 入口 `_do_stream_message` 改为单点分发。删除了 `_apply_product_admission_gate` 的暴力降级逻辑和 `_looks_like_single_product_analysis` 的规则 hack。

3. **Phase C -- 回复自然化**：重写 `response.txt` 和 `chitchat.txt` prompt，去掉五段标签模板。弱化 `_primary_text_matches_selected`——不再用 FakeLLM 整段覆盖 LLM 输出，只记 warning 日志。幻觉检测 (`HallucinationChecker`) 保留作为安全网。

效果：真实 LLM 端到端测试，「华为 Pura 90 Pro 价格」 -> `tool=product_analysis, confidence=0.95, target_product_query="华为 Pura 90 Pro"` -> 「您提到的华为 Pura 90 Pro 目前尚未在官方渠道发布...如果您是想了解已上市的 Pura 70 系列，我可以为您做进一步对比参考。」——不拒答，不套模板。

### 问题 2：「连接中断，请重试」频繁超时

**现象**：用户发消息后等待 30 秒，Android App 显示「连接中断，请重试」。

**根因**：两条独立的超时配置互相打架——

1. Android 客户端 `STREAM_TIMEOUT_MILLIS = 30_000`（30 秒无事件则断连）
2. 后端 LLM 有两轮调用：`plan_tool()` 用 slow model (v4-pro) 做 JSON completion，耗时 15-25s；然后 `stream_response()` 做流式生成，首 chunk 耗时 10-20s。两轮合计 25-45s，超过客户端 30s 阈值。

更糟糕的是 `plan_tool()` 在 `_do_stream_message` 里是 `await` 同步等待——这期间客户端收不到任何 WebSocket 事件，连「我在干活」的信号都没有。客户端看到的就是空白气泡 + 30s 超时断连。

**解决方案**：

1. `STREAM_TIMEOUT_MILLIS`: 30s -> 90s（`ChatViewModel.kt`）
2. `DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS`: 12s -> 25s（`agent.py`）
3. 在 `plan_tool()` 调用之前立即 yield 一个 `assistant_state("thinking", "正在理解你的需求")` 事件——**客户端不到 1ms 就收到反馈**，不会误判死连
4. `plan_tool()` 已经使用 `LLM_FAST_MODEL`（v4-flash）做 JSON completion，比 v4-pro 快

效果：总耗时不变（25-45s），但用户体验从「空白->超时报错」变成「立即看到'正在思考'->等待->流式输出文本」。

### 问题 3：「心情不好推荐甜的」-> filter_recovery 「请选择类目」

**现象**：用户说「今天我心情不太好，你给我推荐一点适合我吃了以后能有好心情的」，后端回复「当前商品库里还没有能稳定匹配这个需求的类目。你可以换成现有商品类目再试。」

**根因**：这条消息同时包含情绪诉求（「心情不好」）和购物意图（「推荐好心情的食物」），但 ToolPlanner 把整条消息判为 `recommend_product`，LLM 给出的 `category_hint="零食"` 被传给 taxonomy resolver——而 taxonomy 里没有「零食」这个类目（只有「食品生活」），触发 `_looks_like_product_request` + `not taxonomy.is_known_request` -> `filter_recovery_options`，让用户先去选类目。

更深层问题：单 tool 架构无法同时处理「聊天」和「推荐」——要么全聊，要么全推。

**解决方案**：

1. `tool_planner.txt` prompt 增加第 6 条优先级规则：「复合需求（情绪/闲聊 + 购物）」 -> 路由到 `chitchat`，不再走 `recommend_product`
2. `chitchat.txt` prompt 增加复合需求处理说明：LLM 先共情再自然带出推荐，用 `[[商品名#product_id]]` 格式嵌入锚点
3. `_stream_no_retrieval_events` 改为两阶段：1) 调 LLM 前用 BM25 retriever 取 top-5 相关商品注入 prompt；2) LLM 流式输出后扫描文本中的 `[[name#product_id]]` -> 查 product_map -> 下发真实 `product_item` 事件
4. `_run_retrieval_flow` 里 taxonomy miss 时增加兜底：如果 `tool_plan.args.category_hint` 非空，直接用它做 `plan.retrieval_query` 去检索，跳过 recovery

效果：「心情不好推荐甜的」 -> `tool=chitchat` -> 「抱抱你~吃点甜的确实治愈。给你挑了两款：[[百草味每日坚果#p_food_019]] 和 [[良品铺子肉松饼#p_food_010]]，看看喜不喜欢？」——既有情绪关怀，又有真实商品卡片。

### 问题 4：内联商品卡片的锚点用了虚构 product_id

**现象**：chitchat 流里 LLM 输出了「给你推荐 [[丝滑牛奶巧克力#p_choco_001]]」，但 `p_choco_001` 是 LLM 编的——库里根本没有这个 ID -> `_extract_anchor_product_ids` 在 `product_map` 里找不到 -> 不下发 `product_item` -> 前端不显示卡片。

**根因**：LLM 不知道库里有哪些商品。它能根据通用知识推荐「巧克力」「糖果」，但 product_id 必须来自 catalog。

**解决方案**：在 `_stream_no_retrieval_events` -> `_enrich_chitchat_message` 里调用 LLM 之前，用 `self.retriever.search(user_message, top_k=5)` 取前 5 个相关商品，拼成 `[本店相关商品]` 列表注入到 LLM 的 user message 里：

```
[本店相关商品（可用 [[商品名#product_id]] 锚点提及）]
- p_food_019: 百草味 每日坚果A款 750g/30袋 ￥89 (百草味 食品生活)
- p_food_010: 良品铺子 肉松饼1000g/箱 ￥39 (良品铺子 食品生活)
- p_food_022: 雀巢咖啡 1+2原味 三合一速溶咖啡粉100条 ￥60 (雀巢 食品生活)
```

LLM 现在能看到真实的商品列表 -> 输出的锚点使用真实 ID -> 后端验证通过 -> `product_item` 下发 -> 前端渲染内联卡片。零额外 LLM 调用。

### 问题 5：追加问题时注意力失焦——「这个/刚才那个」无法解析

**现象**：用户先要了一款推荐，然后追问「这个多少钱？」、「换个更便宜的」、「为什么推荐它？」——但 AI 不知道「这个」指什么，要么回退到泛泛的推荐，要么报「我还没有可以替换的上一款商品」。

**根因**：这是多轮对话中最经典的**指代消解**问题。旧架构用硬编码的词典规则来识别——`EXPLAIN_FOCUS_MARKERS = ("刚刚那个是什么", "刚才那个是什么", "为什么推荐", "介绍一下", "这个是什么")`。这个列表只有 5 个词，任何稍微变化的追问（「它怎么样？」、「那这个价格？」、「说说它的参数」）全都不命中 -> 要么降级到 `unclear_input`，要么走一遍完整的推荐重筛流程——用户问个价格，AI 重新推荐了一轮。

更根本的问题是：规则系统无法理解「这个」指代的是会话历史上哪款商品。同样的词「这个」，在不同上下文里可能指向焦点商品、上一条推荐的主推、或最后一次加购的商品，规则无法区分。

**解决方案**：通过**上下文注入**实现跨轮次注意力保持——

1. **SessionContext 结构化焦点追踪**（`models.py`）：`focus_product_id`（当前焦点商品）、`last_product_ids`（上轮推荐的商品列表）、`last_recommendations`（含 role/price/brand 的推荐记录）、`recent_cart_product_id`（最近加购的商品）。这些字段在每次推荐、对比、加购操作中持续更新。

2. **ReferenceResolver 确定性消解**（`reference_resolver.py`）：当检测到「这个/刚才/它/前面那个」等指代词时，按优先级依次尝试：1) `focus_product`（当前焦点商品）-> 2) `last_recommendations` 中 role=primary 的主推 -> 3) `recent_cart_product_id` -> 4) `last_product_ids[-1]`。每一步都有明确的 fallback 逻辑，不会凭空编造。

3. **长会话锚点持久化**（`agent.py` `_prepare_context_for_turn`）：首轮品牌/类目/product_ids 存储为 `reference_anchors`，当用户跨多轮后再说「回到第一轮那个」，触发 `anchor_reference -> first_turn` 解析，从 `reference_anchors["first_turn_brand"]` 恢复硬约束。

4. **LLM 上下文注入**（`semantic_layer.py`）：SemanticParser 的 LLM prompt 包含 `session_context` 字段（`has_focus_product` / `focus_product_id` / `last_product_ids` / `last_recommendations`），让 LLM 在意图解析时知道「当前在聊哪款商品」——即使客户端传的是 `product_followup` 类型，后端仍能根据上下文推断用户到底在追问什么（解释 / 更便宜 / 换品牌 / 问参数）。

5. **Followup Tool 分支处理**：`product_followup` 工具根据 LLM 给出的 `followup_kind` 走不同路径——`explain/specs/price` 直接调 LLM 用焦点商品 evidence 自由回答（不走推荐重筛），`cheaper/more_expensive/exclude_brand` 走检索替换流。

效果：用户说「推荐一款咖啡」-> AI 推荐雀巢 -> 用户说「这个多少钱？」-> `product_followup, followup_kind=price` -> 直接回答「刚才推荐的雀巢咖啡售价 60 元，100 条装，折合每条 6 毛钱」——不再重新推荐一遍。

### 问题 6：BM25 假命中 + 旧规则过滤的笨拙刻板

**现象**：用户输入「完全编造的型号 XYZ-999」——本意是胡扯一句话，不应匹配任何商品。但 BM25 retriever 返回了 `Apple MacBook Pro 14英寸 M5 芯片...`，score=1.0。这是因为「型号」这个词出现在 MacBook 的 chunk 文本中（含大量 SKU 规格如「芯片型号：M5 芯片」），「Pro」也是一个高频商品词，BM25 分词后只要任一 token 命中就有分数。

但问题不止于此——**旧版规则过滤让这个场景更糟糕**。在引入 ProductMatcher 之前，商品识别用的是 `resolve_named_product`（`reference_resolver.py`），它用硬编码的 score 阈值 + 关键词 heuristics：

```python
# 旧版逻辑（已废弃）
if brand_lower and brand_lower in text: score += 30
if text in title_lower: score += 60
if best_score >= 50: return best_product  # 硬阈值
```

这套规则有三大问题：

1. **阈值僵硬**：`best_score >= 50` 是一个拍脑袋的值。用户查「小米 17」时品牌「小米」匹配 +30，部分标题匹配不到 +0，总分 30 -> 不够 50 -> 返回 None -> 上层不知道库里确实有小米 17 系列（Max/Ultra/Pro），直接说「库里没有」。
2. **无法表达模糊度**：score 是单向的绝对值，没有相对信号。查「小米 17」和查「雀巢咖啡」都是匹配到了某些 token——但前者是多款同系商品的模糊匹配，后者是精准命中特定商品——score 看不出来。
3. **对假命中无感知**：查「完全编造的型号 XYZ-999」时，「型号」和「Pro」两条 token 碰巧命中，score 堆到 60 -> 超过阈值 -> 返回 MacBook Pro——系统根本不怀疑「这个人问的是完全不存在的型号吗？」。

**解决方案**：

1. **ProductMatcher 替代硬阈值匹配**（`product_matcher.py`）：不再用绝对 score 判断，改用 **top1-vs-top2 的归一化分数差（gap）** 作为置信度信号：

   | 查询 | top1 score | top2 score | gap | 判定 |
   |------|-----------|-----------|-----|------|
   | 雀巢咖啡 | 1.0 | 0.0 | **1.0** | 明确命中 |
   | 华为 Pura 70 | 1.0 | 0.62 | **0.38** | 明确命中 |
   | 小米 17 | 1.0 | 0.99 | **0.01** | 模糊，best=None |
   | 完全编造 | 1.0 | 0.82 | **0.18** | 模糊，best=None |

   关键设计：因为 BM25 的归一化只依赖当前 query 自己的 max/min，top1 始终是 1.0——**绝对分数无法区分强弱匹配**。但 gap 反映的是「top1 到底比其他候选强多少」——这是一个相对信号，不受归一化影响。当用户问「小米 17」时，gap=0.01 说明 top1(top2) 都是小米 17 系列，分不出谁更匹配 -> 模糊；当用户问「雀巢咖啡」时，gap=1.0 说明 top1 远远强于所有其他候选 -> 明确命中。

2. **假命中保护**：当 top1 raw score <= 0（即 retriever 返回的所有候选归一化前原始分均为 0）时，直接返回 best=None、candidates=[]——「完全编造的型号」可能因为「型号」词触发 BM25 得分，但如果同时没有其他 token 匹配（品牌、子类目、标题特有词），top2 和 top1 之间仍然存在 gap。`min_gap=0.15` 的阈值恰好过滤掉这类「只靠 1-2 个共通词命中」的假阳性。

3. **LLM Planner 做语义兜底**：即使 ProductMatcher 返回了模糊结果或假命中（best=None 但 candidates 非空），上游的 ToolPlanner 仍会根据用户消息的语义做二次判断。「完全编造的型号 XYZ-999」经过 LLM Planner 后会输出 `tool=product_analysis, target_product_query="..."`，但 ProductMatcher 的模糊结果（best=None）加上 LLM 的通用知识（「XYZ-999 不是任何已知产品型号」）最终会走 `product_analysis_unknown` 流程——「你提到的 XYZ-999 似乎不是已知产品型号，要不要看看本店现有的同类商品？」——而不是假装命中了某个商品。

4. **旧规则栈完全废弃**：`resolve_named_product` 的硬阈值逻辑已被 ProductMatcher 的 gap-based 置信度完全替代。`rule_semantic_frame`、`_merge_rule_guards`、`_normalize_intent`、`_apply_product_admission_gate` 这 4 层规则栈在 ToolPlanner 架构下不再被调用（仅保留 `SemanticParser` 对象供 `agent.plan()` 旧路径兼容，新入口 `_do_stream_message` 不经过它们）。

### 问题 7：Product Analysis Tool 匹配成功但 LLM 未收到商品数据

**现象**：用户问「详细分析一下小米 17 Max」，ProductMatcher 正确匹配到库内商品 `小米 17 Max`，但 LLM 回复的内容中没有用到任何库内商品信息——price、brand、specs 全部缺失，LLM 用通用知识回答。

**根因**：Product Analysis Tool 的旧实现中，`ProductMatcher.match()` 成功返回了 product 对象，但传给 LLM 的 prompt 只包含原始 user message，没有把匹配到的商品数据（title、price、brand、specs）注入进去——LLM 看不到自己匹配到了什么。

**解决方案**：在 Product Analysis Tool 命中商品后，构建 `enriched_message`：

```
[本店匹配到的商品]
商品ID: p_phone_003
名称: 小米 17 Max
品牌: 小米
价格: ￥5999
核心卖点: 骁龙8 Gen4 | 5000mAh | 徕卡影像
---
用户问题: 详细分析一下小米 17 Max
```

LLM prompt 现在包含完整商品事实 -> 回复中可以引用真实价格和参数 -> 不会因不知道商品信息而用通用知识搪塞。零额外 LLM 调用。

### CJK-ASCII 分词边界归一化

#### 问题

jieba 分词把「小米17Max」切成 `['小米', '17Max']`，而数据库标题「小米 17 Max」切成 `['小米', '17', 'Max']`。由于「17Max」作为一个整体 token 无法匹配到分别独立的「17」和「Max」，BM25 匹配失败，导致商品明明在库中却检索不到。

#### 根因验证

```
Query: 小米17Max       -> tokens: ['小米', '17Max']   -> best=None (confidence=0.03)
Query: 小米 17 Max     -> tokens: ['小米', '17', 'Max'] -> best=小米 17 Max (confidence=0.34)
```

关键差异仅仅是用户输入中没有空格——这在移动端输入场景中非常常见。

#### 修复

在 `EmbeddingRetriever._tokenize()`（`embedding_retriever.py`）中增加 `_normalize_cjk_ascii()` 预处理：

1. **CJK (arrow) ASCII 边界插入空格**：`小米17` -> `小米 17`
2. **数字 (arrow) 字母边界插入空格**：`17Max` -> `17 Max`

```python
_CJK_ASCII_BOUNDARY = re.compile(r'([一-鿿])|([a-zA-Z0-9])|([a-zA-Z0-9])|([一-鿿])'))
_DIGIT_ALPHA_BOUNDARY = re.compile(r'([0-9])|([a-zA-Z])|([a-zA-Z])|([0-9])'))

def _normalize_cjk_ascii(text: str) -> str:
    text = _CJK_ASCII_BOUNDARY.sub(r'\1\3 \2\4', text)
    text = _DIGIT_ALPHA_BOUNDARY.sub(r'\1\3 \2\4', text)
    return text
```

修复后所有变体均正确命中：

| Query | 归一化后 | Best Match |
|-------|---------|------------|
| 小米17Max | 小米 17 Max | 小米 17 Max |
| 详细分析一下小米17Max的优缺点 | 详细分析一下小米 17 Max 的优缺点 | 小米 17 Max |
| 小米17Max性价比怎么样 | 小米 17 Max 性价比怎么样 | 小米 17 Max |

因为检索索引构建时也经过同一 `_tokenize()`，查询端和文档端分词完全对称，BM25 匹配正确。
