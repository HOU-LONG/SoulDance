# SoulDance — 灵舞 — 设计文档

> 版本：v2.1 架构精简版（2026-06-30）
> 本文档描述当前代码库的实际结构，适用于需要理解系统全貌、定位模块或进行二次开发的读者。

## 1. 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      Android 客户端                           │
│  Jetpack Compose + Material3 + Coil + OkHttp                 │
│  - AiMessageBlock 段落-卡片交替渲染                            │
│  - WebSocket 实时流式接收 + 精灵空间首页联动                     │
│  - ProductDetailBottomSheet 锚点/卡片统一入口                  │
└───────────────┬─────────────────────────────────────────────┘
                │ HTTPS + WebSocket
                │ (Cloudflare Tunnel 公网穿透)
┌───────────────▼─────────────────────────────────────────────┐
│                FastAPI 后端 (Python 3.12+)                    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ planning/tool_planner.py → UnifiedPlan                 │   │
│  │ 单次 LLM 调用 (JSON completion, fast model)            │   │
│  │ 扁平字段携带全部决策信息：                              │   │
│  │ 工具路由 + 意图 + 硬约束 + 软偏好 + 检索参数             │   │
│  └───────────────┬──────────────────────────────────────┘   │
│                  │ planning/state_reducer.apply_unified()    │
│                  │ core/agent.py _dispatch_tool() 单点分发    │
│  ┌───────────────▼──────────────────────────────────────┐   │
│  │ pipeline/ 事实锚定管道 (Fact-Grounded Pipeline)         │   │
│  │ pipeline/fact_context.py      → 构建 [[pid]] 事实表     │   │
│  │ pipeline/anchor_validator.py  → 流式锚点校验 + 展开      │   │
│  │ pipeline/hallucination_checker.py → 价格偏差兜底        │   │
│  │ pipeline/consistency_tracker.py → 跨轮 denial/focus     │   │
│  │ pipeline/degradation.py       → 上下文感知降级文案       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ tools/ 8 个 Tool 实现（按 UnifiedPlan.tool 单点分发）     │   │
│  │ retrieval.py   product_analysis.py   small_talk.py    │   │
│  │ comparison.py  bundle.py             cart.py          │   │
│  │ followup.py    clarify.py                             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ retrieval/ + rag/ 检索层                               │   │
│  │ retrieval/adaptive_retriever.py (BM25 + dense + RRF)  │   │
│  │ rag/lexical_search.py + rag/vector_search.py          │   │
│  │ rag/reranker.py (CrossEncoder 精排)                    │   │
│  │ retrieval/product_matcher.py (BM25 gap 置信度)         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ services/session_store.py + 3-stage Checkpoint         │   │
│  │ db/ SQLAlchemy 持久化 + repositories/ 数据访问层        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 2. 架构概述

### 2.1 整体设计

SoulDance 后端采用 **LLM 优先的 Agent 架构**：用户消息进，结构化事件流（`text_delta` / `product_item` / `quick_actions` / `cart_update` 等）出。核心设计原则：

- **单次 LLM 决策入口**：`planning/tool_planner.py` 一次 JSON completion 输出 `UnifiedPlan`，包含工具路由、意图标记、硬约束、软偏好、检索参数等全部决策信息。后续不再有额外的 LLM 意图解析调用。
- **事实锚定管道**：在 LLM 流式生成前注入事实表（`FactContext`），生成中以 `AnchorValidator` 逐 chunk 校验锚点，生成后用 `HallucinationChecker` 做价格偏差兜底。LLM 只能引用检索层验证过的真实商品数据。
- **CJK-ASCII 分词边界归一化**：修复 jieba 对 "小米17Max" 等的分词断裂问题，在 BM25 分词前自动在 CJK/数字/字母边界插入空格。
- **3 阶段 Session Checkpoint**：`turn_start` / `post_retrieve` / `turn_end` 三个时机自动保存，支持异常恢复。
- **上下文感知降级**：`pipeline/degradation.py` 根据失败原因和当前 `SessionContext` 动态生成降级文案，而非统一模板。
- **工具错误分类与阶段超时**：v2.1 新增 `services/timeout_policy.py` 阶段级超时和 `services/concurrency.py` LLM 信号量，避免单点慢请求拖垮整体服务；工具错误按阶段分类后进入对应降级分支。

### 2.2 LLM 调用次数

每轮对话 **最多 2 次 LLM 调用**：

| 调用 | 时机 | 模型 | 输出 |
|------|------|------|------|
| LLM 调用 1 | `_do_stream_message` 入口 | fast model (deepseek-v4-flash) | JSON → UnifiedPlan |
| LLM 调用 2 | 检索完成后 | pro model (deepseek-v4-pro) | 流式文本生成 |

如果 `UnifiedPlan.tool` 为 `cart_operation` 或 `clarification`，则跳过 LLM 调用 2。

### 2.3 3 阶段 Session Checkpoint

| 阶段 | 触发点 | 保存内容 |
|------|--------|---------|
| **turn_start** | `stream_message` 入口，追加用户消息后 | `dialog_turns` 已包含本次用户消息 |
| **post_retrieve** | 检索完成、`RetrievalPlan` 构建后 | `context.last_plan` 已写入 |
| **turn_end** | 流结束后 | 完整 `SessionContext`（含 `display_messages`、`recommendations`） |

`services/session_store.py` 的 `SessionStore.recover()` 根据 `checkpoint_stage` 返回不同级别的恢复提示。

### 2.4 上下文感知降级

`pipeline/degradation.py` 的 `fallback_text_for_failure()` 根据 `reason` 和当前 `SessionContext` 动态生成降级文案：

