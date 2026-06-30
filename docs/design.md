# SoulDance -- 灵舞 -- 设计文档

## 1. 系统架构图

```
┌──────────────────────────────────────────────────────────┐
│                    Android 客户端                          │
│  Jetpack Compose + Material3 + Coil + OkHttp              │
│  - AiMessageBlock 段落-卡片交替渲染                         │
│  - WebSocket 实时流式接收 + 精灵空间首页联动                  │
│  - ProductDetailBottomSheet 锚点/卡片统一入口               │
└───────────────┬──────────────────────────────────────────┘
                │ HTTPS + WebSocket
                │ (Cloudflare Tunnel 公网穿透)
┌───────────────▼──────────────────────────────────────────┐
│               FastAPI 后端 (Python 3.13)                    │
│                                                            │
│  ┌─────────────────────────────────────────────────┐      │
│  │  ToolPlanner.plan() → UnifiedPlan                 │      │
│  │  单次 LLM 调用 (JSON completion, fast model)       │      │
│  │  扁平字段携带全部决策信息:                            │      │
│  │  工具路由 + 意图 + 硬约束 + 软偏好 + 检索参数          │      │
│  └───────────────┬─────────────────────────────────┘      │
│                  │ StateReducer.apply_unified()            │
│                  │ _dispatch_tool() 按 tool 字段分发        │
│  ┌───────────────▼─────────────────────────────────┐      │
│  │  事实锚定管道 (Fact-Grounded Pipeline)             │      │
│  │  FactContextBuilder   → 构建 [[pid]] 事实表         │      │
│  │  AnchorValidator      → 流式锚点校验 + 展开         │      │
│  │  HallucinationChecker → 价格偏差兜底检测 (deferred)  │      │
│  │  ConsistencyTracker   → 跨轮 denial / focus drift │      │
│  └─────────────────────────────────────────────────┘      │
│                                                            │
│  ┌─────────────────────────────────────────────────┐      │
│  │  8 个工具 (按 UnifiedPlan.tool 单点分发)             │      │
│  │  recommend_product  product_analysis  chitchat    │      │
│  │  compare_products   scenario_bundle  cart_op      │      │
│  │  product_followup   clarification                 │      │
│  └─────────────────────────────────────────────────┘      │
│                                                            │
│  ┌─────────────────────────────────────────────────┐      │
│  │  检索层 (Retrieval)                                │      │
│  │  AdaptiveRetriever (BM25 + dense + RRF + Rerank)  │      │
│  │  BM25 (jieba) + _normalize_cjk_ascii() 预处理      │      │
│  │  ProductMatcher: BM25 gap 置信度模糊匹配           │      │
│  └─────────────────────────────────────────────────┘      │
│                                                            │
│  ┌─────────────────────────────────────────────────┐      │
│  │  SessionStore + 3-stage Checkpoint                │      │
│  │  degradation 上下文感知降级文案                     │      │
│  └─────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────┘
```

## 2. 架构概述

### 2.1 整体设计

SoulDance 后端采用 **LLM 优先的 Agent 架构**：用户消息进，结构化事件流（text_delta + product_item + quick_actions）出。核心设计原则：

- **单次 LLM 决策入口**：ToolPlanner 一次 JSON completion 输出 UnifiedPlan，包含工具路由、意图标记、硬约束、软偏好、检索参数等全部决策信息。后续不再有额外的 LLM 意图解析调用。
- **事实锚定管道**：在 LLM 流式生成前注入事实表（FactContext），生成中以 AnchorValidator 逐 chunk 校验锚点，生成后用 HallucinationChecker 做价格偏差兜底。LLM 只能引用检索层验证过的真实商品数据。
- **CJK-ASCII 分词边界归一化**：修复 jieba 对 "小米17Max" 等的分词断裂问题，在 BM25 分词前自动在 CJK/数字/字母边界插入空格。
- **3 阶段 Session Checkpoint**：turn_start / post_retrieve / turn_end 三个时机自动保存，支持异常恢复。
- **上下文感知降级**：根据失败原因和当前 SessionContext 动态生成降级文案，而非统一模板。

### 2.2 LLM 调用次数

每轮对话 **最多 2 次 LLM 调用**：

| 调用 | 时机 | 模型 | 输出 |
|------|------|------|------|
| LLM 调用 1 | `_do_stream_message` 入口 | fast model (v4-flash) | JSON → UnifiedPlan |
| LLM 调用 2 | 检索完成后 | pro model (v4-pro) | 流式文本生成 |

如果 UnifiedPlan.tool 为 `cart_operation` 或 `clarification`，则跳过 LLM 调用 2。

### 2.3 3 阶段 Session Checkpoint

