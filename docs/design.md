# SoulDance · 灵舞 — 设计文档

## 产品定位

SoulDance 是一个 **LLM Agent 驱动的智能导购助手**。用户像和朋友聊天一样自然表达需求——"心情不好推荐甜的"、"华为 Pura 90 Pro 价格多少"、"帮我对比一下这两款"——AI 先理解意图，再调用对应的工具（检索推荐 / 模糊匹配 / 多维度对比 / 闲聊共情），最后用带真实商品卡片的自然语言回复。

与传统关键词搜索 + 筛选式电商不同，SoulDance 把"购物决策"变成了"对话体验"。

## 产品设计亮点

### 亮点 1：先共情，再推荐 — 复合需求自然融合

同类方案（ChatGPT 插件、电商客服机器人）要么只聊天不推荐，要么只推荐不理人。SoulDance 的 LLM Planner 能识别"情绪 + 购物"复合需求，先共情再自然带出商品推荐——回复里既有"抱抱你～吃点甜的确实治愈"，又有带真实锚点的内联商品卡片。用户感觉是在和朋友聊天，不是和电商客服对话。

### 亮点 2：模糊语义 → 精准商品 — BM25 + LLM 双重匹配

用户说"小棕瓶"、"华为 P70"、"雀巢咖啡"这种简称，传统电商搜索完全无法匹配到长标题商品（"雅诗兰黛特润修护肌活精华露淡纹紧致..."）。SoulDance 的 ProductMatcher 复用检索引擎的 BM25 分词 + 可选向量语义检索，对用户简称做 top-5 模糊匹配，gap-based 置信度判断——命中明确 → 直接回答；候选模糊 → 提示备选。LLM Planner 同时给 `category_hint` 做兜底（如"零食"→直接检索不打断）。

### 亮点 3：对话即决策 — 单轮完成"共情→推荐→加购"

不需要用户先搜、再筛、再比、再下单。一条消息"心情不好推荐甜的，便宜一点的"，SoulDance 在同一轮里完成：情绪安抚 → 检索匹配 → 推荐主推商品卡片 + 备选缩略图 → 用户点卡片加购。全程对话驱动，零页面跳转。

---

## 技术亮点

### 亮点 1：LLM Agent 架构 — 1 个入口替代 5 层规则栈

旧方案是 5 层互斥规则（`rule_semantic_frame → _merge_rule_guards → _normalize_intent → _apply_product_admission_gate → _primary_text_matches_selected`）——LLM 的输出被规则强行覆盖，导致"华为 Pura 90 Pro 价格多少"被拒答。

新架构是 1 个 LLM Planner 入口：

```
用户输入 → ToolPlanner (LLM) → ToolPlan JSON → 单点分发 → 具体 Tool 执行
```

LLM 只做决策（调哪个 tool + 参数），不做具体的商品匹配/检索/回复——这些由 Tool 内部的确定性系统完成。规则仅保留 2 处安全网（cart 硬性短语 + LLM 失败兜底）。

**与 LangChain / AutoGPT 的差异**：不是"LLM 生成 action 链然后逐步执行"——SoulDance 的 Planner 每次只输出 1 个 ToolPlan，执行完毕后等待用户下一轮输入。这避免了 token 消耗爆炸和无限循环，同时保持每轮响应的确定性和可控性。

### 亮点 2：chitchat 内嵌商品推荐 — 对话中自然带货

传统方案里"闲聊"和"推荐"是两条互斥路径。SoulDance 让 chitchat 工具在内部分两步走：

1. **注入 catalog 上下文**：在调 LLM 之前，用 BM25 retriever 取 top-5 相关商品摘要注入 prompt
2. **锚点扫描下发**：LLM 在自然回复中嵌入 `[[商品名#product_id]]` 锚点，后端扫描后下发 `product_item` 事件 → 前端渲染内联卡片

这让"心情不好推荐甜的"在不走推荐流的情况下，直接产出真实的商品卡片——没有额外的 LLM 调用，没有 context 切换。

### 亮点 3：BM25 共享索引 + gap-based 置信度 — 零额外成本的模糊匹配

传统的模糊商品匹配需要额外的 embedding 模型或别名字典。SoulDance 的 ProductMatcher 直接复用推荐流已有的 BM25/Hybrid retriever 索引，用 top1-vs-top2 的分数差（gap）作为置信度信号：