| reason | 行为 |
|--------|------|
| `llm_timeout` | 若存在关注商品则提示用户直接查看卡片，而非仅重新等待 |
| `retrieval_error` | 提示检索不稳定，但保留已知商品名供参考 |
| `llm_error` | 注入最后用户查询词和关注商品信息 |
| `contradiction_blocked` | 说明回复被拦截、建议换方式提问，保留商品上下文 |
| `hallucination_detected` | 说明内容触发保护机制，建议重新描述需求 |
| `internal_error` | 告知服务暂时不可用，对话记录已保存 |

### 2.5 阶段超时与并发控制（v2.1 新增）

- **阶段超时**：`services/timeout_policy.py` 为 plan、retrieve、generate、tool 等阶段设置独立超时，避免某一阶段无限阻塞。
- **LLM 信号量**：`services/concurrency.py` 限制同时进入 LLM 调用的请求数，防止突发流量导致内存或连接耗尽。
- **工具错误分类**：工具执行异常按 `plan` / `retrieve` / `generate` / `tool` / `internal` 分类，降级文案和恢复策略对应到具体阶段。

## 3. 技术栈

| 层 | 技术 | 选型理由 |
|----|------|---------|
| **LLM Planner (JSON)** | DeepSeek v4-flash | plan_tool 用 flash 降延迟；UnifiedPlan JSON schema 固定 |
| **LLM Generate (Stream)** | DeepSeek v4-pro | 流式文本生成，高质量推荐文案 |
| **后端框架** | FastAPI + Uvicorn | 原生 async/await，WebSocket 内置 |
| **数据库** | SQLite + SQLAlchemy (Alembic 迁移就绪) | 嵌入式零配置，生产可迁 PostgreSQL |
| **数据访问层** | repositories/ 模式 | 购物车/会话/订单/反馈/画像按领域隔离 |
| **检索引擎** | rank-bm25 + sentence-transformers | BM25 中文分词 (jieba) + dense 语义融合 |
| **重排序** | CrossEncoder (bge-reranker-v2-m3) | 融合后二次精排，失败静默降级 |
| **分词** | jieba 0.42 + CJK-ASCII 边界归一化 | 中文分词标准方案 + 修复 "小米17Max" 分词断裂 |
| **数据模型** | Pydantic v2 | 全链路类型校验 + JSON Schema |
| **Android UI** | Jetpack Compose + Material3 | 声明式 UI，Compose BOM 2026.04 |
| **图片加载** | Coil 2.7 | Compose 原生支持 |
| **网络层** | OkHttp 4.12 + Retrofit 2.11 | HTTP + WebSocket |
| **公网穿透** | Cloudflare Tunnel | 真机调试零配置 |
| **测试** | pytest + JUnit + MockWebServer | 后端 ~600 单测 / Android ~180 单测 |
| **仪表盘** | Chart.js v4 (CDN) | 零依赖可视化 |