| 阶段 | 触发点 | 保存内容 |
|------|--------|---------|
| **turn_start** | `stream_message` 入口，追加用户消息后 | `dialog_turns` 已包含本次用户消息 |
| **post_retrieve** | 检索完成、RetrievalPlan 构建后 | `context.last_plan` 已写入 |
| **turn_end** | 流结束后 | 完整 SessionContext（含 display_messages、recommendations） |

`SessionStore.recover()` 根据 `checkpoint_stage` 返回不同级别的恢复提示。

### 2.4 上下文感知降级

`degradation.py` 的 `fallback_text_for_failure()` 根据 `reason` 和当前 SessionContext 动态生成降级文案：

| reason | 行为 |
|--------|------|
| `llm_timeout` | 若存在关注商品则提示用户直接查看卡片，而非仅重新等待 |
| `retrieval_error` | 提示检索不稳定，但保留已知商品名供参考 |
| `llm_error` | 注入最后用户查询词和关注商品信息 |
| `contradiction_blocked` | 说明回复被拦截、建议换方式提问，保留商品上下文 |
| `hallucination_detected` | 说明内容触发保护机制，建议重新描述需求 |
| `internal_error` | 告知服务暂时不可用，对话记录已保存 |

## 3. 技术栈

| 层 | 技术 | 选型理由 |
|----|------|---------|
| **LLM Planner (JSON)** | DeepSeek v4-flash | plan_tool 用 flash 降延迟；UnifiedPlan JSON schema 固定 |
| **LLM Generate (Stream)** | DeepSeek v4-pro | 流式文本生成，高质量推荐文案 |
| **后端框架** | FastAPI + Uvicorn | 原生 async/await，WebSocket 内置 |
| **检索引擎** | rank-bm25 + sentence-transformers | BM25 中文分词 (jieba) + dense 语义融合 |
| **重排序** | CrossEncoder (bge-reranker-v2-m3) | 融合后二次精排，失败静默降级 |
| **分词** | jieba 0.42 + CJK-ASCII 边界归一化 | 中文分词标准方案 + 修复 "小米17Max" 分词断裂 |
| **数据模型** | Pydantic v2 | 全链路类型校验 + JSON Schema |
| **数据库** | SQLite (购物车/订单/会话) | 嵌入式零配置，生产可迁 PostgreSQL |
| **Android UI** | Jetpack Compose + Material3 | 声明式 UI，Compose BOM 2026.04 |
| **图片加载** | Coil 2.7 | Compose 原生支持 |
| **网络层** | OkHttp 4.12 + Retrofit 2.11 | HTTP + WebSocket |
| **公网穿透** | Cloudflare Tunnel | 真机调试零配置 |
| **测试** | pytest + JUnit + MockWebServer | 后端 ~600 单测 / Android ~180 单测 |
| **仪表盘** | Chart.js v4 (CDN) | 零依赖可视化 |

## 4. 关键调用链

```
用户消息 → WebSocket /ws/chat
  └─ ShopGuideAgent.stream_message()
      │
  [Step 1]  SessionStore.get() → SessionContext
            └─ dialog_turns.append({role: "user", ...})
            └─ checkpoint("turn_start")
  [Step 2]  yield assistant_state("thinking")  ← 立即反馈 (<1ms)
  [Step 3]  seed_constraint_state_from_plan()
            └─ 首次对话时用上一轮 RetrievalPlan 初始化约束状态
  [Step 4]  ToolPlanner.plan() → UnifiedPlan   ← LLM 调用 1 (JSON, fast model)
            └─ product_followup 类型短路 (confidence=1.0)
            └─ LLM 失败 → rule_fallback (正则兜底)
  [Step 5]  StateReducer.apply_unified(context, plan)
            └─ 将 UnifiedPlan 扁平字段写入 SessionContext
            └─ turn_index++, 约束合并, source_turns 审计日志
  [Step 6]  _dispatch_tool() 按 plan.tool 单点分发:
            ├─ product_analysis  → ProductAnalysisTool
            ├─ chitchat          → SmallTalkTool (含 BM25 top-5 商品注入)
            ├─ cart_operation    → CartTool
            ├─ product_followup  → ProductFollowupTool
            ├─ clarification     → ClarifyTool
            └─ recommend_product / compare_products / scenario_bundle
               └─ _run_retrieval_flow()
  [Step 7]  QueryBuilder.build_from_unified() → RetrievalPlan
            └─ UnifiedPlan 扁平字段直接映射为 HardConstraints + 检索关键词
  [Step 8]  AdaptiveRetriever.search_async()
            └─ HybridRetriever (BM25 + RRF 融合 + Reranker 重排)
            └─ 失败回退 BM25OnlyRetriever + 渐进放松
  [Step 9]  FactContextBuilder.build() → FactContext
            └─ prompt_block: [[product_id]] 锚点事实表
            └─ product_index: dict[pid, FactRecord]
            └─ brand_index: dict[brand, list[pid]]
  [Step 10] ConsistencyTracker.check_before_output()
            └─ Rule 3 focus drift 检测 → 拦截/放行
  [Step 11] LLM.stream_response(fact_block=...) → 流式文本  ← LLM 调用 2
            └─ AnchorValidator.stream_process()
               └─ 普通文本立即透传 + [[pid]] 微缓冲校验展开
               └─ 流结束后 deferred 裸奔名检测 + stray_warning
            └─ HallucinationChecker.verify() 价格偏差兜底
  [Step 12] product_item events + quick_actions + done
            └─ checkpoint("turn_end")
```

