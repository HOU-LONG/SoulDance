# SoulDance · 灵舞 — 设计文档

## 产品定位

SoulDance 是一个 **LLM Agent 驱动的智能导购助手**。用户像和朋友聊天一样自然表达需求——"心情不好推荐甜的"、"华为 Pura 90 Pro 价格多少"、"帮我对比一下这两款"——AI 先理解意图，再调用对应的工具（检索推荐 / 模糊匹配 / 多维度对比 / 闲聊共情），最后用带真实商品卡片的自然语言回复。

与传统关键词搜索 + 筛选式电商不同，SoulDance 把"购物决策"变成了"对话体验"。

## 产品设计亮点

### 亮点 1：精灵空间 — 养成系导购伴侣，让购物决策有人情味

传统的电商 App 首页是冷冰冰的 Banner、类目网格和搜索框——用户面对的是一台"贩卖机"。SoulDance 的首页是一个**养成系 2D 精灵空间**：一只叫"灵舞"的虚拟精灵住在温暖的房间里，她会随着你的对话状态实时变化表情和姿态（空闲 → 倾听 → 思考 → 搜商品 → 推荐展示 → 加购成功庆祝 → 升级），每一次交互都伴随视觉反馈。

**设计理念**：购物助手不应该是一行对话气泡。我们选择用"游戏化养成"把 AI 的不可见推理过程可视化——精灵低头思考 = 正在调用 LLM，双手捧礼盒 = 找到推荐商品，转圈撒花 = 加购成功。用户在精灵身上看到亲密度等级（Lv.1–30+）、火星积分（完成导购任务赚取）、换装系统（默认装/家居顾问装），每一次购物对话都在和精灵一起成长。

**与同类方案的差异**：ChatGPT 的对话界面、淘宝的瀑布流、得物的图文推荐——都没有一个"活"在前面的角色来承载情感连接。SoulDance 用精灵空间把冷冰冰的"AI Agent"变成了一个有形象、有情绪、会成长的"导购伴侣"，让用户在打开 App 的那一刻就知道——这不是一个工具，是一个有温度的地方。

**核心交互**：
- **语音 + 文字双输入**：精灵支持按住说话，识别结果自动发送到聊天
- **对话联动**：聊天页每产生一条消息，首页精灵实时切换姿态（思考/搜索/展示/庆祝）
- **日常任务**：每日导购对话、加购、浏览推荐、分享好物——完成任务赚火星积分
- **等级成长**：加购成功增加亲密度，满值升级解锁更高折扣率
- **装扮系统**：可选择默认装和家居顾问装，选中后精灵外观即时切换

### 亮点 2：先共情再推荐 — 单轮处理"情绪+购物"复合需求

传统的 AI 导购方案把"闲聊"和"推荐"视为互斥的两条路径——要么聊天、要么推商品，无法在自然对话中无缝融合。当用户说"今天心情不好，推荐点甜的"时，传统方案要么只安慰不推荐（"心情不好确实难受，建议你..."），要么只推荐不安慰（"根据你的需求推荐以下商品..."）。

SoulDance 的 LLM ToolPlanner 专门为复合需求设计了优先级规则：只要用户同时表达了情绪诉求和购物意图，就路由到 `chitchat` 工具——这个工具会**先共情**（"抱抱你～吃点甜的确实治愈"），**再自然带出推荐**（"给你挑了两款：[[巧克力#p_xxx]] 和 [[糖果#p_xxx]]"），并且 **用真实的库内商品 ID 生成内联卡片**（因为 chitchat 流已经在 LLM 上下文里注入了 BM25 检索到的 top-5 相关商品）。

这个设计让用户的体验变成"和一个关心你的朋友聊天，聊着聊着就帮你挑好了"——而不是"先填需求表单，再看推荐列表"。

### 亮点 3：对话即决策闭环 — 从"想买"到"买了"零跳转

传统电商的用户路径是：搜索 → 筛选 → 浏览列表 → 点进详情 → 比价 → 加购 → 去购物车 → 结算。每一步都是页面跳转和认知中断。

SoulDance 把整个决策闭环压缩到**一个聊天界面**内：

1. 用户说"推荐一款咖啡，便宜一点的"
2. AI 在同一个聊天气泡里回复：一段自然说明 + 一张**内联商品卡片**（缩略图 + 名称 + 价格 + 品牌，点击弹出详情浮层）+ **备选商品缩略图条**
3. 用户在详情浮层直接点"加购"按钮 → 精灵庆祝 + 亲密度提升
4. 用户继续追问"换个更便宜的" → AI 在上下文中记住焦点商品，推荐更低价替代品

全程不离开聊天界面。卡片是信息载体、浮层是决策空间、聊天是导航方式。这才是"对话式电商"该有的样子——不是"在聊天框里搜商品"，而是"和 AI 聊着聊着就把东西买了"。

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