## 4. 目录结构

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
│       │   ├── model/                       # 消息、商品、购物车、事件模型
│       │   └── profile/                     # 用户画像持久化
│       ├── ui/                              # UI 组件 + 精灵空间首页
│       ├── vm/                              # ChatViewModel / CartViewModel
│       └── voice/                           # 语音输入
├── server/
│   ├── requirements.txt                     # Python 依赖
│   ├── requirements-dev.txt                 # 开发依赖
│   ├── alembic/                             # 数据库迁移
│   ├── backend/app/                         # 后端主包（按职责划分为多个子目录）
│   │   ├── adapters/                        # 外部服务适配器
│   │   │   ├── image_assets.py              # 商品图片 URL 自动解析
│   │   │   ├── stt_adapter.py               # 语音识别适配器
│   │   │   └── tts_adapter.py               # 语音合成适配器
│   │   ├── comparison/                      # 商品对比
│   │   │   ├── comparison_engine.py         # LLM 驱动多维度对比
│   │   │   └── comparison_presenter.py      # 对比结果格式化
│   │   ├── core/                            # 核心编排
│   │   │   └── agent.py                     # ShopGuideAgent — 主入口/编排器
│   │   ├── db/                              # 数据库层
│   │   │   ├── base.py                      # SQLAlchemy Base
│   │   │   ├── engine.py                    # 引擎与 session 工厂
│   │   │   ├── models.py                    # 数据库模型
│   │   │   └── seed.py                      # 数据种子
│   │   ├── eval/                            # 评测框架
│   │   │   ├── long_session_*.py            # 长会话评测
│   │   │   ├── retrieval_ablation.py        # 检索消融
│   │   │   └── prompts/                     # 评测用 prompt
│   │   ├── feedback/                        # 反馈闭环
│   │   │   ├── feedback_store.py            # 反馈存储
│   │   │   ├── feedback_aggregator.py       # 反馈聚合
│   │   │   └── feedback_ranker.py           # 反馈加权排序
│   │   ├── memory/                          # 记忆与压缩
│   │   │   ├── context_compression.py       # 上下文压缩
│   │   │   └── memory_cache.py              # 推荐记忆缓存
│   │   ├── pipeline/                        # 事实锚定管道 + 降级
│   │   │   ├── anchor_validator.py          # 流式锚点校验
│   │   │   ├── consistency_tracker.py       # 跨轮一致性
│   │   │   ├── degradation.py               # 上下文感知降级
│   │   │   ├── fact_context.py              # 事实表构建
│   │   │   └── hallucination_checker.py     # 价格偏差兜底
│   │   ├── planning/                        # 规划与状态
│   │   │   ├── constraint_filter.py         # 约束过滤/去重
│   │   │   ├── planner_agent.py             # Planner 辅助函数
│   │   │   ├── query_builder.py             # 从 UnifiedPlan 构建检索计划
│   │   │   ├── semantic_layer.py            # 纯规则语义兜底
│   │   │   ├── state_reducer.py             # UnifiedPlan → SessionContext
│   │   │   └── tool_planner.py              # ToolPlanner — LLM 单一决策入口
│   │   ├── prompts/v1/                      # LLM 系统提示
│   │   │   ├── tool_planner.txt             # Planner JSON schema 与调度规则
│   │   │   ├── response.txt                 # 推荐回复风格
│   │   │   ├── chitchat.txt                 # 闲聊角色定位
│   │   │   ├── selection.txt                # 商品选择策略
│   │   │   ├── summary.txt                  # 对话摘要
│   │   │   └── contextual_followup.txt      # 上下文追问
│   │   ├── rag/                             # RAG 检索与排序
│   │   │   ├── types.py                     # 共享类型
│   │   │   ├── chunking.py                  # 文本分块
│   │   │   ├── lexical_search.py            # BM25 词汇检索
│   │   │   ├── vector_search.py             # Dense 向量检索
│   │   │   ├── fusion.py                    # RRF / 加权融合
│   │   │   ├── reranker.py                  # CrossEncoder 重排序
│   │   │   └── reranker_scenarios.py        # 重排序场景
│   │   ├── repositories/                    # 数据访问层
│   │   │   ├── cart_repository.py
│   │   │   ├── feedback_repository.py
│   │   │   ├── order_repository.py
│   │   │   ├── profile_repository.py
│   │   │   └── session_repository.py
│   │   ├── retrieval/                       # 检索编排
│   │   │   ├── adaptive_retriever.py        # 渐进放松检索入口
│   │   │   ├── embedding_retriever.py       # BM25 + dense + CJK-ASCII 归一化
│   │   │   ├── knowledge_base.py            # 知识库 (evidence 摘要)
│   │   │   ├── product_matcher.py           # BM25 gap 置信度模糊匹配
│   │   │   ├── ranker.py                    # 硬约束过滤 + 多因素排序
│   │   │   └── taxonomy.py                  # 类目匹配
│   │   ├── services/                        # 业务服务与基础设施
│   │   │   ├── cart.py / cart_intent.py     # 购物车服务 + 意图检测
│   │   │   ├── circuit_breaker.py           # LLM 熔断器
│   │   │   ├── concurrency.py               # LLM 信号量/并发控制 (v2.1)
│   │   │   ├── identity.py                  # 用户身份
│   │   │   ├── llm_client.py                # LLM 客户端
│   │   │   ├── llm_usage.py                 # LLM 用量追踪
│   │   │   ├── order_service.py             # 订单状态机
│   │   │   ├── realtime_envelope.py         # WebSocket 事件封装
│   │   │   ├── reference_resolver.py        # 指代消解
│   │   │   ├── session_store.py             # SessionStore + checkpoint/recover
│   │   │   └── timeout_policy.py            # 阶段超时 (v2.1)
│   │   ├── tools/                           # 8 个 Tool 实现
│   │   │   ├── registry.py                  # ToolRegistry — 工具注册/分发
│   │   │   ├── base.py                      # Tool 协议
│   │   │   ├── retrieval.py                 # RetrieveProductsTool — 推荐检索
│   │   │   ├── product_analysis.py          # ProductAnalysisTool — 单品分析
│   │   │   ├── comparison.py                # CompareProductsTool — 商品对比
│   │   │   ├── followup.py                  # ProductFollowupTool — 焦点商品追问
│   │   │   ├── cart.py                      # CartTool — 购物车
│   │   │   ├── bundle.py                    # ScenarioBundleTool — 场景搭配
│   │   │   ├── small_talk.py                # SmallTalkTool — 闲聊
│   │   │   └── clarify.py                   # ClarifyTool — 澄清
│   │   ├── config.py                        # 全局配置
│   │   ├── data_loader.py                   # 商品数据加载
│   │   ├── dev_console.py                   # 开发者仪表盘
│   │   ├── gateway.py                       # API 网关层
│   │   ├── keywords.py                      # 关键词词典
│   │   ├── main.py                          # FastAPI 入口 + WebSocket + REST
│   │   ├── messages.py                      # 固定文案
│   │   ├── models.py                        # 全量 Pydantic 模型
│   │   ├── observability.py                 # 可观测性
│   │   ├── prompt_registry.py               # Prompt 模板注册
│   │   ├── response_contract.py             # compose_markdown_sections 等
│   │   ├── trace_store.py                   # 请求追踪存储
│   │   ├── user_profile_store.py            # 用户画像持久化
│   │   └── utils.py                         # 工具函数
│   ├── tests/                               # 后端测试
│   └── scripts/                             # 启动/部署脚本
├── ecommerce_agent_dataset/                 # 商品数据 (100 款，含图片)
├── docs/                                    # 文档
├── deploy/                                  # 部署模板
└── data/                                    # 运行时数据 (git ignore)
```

## 5. 关键调用链

```
用户消息 → WebSocket /ws/chat
  └─ core/agent.py ShopGuideAgent.stream_message()
      │
  [Step 1]  services/session_store.py SessionStore.get() → SessionContext
            └─ dialog_turns.append({role: "user", ...})
            └─ checkpoint("turn_start")
  [Step 2]  yield assistant_state("thinking")  ← 立即反馈 (<1ms)
  [Step 3]  planning/state_reducer.py seed_constraint_state_from_plan()
            └─ 首次对话时用上一轮 RetrievalPlan 初始化约束状态
  [Step 4]  planning/tool_planner.py ToolPlanner.plan() → UnifiedPlan
            └─ product_followup 类型短路 (confidence=1.0)
            └─ LLM 失败 → planning/semantic_layer.py _rule_fallback() 兜底
  [Step 5]  planning/state_reducer.py StateReducer.apply_unified()
            └─ 将 UnifiedPlan 扁平字段写入 SessionContext
            └─ turn_index++, 约束合并, source_turns 审计日志
  [Step 6]  core/agent.py _dispatch_tool() 按 plan.tool 单点分发:
            ├─ product_analysis  → tools/product_analysis.py ProductAnalysisTool
            ├─ chitchat          → tools/small_talk.py SmallTalkTool
            ├─ cart_operation    → tools/cart.py CartTool
            ├─ product_followup  → tools/followup.py ProductFollowupTool
            ├─ clarification     → tools/clarify.py ClarifyTool
            └─ recommend_product / compare_products / scenario_bundle
               └─ _run_retrieval_flow()
  [Step 7]  planning/query_builder.py QueryBuilder.build_from_unified() → RetrievalPlan
            └─ UnifiedPlan 扁平字段直接映射为 HardConstraints + 检索关键词
  [Step 8]  retrieval/adaptive_retriever.py AdaptiveRetriever.search_async()
            └─ retrieval/embedding_retriever.py HybridRetriever
            └─ rag/lexical_search.py + rag/vector_search.py + rag/fusion.py
            └─ rag/reranker.py CrossEncoder 重排
            └─ 失败回退 BM25OnlyRetriever + 渐进放松
  [Step 9]  pipeline/fact_context.py FactContextBuilder.build() → FactContext
            └─ prompt_block: [[product_id]] 锚点事实表
            └─ product_index: dict[pid, FactRecord]
            └─ brand_index: dict[brand, list[pid]]
  [Step 10] pipeline/consistency_tracker.py ConsistencyTracker.check_before_output()
            └─ Rule 3 focus drift 检测 → 拦截/放行
  [Step 11] services/llm_client.py LLM.stream_response(fact_block=...) → 流式文本
            └─ pipeline/anchor_validator.py AnchorValidator.stream_process()
               └─ 普通文本立即透传 + [[pid]] 微缓冲校验展开
               └─ 流结束后 deferred 裸奔名检测 + stray_warning
            └─ pipeline/hallucination_checker.py HallucinationChecker.verify() 价格兜底
  [Step 12] product_item events + quick_actions + done
            └─ checkpoint("turn_end")