## 5. 目录结构

```
SoulDance/
├── client/                                  # Android 应用
│   └── app/src/main/java/com/example/shopguideagent/
│       ├── MainActivity.kt                  # 主 Activity
│       ├── navigation/AppNavGraph.kt        # 导航图
│       ├── config/
│       │   ├── AppConfig.kt                 # 后端地址配置 (tunnel 自动更新)
│       │   └── UserSession.kt               # 用户会话管理
│       ├── data/
│       │   ├── model/
│       │   │   ├── ChatMessage.kt           # 消息模型
│       │   │   ├── Product.kt               # 商品模型
│       │   │   ├── Cart.kt                  # 购物车模型
│       │   │   ├── RealtimeEvent.kt         # WebSocket 事件模型
│       │   │   ├── BundleModels.kt          # 场景搭配模型
│       │   │   └── OrderFlowState.kt        # 订单状态
│       │   └── profile/
│       │       ├── UserProfileRepository.kt # 用户画像持久化
│       │       └── UserProfileState.kt      # 画像状态
│       ├── ui/
│       │   ├── component/                   # UI 组件 (AiMessageBlock, InlineProductCard 等)
│       │   └── home/                        # 精灵空间首页 (SpriteHomeScreen, SpriteStage 等)
│       ├── vm/
│       │   ├── ChatViewModel.kt             # 聊天 ViewModel
│       │   └── CartViewModel.kt             # 购物车 ViewModel
│       └── voice/                           # 语音输入
├── server/
│   ├── requirements.txt                     # Python 依赖
│   ├── requirements-dev.txt                 # 开发依赖
│   ├── backend/app/
│   │   ├── agent.py                         # * ShopGuideAgent — 核心编排器
│   │   ├── tool_planner.py                  # * ToolPlanner — LLM 单一决策入口 → UnifiedPlan
│   │   ├── models.py                        # * 全量 Pydantic 模型 (含 UnifiedPlan, FactContext, SessionContext)
│   │   ├── fact_context.py                  # * FactContextBuilder — 事实表构建
│   │   ├── anchor_validator.py              # * AnchorValidator — 流式锚点校验 (循环状态机)
│   │   ├── consistency_tracker.py           # * ConsistencyTracker — 跨轮一致性 (3 条纯规则)
│   │   ├── hallucination_checker.py         # 价格偏差检测 (兜底层)
│   │   ├── session_store.py                 # SessionStore + 3-stage checkpoint + recover
│   │   ├── degradation.py                   # 上下文感知降级文案
│   │   ├── product_matcher.py               # * ProductMatcher — BM25 gap 置信度模糊匹配
│   │   ├── embedding_retriever.py           # BM25 + dense 检索 (_normalize_cjk_ascii 预处理)
│   │   ├── adaptive_retriever.py            # AdaptiveRetriever — 渐进放松检索入口
│   │   ├── semantic_layer.py                # rule_semantic_frame 纯规则引擎
│   │   ├── query_builder.py                 # build_from_unified / build
│   │   ├── state_reducer.py                 # apply_unified / apply / seed_constraint_state_from_plan
│   │   ├── reference_resolver.py            # ReferenceResolver — 指代消解
│   │   ├── planner_agent.py                 # 辅助函数 (_clarification_policy, _detect_category 等)
│   │   ├── llm_client.py                    # LLM 客户端 (DeepSeek + 熔断)
│   │   ├── config.py                        # 全局配置
│   │   ├── taxonomy.py                      # TaxonomyResolver — 类目匹配
│   │   ├── constraint_filter.py             # dedupe, hard_filter, canonical_brand
│   │   ├── ranker.py                        # rank_products — 硬约束过滤 + 多因素排序
│   │   ├── memory_cache.py                  # RecommendationMemoryCache / StructuredMemoryCache
│   │   ├── context_compression.py           # 上下文压缩
│   │   ├── comparison_engine.py             # ComparisonEngine — LLM 驱动商品对比
│   │   ├── comparison_presenter.py          # 对比结果格式化
│   │   ├── response_contract.py             # compose_markdown_sections, action_message
│   │   ├── feedback_store.py                # 反馈存储
│   │   ├── feedback_aggregator.py           # 反馈聚合
│   │   ├── feedback_ranker.py               # 反馈加权排序
│   │   ├── cart.py / cart_intent.py         # 购物车服务 + 意图检测
│   │   ├── order_service.py                 # 订单状态机
│   │   ├── circuit_breaker.py               # LLM 熔断器
│   │   ├── concurrency.py                   # 并发控制
│   │   ├── identity.py                      # 用户身份
│   │   ├── gateway.py                       # API 网关层
│   │   ├── observability.py                 # 可观测性
│   │   ├── trace_store.py                   # 请求追踪存储
│   │   ├── dev_console.py                   # 开发者仪表盘
│   │   ├── tts_adapter.py / stt_adapter.py  # 语音合成 / 识别适配器
│   │   ├── image_assets.py                  # 商品图片 URL 自动解析
│   │   ├── data_loader.py                   # 商品数据加载
│   │   ├── timeout_policy.py                # 超时策略 (run_with_timeout)
│   │   ├── realtime_envelope.py             # WebSocket 事件封装
│   │   ├── llm_usage.py                     # LLM 用量追踪
│   │   ├── prompt_registry.py               # Prompt 模板注册
│   │   ├── user_profile_store.py            # 用户画像持久化
│   │   ├── knowledge_base.py                # 知识库 (evidence 摘要)
│   │   ├── keywords.py                      # 关键词词典
│   │   ├── messages.py                      # 固定文案
│   │   ├── utils.py                         # 工具函数 (extract_json)
│   │   ├── tools/                           # 8 个 Tool 实现
│   │   │   ├── registry.py                  # ToolRegistry — 工具注册/分发
│   │   │   ├── base.py                      # Tool 基类
│   │   │   ├── retrieval.py                 # RetrieveProductsTool — 推荐检索
│   │   │   ├── product_analysis.py          # ProductAnalysisTool — 单品分析
│   │   │   ├── comparison.py                # CompareProductsTool — 商品对比
│   │   │   ├── followup.py                  # ProductFollowupTool — 焦点商品追问
│   │   │   ├── cart.py                      # CartTool — 购物车
│   │   │   ├── bundle.py                    # ScenarioBundleTool — 场景搭配
│   │   │   ├── small_talk.py               # SmallTalkTool — 闲聊 (含 BM25 top-5 商品注入)
│   │   │   └── clarify.py                  # ClarifyTool — 澄清
│   │   ├── rag/                             # RAG 检索与排序
│   │   │   ├── types.py                     # 共享类型
│   │   │   ├── chunking.py                  # 文本分块
│   │   │   ├── lexical_search.py            # BM25 词汇检索
│   │   │   ├── vector_search.py             # Dense 向量检索
│   │   │   ├── fusion.py                    # RRF / 加权融合
│   │   │   ├── reranker.py                  # CrossEncoder 重排序
│   │   │   └── reranker_scenarios.py        # 重排序场景
│   │   ├── prompts/v1/                      # LLM 系统提示
│   │   │   ├── tool_planner.txt             # Planner 调度规则 (含 UnifiedPlan JSON schema)
│   │   │   ├── response.txt                 # 推荐回复风格
│   │   │   ├── chitchat.txt                # 闲聊角色定位
│   │   │   ├── selection.txt                # 商品选择策略
│   │   │   ├── summary.txt                  # 对话摘要
│   │   │   └── contextual_followup.txt      # 上下文追问
│   │   └── main.py                          # FastAPI 入口 + WebSocket + REST 端点
│   ├── tests/                               # 后端测试 (~600 个)
│   └── scripts/                             # 启动/部署脚本
├── ecommerce_agent_dataset/                 # 商品数据 (100 款，含图片)
├── docs/                                    # 文档
├── deploy/                                  # 部署模板
└── data/                                    # 运行时数据 (git ignore)
```