- "雀巢咖啡" → top1 1.0, top2 0.0, gap=1.0 → 明确命中 ✅
- "小米 17" → top1 1.0, top2 0.99, gap=0.01 → 候选模糊（库里小米 17 系列有 Max/Ultra/Pro 多款）→ best=None，candidates 透传

零额外索引、零额外模型，只是换个入口调同一套 retriever。

---

## 系统架构

```
┌──────────────────────────────────────────────────────┐
│                  Android 客户端                        │
│  Jetpack Compose + Material3 + Coil + OkHttp          │
│  · 段落-卡片交替渲染（AiMessageBlock）                  │
│  · WebSocket 实时流式接收                               │
│  · ProductDetailBottomSheet 锚点/卡片统一入口           │
└───────────────┬──────────────────────────────────────┘
                │ HTTPS + WebSocket
                │ (Cloudflare Tunnel 公网穿透)
┌───────────────▼──────────────────────────────────────┐
│              FastAPI 后端 (Python 3.12)                │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │         ToolPlanner (LLM 入口)                │     │
│  │  DeepSeek v4-pro → ToolPlan JSON              │     │
│  │  plan_tool() 延迟: 15-25s                     │     │
│  └───────────────┬──────────────────────────────┘     │
│                  │ 单点分发 (_dispatch_tool)            │
│  ┌───────────────┼──────────────────────────────┐     │
│  │  ┌────────────┴───────────┐                  │     │
│  │  │ 7 个 Tool 各司其职      │                  │     │
│  │  │ · product_analysis     │ BM25 模糊匹配    │     │
│  │  │ · chitchat             │ LLM + catalog注入 │     │
│  │  │ · recommend_product    │ IR + retrieval   │     │
│  │  │ · product_followup     │ 焦点商品追问      │     │
│  │  │ · compare_products     │ 多维度对比        │     │
│  │  │ · scenario_bundle      │ 场景拆解+slot检索 │     │
│  │  │ · cart_operation       │ 购物车状态机      │     │
│  │  └────────────────────────┘                  │     │
│  └──────────────────────────────────────────────┘     │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │         Retrieval Layer                       │     │
│  │  BM25(jieba) + Dense(sentence-transformers)   │     │
│  │  RRF/weighted fusion + CrossEncoder rerank    │     │
│  └──────────────────────────────────────────────┘     │
│                                                       │
│  ┌──────────────────────────────────────────────┐     │
│  │         Trace & Observability                 │     │
│  │  TraceStore ring buffer + JSONL               │     │
│  │  /dev Developer Console (Chart.js dashboard)  │     │
│  └──────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| **LLM** | DeepSeek v4-pro (v4-flash for JSON tasks) | 计划/生成分离，fast model 做 plan_tool |
| **后端框架** | FastAPI + Uvicorn | 异步 WebSocket + REST |
| **检索** | rank-bm25 + sentence-transformers + CrossEncoder | BM25 + dense 融合 + 重排 |
| **分词** | jieba | 中文分词 |
| **数据模型** | Pydantic v2 | 全链路类型校验 |
| **数据库** | SQLite (购物车/订单/会话) | 轻量嵌入式 |
| **Android** | Kotlin + Jetpack Compose + Material3 | 原生 UI |
| **图片加载** | Coil | Compose 原生图片库 |
| **网络** | OkHttp + Retrofit | HTTP + WebSocket |
| **公网穿透** | Cloudflare Tunnel | 真机调试 |
| **测试** | pytest + JUnit + MockWebServer | 后端 + 前端单测 |
| **仪表盘** | Chart.js v4 CDN | 零依赖可视化 |

## 依赖环境

### 后端
- Python 3.12+
- virtualenv (venv_shopguide_backend)
- 见 `server/requirements.txt`

### 前端
- JDK 17+
- Android SDK 36
- Kotlin 2.3.21 + Compose BOM 2026.04.01
- 见 `client/app/build.gradle.kts`

---

## 目录结构

```
SoulDance/
├── client/                          # Android 应用
│   └── app/src/main/java/.../
│       ├── ui/component/            # UI 组件 (AiMessageBlock, InlineProductCard 等)
│       ├── vm/                      # ViewModel (ChatViewModel, CartViewModel)
│       ├── data/model/              # 数据模型 (ProductUiModel, ChatMessageUiModel)
│       ├── data/remote/             # 网络层 (WebSocket client, API services)
│       └── config/                  # AppConfig, UserSession
├── server/                          # FastAPI 后端
│   ├── backend/app/
│   │   ├── agent.py                 # 核心 Agent (ToolPlanner 入口, 分发, 采集)
│   │   ├── tool_planner.py          # LLM 工具调度器
│   │   ├── tool_plan.py             # ToolPlan Pydantic schema
│   │   ├── product_matcher.py       # BM25 模糊商品匹配
│   │   ├── llm_client.py            # LLM 客户端 (DeepSeek/Doubao)
│   │   ├── trace_store.py           # 请求追踪存储
│   │   ├── dev_console.py           # 开发者仪表盘
│   │   ├── tools/                   # 7 个 Tool 实现
│   │   ├── prompts/v1/              # LLM 系统提示
│   │   │   ├── tool_planner.txt     # Planner 提示
│   │   │   ├── response.txt         # 推荐回复提示
│   │   │   └── chitchat.txt        # 闲聊提示
│   │   ├── rag/                     # 检索与排序
│   │   └── models.py                # 所有 Pydantic 模型
│   ├── tests/                       # 后端测试
│   └── scripts/                     # 启动/环境脚本
├── ecommerce_agent_dataset/         # 共享商品数据 (100 款)
├── docs/                            # 文档
│   ├── design.md                    # 本设计文档
│   ├── architecture.md              # 架构文档
│   ├── deploy-and-experience.md     # 部署与体验文档
│   └── runbook.md                   # 开发运行手册
├── deploy/                          # 部署模板
└── data/                            # 运行时数据 (git ignore)
```

---

## 配置说明

### LLM Provider

编辑仓库根目录 `.env`：

```bash
LLM_PROVIDER=deepseek              # 或 doubao
LLM_API_KEY=sk-xxx                 # DeepSeek API key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro         # 生成/计划用
LLM_FAST_MODEL=deepseek-v4-flash  # plan_tool JSON 用（更快）
```

### 后端端口

```bash
HOST=0.0.0.0 PORT=8000 bash server/scripts/start_backend.sh
```

### Android AppConfig

`client/.../config/AppConfig.kt` 中的 `BASE_HTTP_URL` / `BASE_WS_URL` 指向 Cloudflare tunnel 地址，编译时 Gradle 脚本自动检查隧道可用性并更新。

---

## 关键问题与解决方案

### Q1: "华为 Pura 90 Pro 价格" → "我没抓到你的购物需求"

**根因**：旧架构的 5 层规则栈中，`rule_semantic_frame` 的 `_has_shopping_signal` 关键词词典不含"华为 Pura"这类品牌+型号组合 → 判为 `unclear_input`。

**解决**：Phase B 用 LLM ToolPlanner 替代规则栈。LLM 看到"华为 Pura 90 Pro + 价格"直接输出 `tool=product_analysis, target_product_query=...`，不再依赖词典。

### Q2: "心情不好推荐甜的" → filter_recovery "请选择类目"

**根因**：ToolPlanner 判 `recommend_product`，但 taxonomy resolver 无法把 LLM 输出的 `category_hint="零食"` 映射到目录类目 → 触发 `filter_recovery_options`。

**解决**：Plan prompt 加"复合需求→chitchat"优先级规则 + `_run_retrieval_flow` taxonomy miss 时用 `category_hint` 直接检索。chitchat 流内注入 catalog top-5 让 LLM 用真实 ID 生成商品锚点。

### Q3: "连接中断，请重试" 超时

**根因**：Android `STREAM_TIMEOUT=30s`，在 plan_tool (15-25s) + stream 首 chunk (10-20s) 两轮 LLM 调用合并耗时下不够。

**解决**：Android timeout → 90s；后端首 chunk timeout → 25s；`_do_stream_message` 立即 yield thinking 状态让客户端知道没死连。

### Q4: 前端商品卡片展示异常

**根因**：Android `InlineProductThumbnails` 把主推和备选混在底部缩略图区，视觉无层级区分。

**解决**：`AiMessageBlock` 改为段落-卡片交替布局——含锚点的段落（主推）后插入 `InlineProductCard`，未在锚点提及的商品（备选）放气泡下 `AlternativeThumbnails`（56dp 缩略图，视觉层级弱化）。