```

## 6. 依赖清单

### 6.1 后端 (Python 3.12+)

```
fastapi==0.136.3          # Web 框架
uvicorn[standard]==0.48.0  # ASGI 服务器
openai==2.38.0            # LLM SDK (DeepSeek 兼容)
httpx==0.28.1             # HTTP 客户端
websockets==16.0          # WebSocket
pydantic==2.13.4          # 数据校验
sqlalchemy==2.0.40        # ORM
alembic==1.15.0           # 数据库迁移
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

## 7. UnifiedPlan — 统一决策载体

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

- **创建**: `planning/tool_planner.py ToolPlanner.plan()` → LLM JSON completion → `UnifiedPlan.model_validate(data)`
- **消费 (状态)**: `planning/state_reducer.py StateReducer.apply_unified()` → 将扁平字段写入 SessionContext
- **消费 (检索)**: `planning/query_builder.py QueryBuilder.build_from_unified()` → 直接映射为 RetrievalPlan
- **消费 (路由)**: `core/agent.py _dispatch_tool()` → 按 `plan.tool` 分发到 8 个 tool

### 7.4 v2.1 删除的模块

| 删除项 | 说明 |
|--------|------|
| `planning/tool_plan.py` | ToolPlan / ToolPlanArgs 被 UnifiedPlan 合并，不再需要独立 schema |
| `planning/intent_compiler.py` | LLM 语义解析 + 意图编译路径完全废弃，由 UnifiedPlan 扁平字段替代 |
| `planning/semantic_layer.py` SemanticParser/PlannerAgent 类 | 旧意图解析/规划类删除，保留纯规则函数 |
| `services/llm_client.py` `parse_semantic_frame()` | LLM 客户端上的语义解析方法删除 |
| `models.py` UnifiedPlan 兼容属性 | `.intent` / `.cart_operation` / `.constraint_edits` / `.query_intent` 等向后兼容 property 全部删除 |
| `planning/state_reducer.py` `_merge_tool_plan_into_ir()` | 过渡期 workaround 删除 |

## 8. 事实锚定管道

### 8.1 设计理念

为解决 LLM 幻觉（虚构不存在的商品型号/价格）和前后回答矛盾，引入事实锚定管道——LLM 只能引用检索层验证过的真实商品数据。

管道将 LLM 生成过程分为三个阶段：

| 阶段 | 组件 | 时机 | 职责 |
|------|------|------|------|
| **事实注入** | pipeline/fact_context.py FactContextBuilder | LLM 生成前 | 将检索结果组装为 `prompt_block`，注入 system prompt |
| **锚点校验** | pipeline/anchor_validator.py AnchorValidator | LLM 生成中 (流式) | 逐 chunk 校验 `[[product_id]]` 锚点，命中展开、未命中替换 |
| **价格审计** | pipeline/hallucination_checker.py HallucinationChecker | LLM 生成后 (deferred) | 检测文本中价格与 FactContext 的偏差 |

### 8.2 FactContextBuilder

在 LLM 流式生成之前，将检索结果 (`list[RankedProduct]`) 组装为 `FactContext`：

- **`prompt_block`**: 注入 LLM system prompt 末尾，列出每个商品的 `[[product_id]]`、名称、品牌、价格、核心卖点，并附带规则约束——"引用时必须使用 `[[product_id]]` 锚点格式，任何未列在此库中的商品名称视为不存在"
- **`product_index`**: `dict[product_id, FactRecord]`，供 AnchorValidator 流式校验查询
- **`brand_index`**: `dict[brand, list[product_id]]`，供 ConsistencyTracker 跨轮品牌一致性校验
- **`denied_queries`**: 由 ConsistencyTracker 提供的已声明不存在查询列表，注入 prompt 防止 LLM 绕过高亮检测

核心代码位置: `pipeline/fact_context.py` → `FactContextBuilder.build(ranked, denied_queries)`

### 8.3 AnchorValidator — 流式校验

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

核心代码位置: `pipeline/anchor_validator.py` → `AnchorValidator.stream_process(chunks, fact_ctx)`

### 8.4 HallucinationChecker — 价格兜底

在 AnchorValidator 流处理完成后，对流式输出收集的完整文本执行延迟的价格偏差检测：