## 6. 依赖清单

### 6.1 后端 (Python 3.13+)

```
fastapi==0.136.3          # Web 框架
uvicorn[standard]==0.48.0  # ASGI 服务器
openai==2.38.0            # LLM SDK (DeepSeek 兼容)
httpx==0.28.1             # HTTP 客户端
websockets==16.0          # WebSocket
pydantic==2.13.4          # 数据校验
numpy==2.3.5              # 矩阵运算 (向量检索)
jieba==0.42.1             # 中文分词
rank-bm25==0.2.2          # BM25 关键词检索
sentence-transformers==5.1.2  # Dense 向量编码
pytest==9.0.3             # 测试框架
pytest-asyncio==1.3.0     # 异步测试
respx>=0.22.0             # HTTP mock
python-multipart>=0.0.12  # 表单解析
```

### 6.2 Android 客户端

```
Kotlin 2.3.21                     # 编程语言
Compose BOM 2026.04.01            # Jetpack Compose 版本管理
Coil 2.7.0                        # 图片加载
OkHttp 4.12.0                     # HTTP + WebSocket 客户端
Retrofit 2.11.0                   # HTTP API 封装
minSdk 26 / targetSdk 36          # Android 兼容范围
versionCode = git rev-list --count HEAD   # 自动版本号
```

## 7. UnifiedPlan -- 统一决策载体

### 7.1 设计目标

将原来 3 次 LLM 调用（SemanticParser + IntentCompiler + PlannerAgent）的信息合并为一次 JSON completion 输出。`UnifiedPlan` 是 `models.py` 中的 Pydantic BaseModel，所有字段均设默认值——LLM 只需填充它能抽取的部分。

### 7.2 字段设计

| 类别 | 字段 | 用途 |
|------|------|------|
| **工具路由** | `tool`, `confidence` | 决定调用哪个 tool |
| **意图 + 澄清** | `need_clarification`, `clarification_question` | 是否需要向用户追问 |
| **硬约束** | `category`, `sub_category`, `price_min`, `price_max`, `include_brands`, `exclude_brands` | 检索时必须满足的条件 |
| **软偏好** | `soft_preferences` | 检索加分项 (不强制) |
| **检索参数** | `retrieval_query`, `retrieval_mode` | 给检索引擎的搜索词和模式 |
| **商品识别** | `target_product_query`, `category_hint` | 用户提到的具体商品名 / 类目线索 |
| **对比/分析/追问** | `compare_targets`, `analysis_aspect`, `followup_kind` | 对比目标 / 分析角度 / 追问类型 |
| **购物车** | `cart_action`, `cart_target_product_id`, `cart_quantity` | 购物车操作参数 |
| **否定缓存** | `denied_queries` | 已声明不存在的查询词列表 |

### 7.3 创建与消费

- **创建**: `ToolPlanner.plan()` → LLM JSON completion → `UnifiedPlan.model_validate(data)`
- **消费 (状态)**: `StateReducer.apply_unified()` → 将扁平字段写入 SessionContext
- **消费 (检索)**: `QueryBuilder.build_from_unified()` → 直接映射为 RetrievalPlan
- **消费 (路由)**: `_dispatch_tool()` → 按 `plan.tool` 分发到 8 个 tool

### 7.4 删除的模块

| 删除项 | 说明 |
|--------|------|
| `intent_compiler.py` | LLM 语义解析 + 意图编译路径完全废弃，由 UnifiedPlan 扁平字段替代 |
| `tool_plan.py` | ToolPlan / ToolPlanArgs 被 UnifiedPlan 合并，不再需要独立 schema |
| SemanticParser 类 (`semantic_layer.py`) | LLM 语义解析器删除，tool routing 由 ToolPlanner 处理 |
| PlannerAgent 类 (`planner_agent.py`) | LLM 规划器删除，保留其中的辅助函数 (_clarification_policy 等) |
| `parse_semantic_frame()` (LLM client) | LLM 客户端上的语义解析方法删除 |
| UnifiedPlan compat properties | `.intent`, `.constraint_edits`, `.cart_operation`, `.query_intent` 等向后兼容 property 全部删除 |

## 8. 事实锚定管道

### 8.1 设计理念

为解决 LLM 幻觉（虚构不存在的商品型号/价格）和前后回答矛盾，引入事实锚定管道——LLM 只能引用检索层验证过的真实商品数据。

管道将 LLM 生成过程分为三个阶段：

| 阶段 | 组件 | 时机 | 职责 |
|------|------|------|------|
| **事实注入** | FactContextBuilder | LLM 生成前 | 将检索结果组装为 `prompt_block`，注入 system prompt |
| **锚点校验** | AnchorValidator | LLM 生成中 (流式) | 逐 chunk 校验 `[[pid]]` 锚点，命中展开、未命中替换 |
| **价格审计** | HallucinationChecker | LLM 生成后 (deferred) | 检测文本中价格与 FactContext 的偏差 |

### 8.2 FactContextBuilder

在 LLM 流式生成之前，将检索结果 (`list[RankedProduct]`) 组装为 `FactContext`：

- **`prompt_block`**: 注入 LLM system prompt 末尾，列出每个商品的 `[[product_id]]`、名称、品牌、价格、核心卖点，并附带规则约束——"引用时必须使用 `[[product_id]]` 锚点格式，任何未列在此库中的商品名称视为不存在"
- **`product_index`**: `dict[product_id, FactRecord]`，供 AnchorValidator 流式校验查询
- **`brand_index`**: `dict[brand, list[product_id]]`，供 ConsistencyTracker 跨轮品牌一致性校验
- **`denied_queries`**: 由 ConsistencyTracker 提供的已声明不存在查询列表，注入 prompt 防止 LLM 绕过高亮检测