- 用正则匹配文本中的所有 `¥xxx` / `xxx元` 价格提及
- 与 `FactContext.product_index` 中对应商品的真实价格对比
- 偏差超过 10% 则记录 `price_mismatch` 并下发给客户端

注意：AnchorValidator 已覆盖虚构 ID / 名称检测，本组件仅保留价格偏差审计。

核心代码位置: `pipeline/hallucination_checker.py` → `HallucinationChecker.verify(response_text, fact_ctx)`

### 8.5 ConsistencyTracker — 跨轮校验

3 条纯规则（不调 LLM），在每次推荐生成前执行：

| 规则 | 检查内容 | 失败处理 |
|------|---------|---------|
| **Rule 1 (Denial Cache)** | 已声明「不存在」的查询词不重新出现在后续检索中 | 注入 `denied_queries` 到 FactContext prompt，阻止 LLM 重提旧查询 |
| **Rule 2 (Price Consistency)** | 同一 `product_id` 的报价与 FactContext 一致 | 由 AnchorValidator + HallucinationChecker 双层保证 |
| **Rule 3 (Focus Drift)** | `confirmed_product_id`（用户明确关注的商品）未出现在新推荐中 | 调用被 `check_before_output` 拦截，返回 `consistency_blocked` 事件 + 降级提示 |

核心代码位置: `pipeline/consistency_tracker.py` → `ConsistencyTracker.check_before_output()`

## 9. 8 个工具详解

### 9.1 工具注册与分发

`tools/registry.py` 的 `ToolRegistry` 维护 `name → Tool` 的映射。`core/agent.py` 的 `_dispatch_tool()` 按 `UnifiedPlan.tool` 单点分发：

- `product_analysis`, `chitchat`, `cart_operation`, `product_followup` → 直接调用对应 tool
- `recommend_product`, `compare_products`, `scenario_bundle` → 由 `_run_retrieval_flow()` 统一处理检索路径后分发
- `clarification` → 在 `_run_retrieval_flow()` 内部按 `plan.need_clarification` 分发

### 9.2 recommend_product — 推荐检索

**调用链**: `_run_retrieval_flow()` → `planning/query_builder.py QueryBuilder.build_from_unified()` → `retrieval/adaptive_retriever.py AdaptiveRetriever.search_async()` → `retrieval/ranker.py rank_products()` → `_select_products()` (LLM product selection) → 事实锚定管道 → `_stream_recommendation_events()`

**关键流程**:

1. UnifiedPlan → RetrievalPlan (硬约束 + 软偏好 + 检索关键词)
2. AdaptiveRetriever 渐进放松检索 (Hybrid BM25+dense+RRF+Rerank → 降级 BM25 only)
3. `rank_products` 硬约束过滤 + 多因素排序
4. LLM product selection：从候选池中选出 top-4 并给出推荐理由
5. `pipeline/fact_context.py` 构建事实表 → `pipeline/consistency_tracker.py` 拦截检查
6. LLM 流式生成 → AnchorValidator 流式校验 → HallucinationChecker 价格兜底
7. `product_item` events 下发每个选中商品的卡片

### 9.3 product_analysis — 单品分析

**调用链**: `_dispatch_tool()` → `tools/product_analysis.py ProductAnalysisTool.execute()`

**关键流程**:

1. 从 `UnifiedPlan.target_product_query` 提取目标商品名
2. `retrieval/product_matcher.py ProductMatcher.match()` 做 BM25 模糊匹配 (gap 置信度)
3. 命中 → 构建 `enriched_message` (注入匹配到的商品 title/price/brand/specs) → LLM 流式回答
4. 未命中 (best=None) → 如果 candidates 非空则透传给 LLM 做模糊提示；candidates 为空则走 `product_analysis_unknown` 流程

### 9.4 compare_products — 商品对比

**调用链**: `_run_retrieval_flow()` → `tools/comparison.py CompareProductsTool.execute()` → `comparison/comparison_engine.py ComparisonEngine.compare()`

**关键流程**:

1. 解析对比目标 (用户消息中的命名商品 / 上下文事件中的 product_ids)
2. 应用硬约束过滤 (价格、品牌等)
3. `ComparisonEngine.compare()` → LLM 多维度对比 (各维度打分 + 综合结论)
4. AnchorValidator 校验对比文本中的 `[[pid]]` 锚点

### 9.5 scenario_bundle — 场景搭配

**调用链**: `_run_retrieval_flow()` → `tools/bundle.py ScenarioBundleTool.execute()`

**关键流程**:

1. 按场景拆分为多个搭配分组 (slot)
2. 每个 slot 独立检索 → 取 top1
3. 下发 `bundle_start` → `bundle_item` (每组商品卡片) → `bundle_done`
4. AnchorValidator 校验 bundle 总结文本中的锚点

### 9.6 product_followup — 焦点商品追问

**调用链**: `_dispatch_tool()` → `tools/followup.py ProductFollowupTool.execute()`

**关键流程**:

1. `services/reference_resolver.py ReferenceResolver` 指代消解 → 确定焦点商品
2. 按 `UnifiedPlan.followup_kind` 分支:
   - `explain/specs/price` → 直接用焦点商品数据生成回答 (不走检索)
   - `cheaper/more_expensive/exclude_brand` → 走检索替换流 (修改硬约束后重新检索)

### 9.7 cart_operation — 购物车操作

**调用链**: `_dispatch_tool()` → `tools/cart.py CartTool.execute()`

**关键流程**:

1. `UnifiedPlan.cart_action` → `_normalize_cart_action()` 标准化
2. 商品识别: 从 `cart_target_product_id` / 用户消息中的商品名 / ReferenceResolver 获取
3. 执行操作 (`add/remove/update_quantity/clear/checkout/get_cart`)
4. 更新 `context.recent_cart_product_id` + `CartMemory`
5. 通过 `repositories/cart_repository.py` 持久化，必要时经 `services/order_service.py` 进入订单状态机