核心代码位置: `fact_context.py` → `FactContextBuilder.build(ranked, denied_queries)`

### 8.3 AnchorValidator -- 流式校验

```
LLM 逐 token 输出 (async generator)
  → 普通文本: 立即透传 (零延迟)
  → 遇到 [[ : 进入锚点缓冲 → 收集到 ]] → 查 product_index
      → 命中: 展开为 **商品名** → 立即透传
      → 未命中: 替换为「该商品」+ yield anchor_warning 事件
  → 同 chunk 内多锚点: 循环状态机处理 (while '[[' in text)
  → 跨 chunk 保护: chunk 以 '[' 结尾时缓冲到 pending，防止 '[[' 被分割
  → 流结束后: deferred 裸奔名检测 (未被 [[...]] 包裹的真实商品名 → stray_warning)
```

关键设计决策：

- **循环而非递归**: 使用 `while '[[' in text` 循环消费同一 chunk 内的多个锚点，避免递归开销
- **`[` 后缀保护**: 当 chunk 以 `[` 结尾时将其保留到 pending，防止 `[[` 被跨 chunk 分割
- **deferred 检测**: 裸奔名检测在完整的原始文本上执行（而非展开后），避免已展开的锚点干扰检测

核心代码位置: `anchor_validator.py` → `AnchorValidator.stream_process(chunks, fact_ctx)`

### 8.4 HallucinationChecker -- 价格兜底

在 AnchorValidator 流处理完成后，对流式输出收集的完整文本执行延迟的价格偏差检测：

- 用正则匹配文本中的所有 `¥xxx` / `xxx元` 价格提及
- 与 `FactContext.product_index` 中对应商品的真实价格对比
- 偏差超过 10% 则记录 `price_mismatch` 并下发给客户端

注意：AnchorValidator 已覆盖虚构 ID / 名称检测，本组件仅保留价格偏差审计。

核心代码位置: `hallucination_checker.py` → `HallucinationChecker.verify(response_text, fact_ctx)`

### 8.5 ConsistencyTracker -- 跨轮校验

3 条纯规则（不调 LLM），在每次推荐生成前执行：

| 规则 | 检查内容 | 失败处理 |
|------|---------|---------|
| **Rule 1 (Denial Cache)** | 已声明「不存在」的查询词不重新出现在后续检索中 | 注入 `denied_queries` 到 FactContext prompt，阻止 LLM 重提旧查询 |
| **Rule 2 (Price Consistency)** | 同一 `product_id` 的报价与 FactContext 一致 | 由 AnchorValidator + HallucinationChecker 双层保证 |
| **Rule 3 (Focus Drift)** | `confirmed_product_id`（用户明确关注的商品）未出现在新推荐中 | 调用被 `check_before_output` 拦截，返回 `consistency_blocked` 事件 + 降级提示 |

核心代码位置: `consistency_tracker.py` → `ConsistencyTracker.check_before_output()`

## 9. 8 个工具详解

### 9.1 工具注册与分发

`ToolRegistry` (`tools/registry.py`) 维护 `name → Tool` 的映射。`_dispatch_tool()` 按 `UnifiedPlan.tool` 单点分发：

- `product_analysis`, `chitchat`, `cart_operation`, `product_followup` → 直接调用对应 tool
- `recommend_product`, `compare_products`, `scenario_bundle` → 由 `_run_retrieval_flow()` 统一处理检索路径后分发
- `clarification` → 在 `_run_retrieval_flow()` 内部按 `plan.need_clarification` 分发

### 9.2 recommend_product -- 推荐检索

**调用链**: `_run_retrieval_flow()` → `QueryBuilder.build_from_unified()` → `AdaptiveRetriever.search_async()` → `rank_products()` → `_select_products()` (LLM product selection) → 事实锚定管道 → `_stream_recommendation_events()`

**关键流程**:

1. UnifiedPlan → RetrievalPlan (硬约束 + 软偏好 + 检索关键词)
2. AdaptiveRetriever 渐进放松检索 (Hybrid BM25+dense+RRF+Rerank → 降级 BM25 only)
3. rank_products 硬约束过滤 + 多因素排序
4. LLM product selection：从候选池中选出 top-4 并给出推荐理由
5. FactContextBuilder 构建事实表 → ConsistencyTracker 拦截检查
6. LLM 流式生成 → AnchorValidator 流式校验 → HallucinationChecker 价格兜底
7. product_item events 下发每个选中商品的卡片

### 9.3 product_analysis -- 单品分析

**调用链**: `_dispatch_tool()` → `ProductAnalysisTool.execute()`

**关键流程**:

1. 从 `UnifiedPlan.target_product_query` 提取目标商品名
2. `ProductMatcher.match()` 做 BM25 模糊匹配 (gap 置信度)
3. 命中 → 构建 `enriched_message` (注入匹配到的商品 title/price/brand/specs) → LLM 流式回答
4. 未命中 (best=None) → 如果 candidates 非空则透传给 LLM 做模糊提示；candidates 为空则走 `product_analysis_unknown` 流程

### 9.4 compare_products -- 商品对比

**调用链**: `_run_retrieval_flow()` → `CompareProductsTool.execute()` → `ComparisonEngine.compare()`

**关键流程**:

1. 解析对比目标 (用户消息中的命名商品 / 上下文事件中的 product_ids)
2. 应用硬约束过滤 (价格、品牌等)
3. `ComparisonEngine.compare()` → LLM 多维度对比 (各维度打分 + 综合结论)
4. AnchorValidator 校验对比文本中的 `[[pid]]` 锚点

### 9.5 scenario_bundle -- 场景搭配

**调用链**: `_run_retrieval_flow()` → `ScenarioBundleTool.execute()`

**关键流程**:

1. 按场景拆分为多个搭配分组 (slot)
2. 每个 slot 独立检索 → 取 top1
3. 下发 `bundle_start` → `bundle_item` (每组商品卡片) → `bundle_done`
4. AnchorValidator 校验 bundle 总结文本中的锚点

### 9.6 product_followup -- 焦点商品追问

**调用链**: `_dispatch_tool()` → `ProductFollowupTool.execute()`

**关键流程**:

1. ReferenceResolver 指代消解 → 确定焦点商品
2. 按 `UnifiedPlan.followup_kind` 分支:
   - `explain/specs/price` → 直接用焦点商品数据生成回答 (不走检索)
   - `cheaper/more_expensive/exclude_brand` → 走检索替换流 (修改硬约束后重新检索)

### 9.7 cart_operation -- 购物车操作

**调用链**: `_dispatch_tool()` → `CartTool.execute()`

**关键流程**:

1. `UnifiedPlan.cart_action` → `_normalize_cart_action()` 标准化
2. 商品识别: 从 `cart_target_product_id` / 用户消息中的商品名 / ReferenceResolver 获取
3. 执行操作 (add/remove/update_quantity/clear/checkout/get_cart)
4. 更新 `context.recent_cart_product_id` + `CartMemory`

**注意**: 购物车操作不经过 LLM 生成链路，不走事实锚定管道。

### 9.8 chitchat -- 闲聊

**调用链**: `_dispatch_tool()` → `SmallTalkTool.execute()` → `_stream_no_retrieval_events()`

**关键流程**:

1. **LLM 调用前注入商品上下文**: `_enrich_chitchat_message()` 用 BM25 retriever 取 top-5 相关商品，拼成 `[本店相关商品]` 列表注入到 LLM 的 user message 中
2. LLM 流式生成闲聊回复 (可自然提及 `[[商品名#product_id]]` 锚点)
3. **扫描 LLM 生成文本中的锚点**: `_extract_anchor_product_ids()` → 查 product_map → 下发真实 `product_item` 事件

此设计使 chitchat 既能共情回复又能自然嵌入真实商品推荐，零额外 LLM 调用。

### 9.9 clarification -- 澄清

**调用链**: `_dispatch_tool()` (在 `_run_retrieval_flow` 内部) → `ClarifyTool.execute()`

**关键流程**:

1. 生成澄清问题文本 + `clarification_request` 事件 (含选项)
2. `_remember_pending_clarification()` 将澄清状态写入 SessionContext
3. 下一轮用户回答时，`_build_pending_recovery_events()` 匹配澄清选项并恢复约束

## 10. 关键组件补充说明

### 10.1 ProductMatcher -- BM25 gap 置信度模糊匹配

复用检索层已有的 BM25 分词索引。用户说「华为 Pura 70 Pro」、「小棕瓶」、「雀巢咖啡」等简称时，用同一套 retriever 做 `search(query, top_k=5)`。

**核心设计**: 不再用绝对 score 判断，改用 **top1-vs-top2 的归一化分数差 (gap)** 作为置信度信号：

| 查询 | top1 score | top2 score | gap | 判定 |
|------|-----------|-----------|-----|------|
| 雀巢咖啡 | 1.0 | 0.0 | **1.0** | 明确命中 |
| 华为 Pura 70 | 1.0 | 0.62 | **0.38** | 明确命中 |
| 小米 17 | 1.0 | 0.99 | **0.01** | 模糊，best=None |
| 完全编造 | 1.0 | 0.82 | **0.18** | 模糊，best=None |

关键设计：因为 BM25 的归一化只依赖当前 query 自己的 max/min，top1 始终是 1.0——绝对分数无法区分强弱匹配。但 gap 反映的是「top1 到底比其他候选强多少」——这是一个相对信号，不受归一化影响。