**注意**: 购物车操作不经过 LLM 生成链路，不走事实锚定管道。

### 9.8 chitchat — 闲聊

**调用链**: `_dispatch_tool()` → `tools/small_talk.py SmallTalkTool.execute()` → `_stream_no_retrieval_events()`

**关键流程**:

1. **LLM 调用前注入商品上下文**: `_enrich_chitchat_message()` 用 BM25 retriever 取 top-5 相关商品，拼成 `[本店相关商品]` 列表注入到 LLM 的 user message 中
2. LLM 流式生成闲聊回复 (可自然提及 `[[商品名#product_id]]` 锚点)
3. **扫描 LLM 生成文本中的锚点**: `_extract_anchor_product_ids()` → 查 product_map → 下发真实 `product_item` 事件

此设计使 chitchat 既能共情回复又能自然嵌入真实商品推荐，零额外 LLM 调用。

### 9.9 clarification — 澄清

**调用链**: `_dispatch_tool()` (在 `_run_retrieval_flow` 内部) → `tools/clarify.py ClarifyTool.execute()`

**关键流程**:

1. 生成澄清问题文本 + `clarification_request` 事件 (含选项)
2. `_remember_pending_clarification()` 将澄清状态写入 SessionContext
3. 下一轮用户回答时，`_build_pending_recovery_events()` 匹配澄清选项并恢复约束

## 10. 关键组件补充说明

### 10.1 ProductMatcher — BM25 gap 置信度模糊匹配

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

**修复**: `retrieval/embedding_retriever.py` 中增加 `_normalize_cjk_ascii()` 预处理：

1. **CJK-ASCII 边界插入空格**: `小米17` → `小米 17`
2. **数字-字母边界插入空格**: `17Max` → `17 Max`

因为检索索引构建时也经过同一 `_tokenize()`，查询端和文档端分词完全对称，BM25 匹配正确。

### 10.3 ToolPlanner — LLM 优先工具调度器

**设计原则**:
- LLM 输出 UnifiedPlan JSON 决定调什么工具 + 关键参数
- 规则只在 2 处保留:
  1. `product_followup` 类型的 request 直接固定 `tool="product_followup"`
  2. LLM 调用失败时的 `planning/semantic_layer.py _rule_fallback()` 兜底 (正则匹配 cart/compare 信号，默认 chitchat)
- 不再前置多层规则栈；规则层仅作为 LLM 失败时的安全网

`_context_payload()` 将当前 `SessionContext` 的关键信息 (`has_focus_product`, `focus_product_id`, `last_product_ids`, `recent_cart_product_id`) 注入 LLM prompt，让 LLM 做上下文感知的工具选择。

### 10.4 StateReducer — 状态归约

每轮对话调用一次，将 `UnifiedPlan` 的决策信息写入 `SessionContext`：

`planning/state_reducer.py` 的 `apply_unified()`:
- `turn_index++` 递增轮次
- 记录 `last_intent = plan.tool`
- 合并硬约束 (category, sub_category, price_min/max, include/exclude_brands)
- 合并软偏好 (soft_preferences 字典)
- 记录 `source_turns` 审计日志
- 同步 `_sync_legacy_context()` (将硬/软约束写入 global_profile)

### 10.5 指代消解 (ReferenceResolver)

`services/reference_resolver.py` 中的 `ReferenceResolver` 解决多轮对话中的「这个/刚才那个/它/前面那个」等指代词解析：

1. `focus_product` (当前焦点商品) →
2. `last_recommendations` 中 role=primary 的主推 →
3. `recent_cart_product_id` →
4. `last_product_ids[-1]`

每一步都有明确的 fallback 逻辑，不会凭空编造。

长会话锚点持久化：首轮品牌/类目/product_ids 存储为 `reference_anchors`，当用户跨多轮后说「回到第一轮那个」，触发 `anchor_reference → first_turn` 解析。

### 10.6 数据层（v2.1 稳定化）

- **`db/`**: SQLAlchemy Base、引擎、模型定义；Alembic 迁移脚本位于 `server/alembic/`
- **`repositories/`**: 按领域隔离的数据访问对象
  - `cart_repository.py`: 购物车 CRUD 与 SKU 选择
  - `session_repository.py`: 会话、checkpoint、消息持久化
  - `order_repository.py`: 订单状态与确认令牌
  - `feedback_repository.py`: 反馈事件
  - `profile_repository.py`: 用户画像
- **配置**: `SHOPGUIDE_DATABASE_URL` 留空时默认落到仓库根 `data/shopguide.db`

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

编译时 Gradle 脚本 (`client/scripts/ensure_tunnel.sh`) 自动检测 Cloudflare tunnel 可用性并更新 URL。也可 `SKIP_TUNNEL_CHECK=true` 跳过。

### 11.4 版本号

`versionCode` / `versionName` 基于 `git rev-list --count HEAD` 自动生成。

## 12. 关键问题与解决方案

本章记录 SoulDance 在演进过程中真实遇到的核心问题、定位分析过程和最终采用的解决方案。它们共同塑造了当前 v2.1 的架构形态。

### 12.1 LLM 幻觉：虚构不存在的商品

**现象**

用户询问手机推荐时，LLM 会回复类似"小米 17 Max ¥6499"，但数据库中根本不存在该型号。更严重的是，LLM 还会给虚构商品补充详细参数、用户评价和推荐理由，极具迷惑性。

**定位分析**

通过对比 LLM 输出与数据库商品列表，发现幻觉集中在两类场景：

1. **自由生成场景**：LLM 在推荐文案中基于训练数据里的模式"脑补"商品，没有任何外部约束告诉它"只能引用库内商品"。
2. **信息混叠场景**：用户提到真实商品时，LLM 把训练数据中的相似型号（如"小米 14"→"小米 17"）当成库存商品输出。