### 10.2 CJK-ASCII 分词边界归一化

**问题**: jieba 分词把「小米17Max」切成 `['小米', '17Max']`，而数据库标题「小米 17 Max」切成 `['小米', '17', 'Max']`。由于「17Max」作为一个整体 token 无法匹配到分别独立的「17」和「Max」，BM25 匹配失败。

**修复**: `EmbeddingRetriever._tokenize()` 中增加 `_normalize_cjk_ascii()` 预处理：

1. **CJK-ASCII 边界插入空格**: `小米17` → `小米 17`
2. **数字-字母边界插入空格**: `17Max` → `17 Max`

因为检索索引构建时也经过同一 `_tokenize()`，查询端和文档端分词完全对称，BM25 匹配正确。

### 10.3 ToolPlanner -- LLM 优先工具调度器

**设计原则**:
- LLM 输出 ToolPlan JSON 决定调什么工具 + 关键参数
- 规则只在 2 处保留:
  1. `product_followup` 类型的 request 直接固定 `tool="product_followup"`
  2. LLM 调用失败时的 `_rule_fallback()` 兜底 (正则匹配 cart/compare 信号，默认 chitchat)
- 不再前置 `rule_semantic_frame` / `IntentCompiler` 那一套规则栈

`_context_payload()` 将当前 SessionContext 的关键信息 (has_focus_product, focus_product_id, last_product_ids, recent_cart_product_id) 注入 LLM prompt，让 LLM 做上下文感知的工具选择。

### 10.4 rule_semantic_frame -- 纯规则引擎兜底

`rule_semantic_frame()` 在以下场景使用：

1. `agent.plan()` (旧路径兼容)
2. `agent.compile_intent()` (意图编译 API)
3. `agent._stream_followup()` (旧 followup 路径)
4. LLM 失败时 `_rule_fallback()` 作为后备

直接返回 `UnifiedPlan`（Stage 2 扁平字段），通过正则 + 词典做 cart 检测、对比检测、闲聊检测、价格抽取、品牌抽取、软偏好抽取。

### 10.5 StateReducer -- 状态归约

每轮对话调用一次，将 `UnifiedPlan` 的决策信息写入 SessionContext：

`apply_unified()`:
- `turn_index++` 递增轮次
- 记录 `last_intent = plan.tool`
- 合并硬约束 (category, sub_category, price_min/max, include/exclude_brands)
- 合并软偏好 (soft_preferences 字典)
- 记录 `source_turns` 审计日志
- 同步 `_sync_legacy_context()` (将硬/软约束写入 global_profile)

### 10.6 指代消解 (ReferenceResolver)

`reference_resolver.py` 中的 `ReferenceResolver` 解决多轮对话中的「这个/刚才那个/它/前面那个」等指代词解析：

1. `focus_product` (当前焦点商品) →
2. `last_recommendations` 中 role=primary 的主推 →
3. `recent_cart_product_id` →
4. `last_product_ids[-1]`

每一步都有明确的 fallback 逻辑，不会凭空编造。

长会话锚点持久化：首轮品牌/类目/product_ids 存储为 `reference_anchors`，当用户跨多轮后说「回到第一轮那个」，触发 `anchor_reference → first_turn` 解析。

## 11. 配置说明

### 11.1 LLM Provider

仓库根目录 `.env`：

```bash
LLM_PROVIDER=deepseek                  # LLM 提供商
LLM_API_KEY=sk-xxx                     # API Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro             # 流式生成用
LLM_FAST_MODEL=deepseek-v4-flash      # plan_tool JSON 用 (更快)
LLM_REASONING_EFFORT=high             # 推理深度
```

### 11.2 后端

```bash
HOST=0.0.0.0 PORT=8000
RERANK_ENABLED=true                   # CrossEncoder 重排
USE_EMBEDDING=true                    # dense 向量检索
TTS_ENABLED=false                     # 语音合成
STT_ENABLED=false                     # 语音识别
SHOPGUIDE_DATABASE_URL=               # SQLite 路径 (默认 data/shopguide.db)
```

### 11.3 Android

`client/.../config/AppConfig.kt`：

```kotlin
const val BASE_HTTP_URL = "https://xxx.trycloudflare.com/"
const val BASE_WS_URL = "wss://xxx.trycloudflare.com"
const val WS_CHAT_PATH = "/ws/chat"
```

编译时 Gradle 脚本 (`ensure_tunnel.sh`) 自动检测 Cloudflare tunnel 可用性并更新 URL。也可 `SKIP_TUNNEL_CHECK=true` 跳过。

### 11.4 版本号

`versionCode` / `versionName` 基于 `git rev-list --count HEAD` 自动生成。