日志审计还发现，旧架构只在生成结束后做一次简单正则匹配，无法拦截流式输出中已经到达客户端的虚构内容。

**解决方案**

引入**事实锚定管道**（Fact-Grounded Pipeline），把"LLM 能引用什么商品"从开放生成变成受控引用：

- `pipeline/fact_context.py` 在生成前构建 `[[product_id]]` 锚点事实表，只有进入事实表的商品才能被引用。
- `pipeline/anchor_validator.py` 在流式输出中逐 chunk 校验锚点：普通文本零延迟直通，`[[` 触发微缓冲，未闭合或无效锚点实时替换。
- `pipeline/hallucination_checker.py` 在生成后做价格偏差兜底审计。

这套机制把幻觉拦截点从"生成后"前移到"生成中"，虚构商品 ID 在到达客户端之前即被替换或阻断。

### 12.2 前后回答矛盾：同一商品既被否认又被推荐

**现象**

同一轮对话里，LLM 先说"未找到华为 Pura 90 Pro"，随后又在推荐列表里列出该商品；多轮对话中，用户已明确说"不要小米"，下一轮却仍出现小米商品。

**定位分析**

问题的根源在于 LLM 每次生成都是独立的条件采样，对历史会话中的"否认"、"拒绝"、"已确认"没有结构化记忆：

- 检索层不会记录 LLM 是否曾经否认过某个查询。
- LLM prompt 中没有注入"这些商品/属性已经被用户否定"的显式约束。
- 当对话焦点从 A 品牌漂移到 B 品牌时，系统没有提示 LLM 先说明立场变化。

**解决方案**

在 `pipeline/consistency_tracker.py` 中实现两条纯规则防线：

- **Denial Cache**：记录 LLM 已声明"不存在"的查询词，后续检索中过滤相关商品，并把 `denied_queries` 注入 FactContext prompt，阻止 LLM 再次提及。
- **Focus Drift 检测**：监控用户已确认的焦点商品是否在新推荐中消失。若发生无声明漂移，调用 `check_before_output()` 拦截输出，返回 `consistency_blocked` 事件和降级提示。

这两条规则不调用 LLM，延迟极低，解决了跨轮一致性问题。

### 12.3 服务异常后上下文丢失

**现象**

后端偶发 LLM 超时或进程重启后，用户需要重新描述预算、偏好、已选商品，体验割裂，像"失忆"了一样。

**定位分析**

旧架构只在内存中维护 `SessionContext`，没有持久化中间状态。一旦进程退出，整轮对话上下文全部丢失。即使有数据库，也只在对话结束时保存，无法恢复进行中的轮次。

**解决方案**

在 `services/session_store.py` 中实现 **3 阶段 Session Checkpoint**：

- **turn_start**：用户消息追加后立即保存，确保用户输入不丢失。
- **post_retrieve**：检索完成后保存，保留检索结果和初步决策。
- **turn_end**：整轮结束后保存完整状态。

恢复时根据 `checkpoint_stage` 返回不同级别的提示；`pipeline/degradation.py` 的 fallback 文案会引用已确认的上下文（如"根据您之前确认的 6000 元预算……"），而不是冷启动。

### 12.4 CJK-ASCII 分词断裂："小米17Max" 搜不到"小米 17 Max"

**现象**

用户输入"小米17Max"时，检索返回空或完全不相关商品；而输入"小米 17 Max"（带空格）则能命中。同样的问题也出现在"iPhone16Pro"、"华为Pura70"等中英文/数字混合型号上。

**定位分析**

通过打印 jieba 分词结果，发现：

- 查询"小米17Max"被切分为 `['小米', '17Max']`
- 数据库标题"小米 17 Max"被切分为 `['小米', '17', 'Max']`
- 由于"17Max"是一个独立 token，无法与分别独立的"17"和"Max"匹配，BM25 得分接近 0

这是 jieba 对中英文、数字字母边界的处理缺陷，不是索引问题。

**解决方案**

在 `retrieval/embedding_retriever.py` 中增加 `_normalize_cjk_ascii()` 预处理：

- 在 CJK 字符与 ASCII 字符之间插入空格：`小米17` → `小米 17`
- 在数字与字母之间插入空格：`17Max` → `17 Max`

该预处理同时应用于查询端和索引构建端，保证两端 token 化完全对称。修复后，中英文混合型号查询命中率显著提升。

### 12.5 Product Analysis：匹配到商品却回答"库中无此商品"

**现象**

用户问"华为 Pura 70 Pro 怎么样"，后台日志显示 `ProductMatcher` 已经正确匹配到数据库商品，但 LLM 仍回复"本店暂未找到该商品"。

**定位分析**

跟踪调用链后发现，匹配结果只用于触发后续分支判断，并没有进入 LLM 的 prompt。LLM 只看到原始用户消息，不知道系统已经命中了什么商品，因此它会基于自身知识做出"未找到"的判断。

这是一个典型的"系统知道，但 LLM 不知道"的信息断层问题。

**解决方案**

在 `tools/product_analysis.py` 中，当 `ProductMatcher.match()` 命中商品后，构造 `enriched_message`：

- 把商品名称、价格、品牌、核心规格以结构化格式拼入 user message
- 明确告诉 LLM"以下商品已在本店数据库中匹配到"

这样 LLM 生成回复时基于注入的事实，而非自身知识，彻底消除了"命中但回答没有"的假阴性。

### 12.6 单点 LLM 阻塞导致整轮无响应

**现象**

某些 LLM 调用（尤其是 plan_tool JSON 解析）偶发卡住，用户端长时间显示"思考中"，没有任何反馈，最终只能刷新或重试。

**定位分析**

通过 `/dev` 仪表盘观察端到端延迟，发现异常请求的耗时分布没有上限：有的请求 60 秒、90 秒甚至更久仍处于等待状态。进一步按阶段拆分后发现，延迟主要集中在 plan 或 generate 阶段，且一旦进入就无法中断。

**解决方案**

在 `services/timeout_policy.py` 中引入**阶段级超时**：

- 为 `plan` / `retrieve` / `generate` / `tool` 分别设置独立超时
- 超时后不再死等，而是触发上下文感知降级，返回包含用户查询词和关注商品的友好提示
- 错误按阶段标记 `failure_stage`，便于后续排查

这让"卡住"从用户无反馈变成可控降级，显著改善了长尾延迟体验。

### 12.7 突发流量下 LLM 并发耗尽

**现象**

多人同时使用时，后端偶发大量请求同时阻塞在 LLM 调用上，内存和连接数飙升，进而导致服务整体变慢甚至无响应。

**定位分析**

FastAPI 的 async 模型允许大量并发请求，但每个请求都会向 DeepSeek API 发起独立连接。LLM API 的并发连接数和本机内存都是有限资源，当请求数超过临界点时，新请求排队、老请求超时，形成级联故障。

**解决方案**

在 `services/concurrency.py` 中引入 **LLM 信号量**：

- 限制同时进入 LLM 调用的请求数
- 超出的请求排队等待，而非无限制地创建连接
- 与阶段超时配合，避免排队请求无限等待

这就像给 LLM 调用加了一道闸门，既能保护下游 API 和本机资源，又不会直接拒绝用户请求。

### 12.8 工具失败统一降级为"服务不可用"

**现象**

当某个工具执行失败（如检索服务异常、LLM 返回格式错误）时，用户看到的都是统一提示"服务暂时不可用"，无法判断是网络问题、检索问题还是生成问题，也不知道该重试还是换种说法。

**定位分析**

旧架构的异常处理集中在 `core/agent.py` 顶层，用一个大 `try/except` 捕获所有异常后调用统一的 `fallback_text_for_failure("internal_error")`。不同阶段的失败原因（plan 解析失败、retrieve 超时、generate 异常、tool 内部错误）被混为一谈，导致：

- 用户无法获得针对性提示
- 开发者从日志中也难以快速定位失败阶段
- 某些本可降级继续的场景被粗暴中断

**解决方案**

在 `core/agent.py` 和 `pipeline/degradation.py` 中引入**工具错误分类**：

- 将异常按发生阶段标记为 `plan` / `retrieve` / `generate` / `tool` / `internal`
- 每个阶段对应不同的降级文案和恢复建议：
  - `plan` 失败 → "理解需求时遇到一点问题，请重新描述一下"
  - `retrieve` 失败 → "检索阶段超时，正在为您降级处理，请稍后再试"
  - `generate` 失败 → "生成回复时出错，但已保存上下文，可直接继续对话"
  - `tool` 失败 → "某个工具执行失败，已跳过该步骤"
- 将 `failure_stage` 写入 `trace_store.py` 追踪日志，便于 `/dev` 仪表盘排查

这让错误提示从"一刀切"变成"阶段感知"，用户知道发生了什么，开发者也能更快定位根因。

### 12.9 意图解析多层规则栈复杂难维护

**现象**

旧架构中，一条用户消息要经过 5 层规则才能确定调用哪个工具：`rule_semantic_frame` → `_merge_rule_guards` → `_normalize_intent` → `_apply_product_admission_gate` → `_primary_text_matches_selected`。每层都有硬编码词典和特殊分支，新增一个工具或场景需要改多处，调试困难，且规则之间互相冲突。

**定位分析**

规则栈的初衷是降低 LLM 调用成本，但实际效果适得其反：

- 规则无法覆盖自然语言的多样性， constantly 需要打补丁
- LLM 的语义理解能力被规则压制，正确意图被规则覆盖
- 多层规则导致调用链冗长，延迟和故障点都增加

**解决方案**

用 **UnifiedPlan 统一决策** 替代多层规则栈：

- `planning/tool_planner.py` 中，LLM 一次 JSON completion 直接输出 `UnifiedPlan`，包含工具路由、约束、检索参数等全部信息
- 规则层退化为安全网：只在 LLM 失败时由 `planning/semantic_layer.py` 的 `_rule_fallback()` 做兜底
- `planning/state_reducer.py` 的 `apply_unified()` 将扁平字段写入 `SessionContext`，简化状态管理

效果：调用链从"5 层规则 + 3 次 LLM"简化为"1 次 LLM 决策 + 1 次生成"，新增场景只需调整 prompt 和工具实现，不再维护复杂的规则优先级。

### 12.10 后端代码平铺难以定位

**现象**

随着功能增加，`server/backend/app/` 下积累了 50+ 个平铺文件（`agent.py`、`tool_planner.py`、`fact_context.py`、`session_store.py`、`cart.py`、`order_service.py` 等）。新成员很难判断某个功能该放到哪个文件，import 关系混乱，循环依赖风险增加。

**定位分析**

平铺结构在项目早期运行良好，但当模块数量超过一定规模后：

- 文件名相似导致误导入（如 `session_store.py` 与 `models.py` 中的 `SessionStore`）
- 业务逻辑、基础设施、适配器混在一起，单测难以隔离
- 每次新增功能都要在根目录创建文件，命名空间快速膨胀

**解决方案**

v2.1 按职责将 `server/backend/app/` 重构为多个子目录：

- `core/`：核心编排（`ShopGuideAgent`）
- `planning/`：规划与状态（`ToolPlanner`、`UnifiedPlan`、`StateReducer`）
- `pipeline/`：事实锚定与降级（`FactContextBuilder`、`AnchorValidator` 等）
- `retrieval/` + `rag/`：检索与排序
- `tools/`：8 个 Tool 实现
- `services/`：业务服务与基础设施
- `repositories/` + `db/`：数据访问与持久化
- `memory/`、`feedback/`、`comparison/`、`adapters/`、`eval/`：专项能力

每个子目录有明确边界，新增功能时归属清晰，import 深度可控，也便于后续按领域拆分单测和微服务。
