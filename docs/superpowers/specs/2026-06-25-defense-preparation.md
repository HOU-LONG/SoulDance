# SoulDance 智能导购 Agent — 答辩准备材料

**日期**：2026-06-25
**目标**：字节跳动 AI/LLM 应用开发岗 求职技术面试
**形式**：现场 Live Demo（~10min）+ 技术路径讲述（~15min）+ Q&A 应答（~35min）
**评审背景**：全栈综合评审

---

## 0. 答辩策略总纲

### 核心叙事主线

> **"如何构建一个在长会话中依然稳定、高效、不产生幻觉的 LLM Agent？"**

整个答辩围绕这一核心问题展开——从问题定义 → 架构决策 → 逐层验证 → 量化结论。不是逐个罗列技术点，而是讲述一个"我遇到了什么问题 → 为什么这么解决 → 怎么证明解决了"的完整故事。

### 叙事节奏

```
Phase 1: Demo 驱动 (10 min)
  └─ 边演示边拆解，每一屏都是架构图中的一层

Phase 2: 技术深讲 (15 min)
  └─ 从架构总览 → 逐层深入 → 评测体系 → 量化结论

Phase 3: Q&A 攻防 (35 min)
  └─ 专家追问技术细节、技术选型、评测方法论
```

### 关键原则

1. **先 Demo 后 PPT**：让专家看到能跑的东西，再展开讲怎么做的
2. **每个技术点都有量化证据**：不空讲"效果好"，引 trace 数据 / 评测指标
3. **对弱点诚实**：C0 硬截断、LLM judge 分歧率、B1/B2 系统级边际——这些已经做了 methodological 处理，可以诚实讲但必须讲清楚你已经做了什么
4. **主动 cue 你的安全护栏**：§13 的 16 条 safeguards 是你的护城河

---

## 1. Demo 演示脚本

### 1.0 事前准备（Demo 前 15 分钟）

```bash
# 1. 确保后端启动
cd /home/huadabioa/houlong/SoulDance/server
source ../env/venv_shopguide_backend/bin/activate

# 2. 检查 Cloudflare tunnel 是否通畅
curl -s https://lists-province-wines-postal.trycloudflare.com/health

# 3. 如果 tunnel 不通，切换 AppConfig 到本地模式：
#    AppConfig.kt: 取消注释 10.0.2.2:8000，注释 Cloudflare URL
#    然后 adb reverse tcp:8000 tcp:8000

# 4. 启动后端（非 TTS/STT 模式）
HOST=127.0.0.1 PORT=8000 USE_EMBEDDING=0 TTS_ENABLED=false STT_ENABLED=false \
  ARK_API_KEY=<your_key> LLM_API_KEY=<your_key> \
  bash server/scripts/start_backend.sh

# 5. 准备好 Android 模拟器或真机，安装最新 APK
# 6. 准备一个"干净"的会话（清除之前的聊天记录）
```

### 1.1 Demo 流程（8-10 min）

#### Scene 1: 开场 — "推荐一款护肤品"（1.5 min）

| 步骤 | 操作 | 展示内容 | 旁白话术 |
|------|------|----------|----------|
| 1 | 打开 App，展示首页 | Sprite 精灵空间 + 聊天输入框 | "这是 SoulDance，一个智能导购 Agent。不同于传统电商搜索，用户用自然语言描述需求，Agent 负责理解意图、检索商品、做推荐。" |
| 2 | 输入："我是干性皮肤，想找一款适合秋冬用的保湿精华，预算500以内" | 展示完整自然语言输入 | "注意这个 query 包含三个约束：肤质、季节、预算。Agent 需要同时满足这些硬约束。" |
| 3 | 等待回复 | 展示产品卡片流式返回 | "看 — 推荐结果带图片、价格、SKU 选项。推荐的这款是 XXXX，价格 XXX 元，符合预算。下面还有推荐理由。" |

**讲解点**：这一轮实际走了 planner → retrieval → ranker → answer 完整 pipeline。SemanticParser 解析出 intent=recommend_product + 硬约束 {skin_type: 干性, season: 秋冬, max_price: 500}。

#### Scene 2: 上下文保持 — "有没有便宜一点的替代品？"（1.5 min）

| 步骤 | 操作 | 展示内容 | 旁白话术 |
|------|------|----------|----------|
| 1 | 输入："有没有便宜一点的替代品？" | 不重新指定肤质/类目 | "这是一个典型的 follow-up。用户没有重申肤质、品类、季节 — Agent 必须从上下文推断。" |
| 2 | 等待回复 | 展示价格更低但仍符合干皮+秋冬约束的产品 | "Agent 正确识别了这是 product_followup 意图 — 保持了 focus_product 指向上一轮的精华，同时应用了'更便宜'的约束松弛。" |
| 3 | 指出关键点 | 强调 focus_product 正确保持 | "如果 focus_product 丢掉了，这一轮就会随机推荐。上下文控制层（A2 结构化快照）保证了 focus 不丢失。" |

**讲解点**：引出上下文控制层 A2（结构化快照）的作用 — focus_product / last_plan / pending_clarification 始终可见。

#### Scene 3: 商品对比 — "帮我对比一下这两款"（1.5 min）

| 步骤 | 操作 | 展示内容 | 旁白话术 |
|------|------|----------|----------|
| 1 | 输入："帮我对比一下雅诗兰黛小棕瓶和刚才那个便宜的" | 展示模糊指代+对比意图 | "对比请求有两个难点：一是用了品牌名+模糊指代'刚才那个'，二是需要同时引用两个可能不在同一轮的商品。" |
| 2 | 等待回复 | 展示对比卡片：价格/成分/评价/肤质 | "Agent 正确解析了指代，从历史上下文中提取了两个商品的 product_id，触发了 comparison 工具链。" |
| 3 | 指出 Reranker 作用 | 强调对比的维度覆盖 | "这里 Reranker 层在对比场景下触发了 LLM 兜底重排，确保对比维度的语义相关性，而不只是价格/品牌匹配。" |

**讲解点**：引出 Reranker 的场景触发机制 + 对比工具链。

#### Scene 4: 长会话上下文保持 — "第十轮后的指代测试"（2 min）

| 步骤 | 操作 | 展示内容 | 旁白话术 |
|------|------|----------|----------|
| 1 | 快速做 5-6 轮与当前话题无关的查询（切换类目），展示历史列表 | 聊天历史列表变得越来越长 | "在真正的导购场景中，用户会反复切换需求。历史不断增长，Agent 的上下文窗口面临压力。" |
| 2 | 回到最初的话题："回到第一轮那个干皮的精华，有没有同品牌的其他系列？" | 展示跨越多轮的指代 | "这一轮跨越了多轮对话回到第一轮的商品 — 如果上下文管理不当，Agent 会丢失 focus。" |
| 3 | 等待回复 | 展示是否正确找回第一轮的商品 | "Agent 正确找到了第一轮推荐的品牌，这是因为上下文控制层（A1 窗口截断）在上下文增长时做了智能裁剪，保留了关键轮次。" |

**讲解点**：引出上下文控制层 A1（窗口截断）的必要性 — 不做压缩，token 成本线性增长，最终超出模型上下文窗口。

#### Scene 5: 购物车闭环（1.5 min）

| 步骤 | 操作 | 展示内容 | 旁白话术 |
|------|------|----------|----------|
| 1 | 输入："把第一款加入购物车" | 展示加购操作 | "Agent 需要正确解析'第一款'指向当前推荐列表的第一个产品。" |
| 2 | 输入："查看购物车" | 展示购物车列表 | "购物车状态在后端持久化，由 CartService 管理。" |
| 3 | 输入："把刚才那个换成 50ml 的" | 展示 SKU 切换 | "Agent 保持购物车中商品的 focus，并理解'换成50ml'是 SKU 级别的操作。" |

**讲解点**：购物车是带状态的业务工具 — Agent 不只是"聊天"，而是可操作的导购助手。

### 1.2 Demo 风险预案

| 风险 | 预案 |
|------|------|
| Cloudflare tunnel 不通 | 提前 15min 检查；不通则切换到 adb reverse 本地模式 |
| ARK API 超时 | 准备一张截图做 fallback 展示；解释"实际后端部署在远端 A100，Demo 环境网络波动" |
| 检索结果不理想 | 不慌，这恰好引出"为什么需要 Reranker + 评测体系" |
| 语音助手无法展示 | STT/TTS 默认关闭；如果有时间可以开启展示一句"语音交互也支持，底层接的豆包 TTS/STT" |

---

## 2. 技术路径讲述大纲

### 2.1 系统架构总览（3 min）

**画架构图（现场白板或幻灯片）**：

```
┌─────────────────────────┐
│   Android Client        │
│   Jetpack Compose       │
│   WebSocket + HTTPS     │
└───────────┬─────────────┘
            │  ChatRequest {type, session_id, message}
            ▼
┌─────────────────────────┐
│   FastAPI Backend       │
│                         │
│  ┌───────────────────┐  │
│  │ SemanticParser    │  │  ← 语义理解层
│  │ + IntentCompiler  │  │
│  └────────┬──────────┘  │
│           ▼              │
│  ┌───────────────────┐  │
│  │ HybridRetriever   │  │  ← 混合检索层
│  │ BM25 + Dense + RRF│  │
│  └────────┬──────────┘  │
│           ▼              │
│  ┌───────────────────┐  │
│  │ Reranker          │  │  ← 精排层（新增）
│  │ CrossEncoder+LLM  │  │
│  └────────┬──────────┘  │
│           ▼              │
│  ┌───────────────────┐  │
│  │ rank_products     │  │  ← 业务规则打分
│  │ + hard_filter     │  │
│  └────────┬──────────┘  │
│           ▼              │
│  ┌───────────────────┐  │
│  │ Response + TTS    │  │  ← 流式输出
│  └───────────────────┘  │
│                         │
│  ┌─ 上下文控制层 ────┐  │
│  │ A1 窗口截断       │  │  ← 上下文体积控制
│  │ A2 结构化快照     │  │  ← 关键状态保持
│  └───────────────────┘  │
│  ┌─ 决策复用层 ────┐    │
│  │ B1 语义记忆缓存   │  │  ← 跳过 LLM 重选
│  │ B2 排序结果缓存   │  │  ← plan→ranked 复用
│  └───────────────────┘  │
└─────────────────────────┘
```

**讲解话术**：

"整个架构分为 6 层。从上到下：用户自然语言 → 语义理解 → 混合检索 → 精排 → 业务规则 → 流式输出。

另外有两层横切关注点：上下文控制层负责控制注入 LLM 的上下文体积和结构；决策复用层负责缓存和复用历史决策。

为什么分层这么细？因为在 long session 场景下，每层的故障模式和优化空间都不同。如果不分层，你没法做消融实验，也没法讲清楚每层到底贡献了多少。"

**关键数字**：
- 数据集：100 个商品，4 个类目（美妆/数码/服饰/食品）
- 每个商品含：SKU 变体 + RAG 知识库（营销文案/FAQ/用户评价）+ 图片
- 后端约 80 个 Python 文件，504 个测试通过

### 2.2 核心链路：自然语言 → 结构化意图 → 结构化检索 → 商品匹配（5 min）

**这是整个项目最核心的技术链路——也是答辩中最应该讲清楚的部分。**

用户说一句话，最终得到精确的商品推荐。中间经历了什么？不是黑箱 LLM pipeline，而是 **5 个阶段的强类型结构化数据转换**。每一步的输入和输出都是 Pydantic Model，可校验、可回溯、可 debug。

---

#### 阶段 1：规则快速通道 — `rule_semantic_frame()`

**源文件**：`server/backend/app/semantic_layer.py:95-168`

这是一层**纯规则引擎**（正则 + 关键词字典），不调 LLM，1ms 内返回：

```python
def rule_semantic_frame(request: ChatRequest) -> SemanticFrame:
    # ① 购物信号检测：没有购物意图 → unclear_input
    if not _has_shopping_signal(text):                          # L284-291: 关键词正则
        return SemanticFrame(intent="unclear_input")

    # ② 价格约束提取（正则，非 LLM）
    price_min = _detect_price_min(text)   # "500以上" → 500.0  L551-561
    price_max = _detect_price_max(text)   # "500以内" → 500.0  L564-586

    # ③ 品牌排除/包含（正则）
    extract_excluded_brands(text)         # "不要日系" → ["日本"]
    extract_included_brands(text)         # "雅诗兰黛" → ["雅诗兰黛"]

    # ④ 软偏好字典匹配（关键词映射表）
    if "油皮" in text: soft["skin_type"] = "油皮"             # L146-147
    if "保湿" in text: soft["effect"] = "保湿修护"             # L150-151
    if "送人" in text: soft["occasion"] = "送礼"               # L158-159
    # ... 共 15 个软偏好维度

    return SemanticFrame(intent=intent, constraint_edits=edits)
```

**产出**：`SemanticFrame`（`server/backend/app/models.py:94-103`）—— Pydantic Model，包含 intent + constraint_edits + soft_preferences。

**为什么需要这一层？** 两点：(1) 1ms 覆盖 60% 简单意图，省 LLM 调用；(2) LLM 不可用时兜底，服务不降级。

---

#### 阶段 2：LLM 语义解析 + 规则守卫合并 — `SemanticParser.parse()`

**源文件**：`server/backend/app/semantic_layer.py:26-52`

规则层不够用时（复杂意图/模糊表述），调 LLM。但**关键设计**：LLM 输出和规则层输出不是二选一，而是**取并集**：

```python
async def parse(self, request, context) -> SemanticFrame:
    # ① LLM 语义解析（带上下文快照）
    raw = await self.llm_client.parse_semantic_frame(
        request.message,
        self._payload(context),     # A2 结构化上下文：focus_product/last_plan/...
        request_type=request.type,
    )
    frame = _parse_frame(raw)                      # L203-206: JSON → SemanticFrame

    # ② 低置信度 → 转澄清
    if frame.confidence < 0.6:                     # L35-37
        frame.intent = "clarification"

    # ③ ★ 关键：规则守卫合并
    guarded = _merge_rule_guards(frame, request)    # L222-259

    # ④ 上下文 followup 二次判定
    if guarded.intent == "unclear_input":
        recovered = await self._try_contextual_followup_judge(...)
        # ↑ LLM 说"不明白"但上下文有 focus_product → 是否其实是追问？
```

**`_merge_rule_guards()` 是整条链路最精妙的设计**（`semantic_layer.py:222-259`）：

```python
def _merge_rule_guards(frame, request):
    guarded = rule_semantic_frame(request)   # 同时跑一遍规则层

    # 规则层判定为 small_talk → 覆盖 LLM 的 intent
    if guarded.intent == "small_talk":
        frame.intent = "small_talk"           # 规则层有否决权

    # 规则层提取了购物车操作 → 覆盖 LLM
    if guarded.intent == "cart_operation":
        frame.cart_operation = guarded.cart_operation

    # ★ 硬约束取并集：LLM 的软意图 + 规则层的硬提取
    frame.constraint_edits.add.exclude_terms.extend(guarded...)     # L233-235
    frame.constraint_edits.add.exclude_brands.extend(guarded...)    # L242-244
    frame.constraint_edits.add.price_max = guarded...               # L247-248
    # soft_preferences 也合并
    frame.constraint_edits.add.soft_preferences.update(guarded...)  # L249
```

**为什么这样设计？** LLM 擅长理解"我想要那种涂上去不油腻的"（语义理解），规则层擅长精确提取"500 元以内"和"不要日系"（结构化提取）。两者并行取并集，各取所长。LLM 可能把"500"误解为"500ml"——但正则不会；LLM 可能无法从"涂上去不油腻"中提取出"肤质=油皮"——但规则字典会。

---

#### 阶段 3：意图编译 → 结构化检索计划 — `IntentCompiler` + `QueryBuilder`

**源文件**：
- `server/backend/app/intent_compiler.py:10-20` — IntentCompiler.compile()
- `server/backend/app/query_builder.py:9-62` — QueryBuilder.build()

这是**数据治理的核心环节**——用户的自然语言被完整转换为结构化的 `RetrievalPlan`：

```python
# query_builder.py:15-62
def build(self, ir, context, user_message) -> RetrievalPlan:
    # ① 从 session 状态读当前约束（跨轮次累积！）
    hard = context.state.constraint_state.hard    # HardConstraints
    soft = dict(context.state.constraint_state.soft)

    # ② Taxonomy 解析：类目匹配
    _fill_category_from_text(hard, user_message, self.taxonomy)  # L65-82

    # ③ 构建检索查询字符串（类目+约束+偏好拼接）
    retrieval_query = " ".join([
        *ir.query_intent.query_terms, user_message,
        hard.category, hard.sub_category, *soft.values()
    ])

    # ④ 澄清策略判定
    need_clarification, question = _clarification_policy(...)

    # ⑤ 选择检索模式
    retrieval_mode = {
        "product_followup": "product_focus_retrieval",  # 基于 focus_product 检
        "compare_products": "state_then_detail",          # 先拿候选再对比
        "scenario_bundle": "decompose_parallel",          # 拆解并行检
    }.get(intent, "single")

    return RetrievalPlan(
        intent=intent,
        retrieval_mode=retrieval_mode,
        hard_constraints=hard,       # 硬约束：价格/品牌/排除词
        soft_preferences=soft,        # 软偏好：肤质/功效/送礼场景
        retrieval_query=...,          # 混合检索查询字符串
    )
```

**以"我是干皮，想买500以内的保湿精华，不要日系"为例的完整转换**：

```
用户输入: "我是干皮，想买500以内的保湿精华，不要日系"

  → [阶段1] rule_semantic_frame()
     price_max=500.0, exclude_brand_regions=["日本"], soft={"skin_type":"干皮","effect":"保湿修护"}

  → [阶段2] SemanticParser.parse()
     LLM 确认 intent=recommend_product, category="精华", confidence=0.85
     _merge_rule_guards() 合并：price_max + exclude 追加到 LLM 输出

  → [阶段3] QueryBuilder.build()
     RetrievalPlan(
       intent="recommend_product",
       retrieval_mode="single",
       category="精华",
       hard_constraints=HardConstraints(
         sub_category="精华",
         price_max=500.0,
         exclude_brand_regions=["日本"],
         in_stock_only=True,
       ),
       soft_preferences={"skin_type":"干皮","effect":"保湿修护"},
       retrieval_query="我是干皮想买500以内的保湿精华不要日系 精华 干皮 保湿修护",
     )
```

**三个关键设计决策**：

1. **全程 Pydantic 强类型**：`SemanticFrame`（`models.py:94`）→ `ShoppingIntentIR`（`models.py:106`）→ `RetrievalPlan`（`models.py:45`），每一步的中间产物都是可序列化、可校验的。debug 不是看 LLM 黑箱输出，是看每一步的 JSON。

2. **约束跨轮累积**：`HardConstraints` 存在 session state 中（`state_reducer.py`），每轮基于上一轮做增量编辑。用户在第五轮说"不要日系"，到第二十轮说"刚才那个不要日系算了"——约束的增删改通过 `apply_constraint_edits()`（`semantic_layer.py:71-85`）做事务性变更，不是每轮重新解析全量历史。

3. **Clarification 优于乱猜**：`_clarification_policy()` 判断是否信息不足——比如用户说"推荐一款"但没给任何约束，Agent 会反问"您想要什么类型的商品？有没有预算或品牌偏好？"，而不是随机推荐。

---

#### 阶段 4：混合检索 + 精排 — `AdaptiveRetriever` + `HybridRetriever` + `Reranker`

**源文件**：
- `server/backend/app/adaptive_retriever.py:31-80` — AdaptiveRetriever.search_async()
- `server/backend/app/rag/fusion.py` — HybridRetriever（BM25+Dense+RRF 融合）
- `server/backend/app/rag/reranker.py` — Reranker（CrossEncoder + LLM 兜底）
- `server/backend/app/rag/reranker_scenarios.py` — 场景触发判断

```python
# adaptive_retriever.py:57-80
async def search_async(self, plan, top_k=30):
    # ① 混合检索：BM25 + Dense Vector + RRF 融合
    hybrid_results = self.hybrid_retriever.search_with_evidence(plan, top_k=30)

    # ② Reranker 精排
    if self.reranker:
        pre_scenario = detect_pre_scenario(plan)  # 场景检测
        hybrid_results = await self.reranker.rerank(
            plan.retrieval_query, hybrid_results, top_k=top_k, scenario=pre_scenario)

    # ③ 自适应放松：结果不足时逐步放宽约束
    if len(hybrid_results) < min_candidates:
        # 放松顺序：软偏好 → 价格区间 → 类目降级
```

**混合检索的两路**：
- **BM25**（jieba 分词）：精确匹配——"雅诗兰黛"、"精华"必须出现在商品字段中
- **Dense Vector**（bge-small-zh-v1.5）：语义近似——"干皮"↔"干燥肌肤"、"秋冬"↔"寒冷季节"
- **RRF 融合**：`score = 1/(60+rank_bm25) + 1/(60+rank_dense)`——不要求两路分数量纲一致，只依赖排名

**Reranker 场景触发**（`reranker_scenarios.py`）：
- **默认**：CrossEncoder（BGE-reranker-v2-m3），本地推理 <10ms
- **LLM 兜底**（三种场景）：对比意图 / 低置信度 / 用户纠偏重推

---

#### 阶段 5：硬过滤 + 业务打分 — `hard_filter()` + `rank_products()`

**源文件**：
- `server/backend/app/constraint_filter.py` — hard_filter()
- `server/backend/app/ranker.py` — rank_products()

```python
# hard_filter：硬约束把关（constraint_filter.py）
for product in candidates:
    if plan.hard_constraints.price_max and product.price > plan.hard_constraints.price_max:
        continue    # 超预算 → 直接过滤
    if product.brand_region in plan.hard_constraints.exclude_brand_regions:
        continue    # 日系 → 直接过滤

# rank_products：业务规则打分（ranker.py）
# 类目匹配度 × 品牌匹配度 × 价格合理度 × 评价星级 → 综合分 → Top 5-8
```

Agent 从商品数据库拿到最终 Top-K，生成推荐回复 —— 走 `server/backend/app/tools/retrieval.py:15-30`（RetrieveProductsTool）。

---

#### 完整链路图（答辩时直接展示）

```
用户自然语言: "干皮，500以内保湿精华，不要日系"
  │
  ▼
┌─ 阶段1: rule_semantic_frame()         [semantic_layer.py:95]   1ms，无LLM
│  产出: SemanticFrame {price_max=500, exclude=["日本"], skin="干皮"}
│
├─ 阶段2: SemanticParser.parse()        [semantic_layer.py:26]   LLM调用
│  ├─ LLM 语义解析                      含A2上下文快照
│  └─ _merge_rule_guards()              [semantic_layer.py:222]  ★规则+LLM取并集
│  产出: SemanticFrame {intent, constraint_edits, confidence}
│
├─ 阶段3: QueryBuilder.build()          [query_builder.py:15]    确定性编译
│  产出: RetrievalPlan {hard_constraints, soft_preferences, retrieval_query}
│
├─ 阶段4: AdaptiveRetriever.search()    [adaptive_retriever.py:57]
│  ├─ HybridRetriever                   [rag/fusion.py]          BM25+Dense+RRF
│  └─ Reranker                          [rag/reranker.py]        CrossEncoder+LLM
│  产出: 候选商品列表（Top-30 → 精排后）
│
├─ 阶段5: hard_filter + rank_products   [constraint_filter.py] + [ranker.py]
│  产出: Top-5 RankedProduct
  │
  ▼
流式输出 ProductCard（图片+价格+SKU+推荐理由）  [agent.py:205 stream_message]
```

**跟专家强调的三个核心设计**：

1. **规则+LLM 并行取并集**——不是"先规则后 LLM"或"规则兜底"，而是同时跑、取并集。硬约束（价格数字、品牌名）不会因 LLM 理解偏差而丢失。

2. **强类型数据管道**——从 `SemanticFrame` → `RetrievalPlan` → `RankedProduct`，全程 Pydantic Model，每一步可校验、可序列化、可回溯。这保证了评测时每一轮的中间状态都可以从 trace 中精确复现。

3. **约束跨轮累积 + 事务性编辑**——`apply_constraint_edits()` 支持 add/remove/relax 三种操作。用户说"不要日系"→ 加约束，说"算了"→ 减约束。不是每轮从零解析全量历史。

### 2.3 上下文控制层：A1 + A2（3 min）

**这是答辩的核心亮点，也是你论文/项目最有区分度的技术点。**

**技术要点**：

**A1 — 窗口截断**（`_recent_context_summary`）：
- 原理：将 LLM 注入的历史上下文限制在最近 [-3:] 或 [-6:] 个轮次
- 触发条件：基于真实 token 计数（tiktoken cl100k_base 近似）而非字符数
- 保护机制：当前轮用户消息永不被截断；受 25K token 硬上限保护

**A2 — 结构化快照**（`semantic_context_payload`）：
- 原理：4 项结构化字段独立于窗口截断，始终注入 LLM 上下文
  - `focus_product`：当前用户正在讨论的商品
  - `last_plan`：上一轮的检索计划（约束/偏好）
  - `pending_clarification`：待澄清项
  - `current_task`：当前任务描述
- 关键设计：即使 A1 截断了包含 focus_product 的历史轮次，结构化快照仍然保留

**两者协同机制**：
```
A1 控制"体积"：历史轮次由全量 → 最近 3-6 轮
A2 控制"结构"：关键状态字段独立于窗口，始终可见
A1 + A2 = 上下文体积可控 + 关键状态不丢失
```

**答辩话术**：
"上下文控制是最容易被忽视但实际最关键的一层。很多 Agent 项目把 prompt 拼接当成'工程细节'，实际上在 100+ 轮长会话中，不控制上下文体积 = 可控的定时炸弹——要么 token 成本线性增长、要么超出模型上下文窗口直接报错。

我的方案分两层：A1 做体积控制，A2 做结构保持。这两层合在一起，既控制了成本，又保住了关键状态。而且每个轮次的可控截断点在代码里是显式的，不依赖 LLM 自己做摘要——因为 LLM 摘要本身可能引入幻觉。"

### 2.4 决策复用层：B1 + B2（2 min）

**技术要点**：

**B1 — 语义记忆复用**（`RecommendationMemoryCache`）：
- 两级键：exact_key（相同 query 的精确匹配）+ semantic_key（embedding 近似匹配）
- 命中后跳过 `llm_selection`，回放 `short_response_summary` + `selected_products`
- 不受硬约束变化的影响（probe 阶段做 hard_filter 校验）

**B2 — 排序结果复用**（`StructuredMemoryCache`）：
- 键：`plan → hash`，复用检索 + 排序的完整结果
- 命中后跳过 planner + retriever + ranker 整条 pipeline

**免责声明（必须主动讲）**：
"决策复用层（B1/B2）的评估结果视为系统级边际效果，不是纯算法单变量。因为收益同时来自上下文减少、LLM 调用避免、回放路径短路三个因素。报告中已明示此 caveat。"

**答辩话术**：
"决策复用本质上是用存储换计算——把历史决策缓存下来，相似请求直接回放。但这里有几个坑：第一，缓存键必须能感知硬约束变化，否则用户改了预算你还返回旧结果；第二，缓存统计必须区分 'would_hit' 和 'effective_hit' 两个口径——在消融实验中 B1/B2 被禁用时 effective_hit 为 0，但我们要知道如果不禁用有多少能命中，所以加了 side-effect-free 的 probe API。"

### 2.5 评测体系：5-Condition 消融实验（2 min）

**技术要点**：

**Condition 矩阵**：

| Cond | A1 | A2 | B1 | B2 | 含义 |
|------|----|----|----|----|------|
| C0 | ✗ | ✗ | ✗ | ✗ | 全关 — baseline |
| C1 | ✓ | ✗ | ✗ | ✗ | 仅窗口截断 |
| C2 | ✓ | ✓ | ✗ | ✗ | 窗口+快照 |
| C3 | ✓ | ✓ | ✓ | ✗ | +语义记忆 |
| C4 | ✓ | ✓ | ✓ | ✓ | 全开（生产默认） |

**1100 轮会话脚本**：
- Phase A：100 商品 × 10 提问模板 = 1000 轮（跨 4 类目交替穿插）
- Phase B：跨商品横评 × 5 轮
- Phase C：长程指代（100+ 轮后回指）× 10 轮
- Phase D：对抗轮 × 75 轮（含糊指代/矛盾约束/跨类目切换/撤销/错指代攻击）
- Phase E：购物车交易 × 10 轮

**评分体系**（按 turn type 分桶）：
- retrieval → NDCG@5 / Recall@5
- followup_factual → 事实正确率（商品 JSON 真值校验）
- comparison → LLM judge 采样
- adversarial → 拒答正确率 / clarification 触发率

**LLM Judge 自适应折叠**：
- 独创设计：dry-run 阶段 3 次 judge → 计算分歧率
- 分歧率 <5%：pilot/full 降到 1 次（省成本）
- 5%≤分歧率<20%：保持 3 次平均
- 分歧率≥20%：标红，需人工决定（说明 provider 非确定性过大）

**答辩话术**：
"做评测最难的不是跑实验，而是设计一个评审自己都说服不了自己会出问题的实验。

这里有三个关键设计：
1. **C0-pre/post 分段**：C0（全关）必然在某一轮触发 token 溢出硬截断。所以我规定 C0 的前半段用于 A 层效果对比，后半段仅用于论证'无压缩不可行'。禁止用 C0-post 低分论证压缩效果好。
2. **LLM judge 自适应折叠**：用 LLM 评价 LLM 输出有争议。我的方案是先测分歧率，分歧率足够低才降调用次数。不预设 'temperature=0 就一定确定'。
3. **缓存隔离**：15 个独立 cache 目录（3 stage × 5 condition），加上独立进程 + hash 校验续跑，确保不同 condition 之间零交叉污染。"

---

## 3. 技术难点与解决过程（核心加分项）

> **这是答辩中最能体现思考深度的部分。不要被动等专家问"你遇到了什么困难"——在技术讲述中主动穿插。每个难点按照 "初始方案 → 遇到的问题 → 分析根因 → 最终方案 → 经验提炼" 的结构讲述。**

### 3.1 难点 1：上下文压缩不是"压缩"，而是"选择性注入"

**初始思路**：
最开始我把它叫做"上下文压缩"，思路是对历史对话做 LLM 摘要，把长历史压缩成一段短文。这是最直观的方案，跟 MemGPT 和 LongMem 的思路一致。

**遇到的问题**：
做了 prototype 后发现三个致命问题：
1. **LLM 摘要不可靠**：摘要可能遗漏关键信息（比如 20 轮前用户说过"我对酒精过敏"），而且摘要本身可能产生幻觉（错误记录用户偏好）
2. **无法做消融实验**：如果压缩是 LLM 摘要，那"关掉压缩"意味着什么？少调一次 LLM？还是不做摘要？无法对压缩本身的每一层做干净的消融
3. **调试不可审计**：当 Agent 在长会话中出错时，你无法回溯"当时上下文进了什么"——LLM 摘要是黑箱

**分析根因**：
"压缩"这个词本身就隐含了"有信息损失"的假设。回到第一性原理——我做上下文管理的真正目的是什么？不是压缩数据，而是**在有限的 token 预算内，把最重要的信息注入 LLM 上下文**。这个目标下，"选择性注入"比"压缩"更准确。

**重新设计**：
把"压缩"拆成两层独立的机制：

- **A1 窗口截断**：不是 LLM 摘要，而是**确定性规则**——只保留最近 N 轮。为什么可以这样？因为长会话中最近几轮的信息密度最高，远期的信息通过 A2 的结构化字段保留。这是**无损截断**（对保留的轮次完整保留），不是压缩。
- **A2 结构化快照**：4 个字段（focus_product / last_plan / pending_clarification / constraint_state）由状态机显式维护，**独立于窗口截断**。即使某轮因 A1 被截断了，它的关键状态仍然通过 A2 注入。

**关键洞察**：
"为什么不让 LLM 管记忆？因为 LLM 在信息管理这件事上天然不可靠——它会在记录记忆时产生幻觉。让确定性规则管理上下文，让 LLM 专注于推理任务。这是这个设计最核心的哲学——**不要让 LLM 管理它不可靠的东西。**"

**如果专家追问"那 A1 截断到底丢了多少信息？"**：
"好问题。这是我们设计消融实验的动机之一——通过 C0（全关）vs C1（仅 A1）的对比，量化截断的信息损失。从方法论上：C0-pre（截断前）和 C1 的 NDCG 差距，就是 A1 截断损失的上界。"

---

### 3.2 难点 2：消融实验中如何保证缓存不交叉污染

**初始思路**：
最简单的方式：每个 condition 跑之前清空缓存，跑完删除缓存目录。

**遇到的问题**：
仔细想后发现这个方案有多个漏洞：
1. **续跑场景**：如果在 C3 的 800 轮时崩了，重启后续跑——此时缓存已经积累了 800 轮的写入。如果清空缓存再续跑，这 800 轮的决策复用就丢失了（续跑的前 800 轮和崩溃前不一致）
2. **Stage 之间的污染**：dryrun 和 pilot 如果共用缓存目录，dryrun 写入的缓存会被 pilot 读到——但这两个阶段用的是同一个 session_id，缓存键会冲突
3. **内存态 vs 磁盘态**：StructuredMemoryCache 和 RecommendationMemoryCache 既有磁盘持久化又有内存 dict。如果同一个进程跑多个 condition（内存残留），前一个 condition 的内存缓存会泄漏到下一个

**分析根因**：
缓存隔离不是"清空不清空"的问题——是 namespace 设计问题。需要有足够多的维度来唯一标识"一段独立的实验会话"，确保不同阶段/条件/进程之间物理不可见。

**最终方案**：

```
隔离维度 = stage × condition × process
         = 3 × 5 × 1 = 15 个独立 namespace
```

具体措施：
1. **物理目录隔离**：`data/eval/long_session_2026-06-24/{stage}/cache_c{N}/`——3 stage × 5 condition = 15 个独立目录，互不可见
2. **session_id 带 stage 前缀**：`eval_dryrun_c2_2026-06-24` vs `eval_pilot_c2_2026-06-24`——防止 session_id 冲突
3. **独立进程**：每个 condition 独立进程，CLI 跑完即退出——消除内存泄漏风险
4. **fresh/resume 互斥**：CLI 强制 `--reset-cache` 和 `--resume` 二选一——首次启动清缓存，续跑不清，意图显式声明
5. **Pure Probe API**：would_hit 通过 `probe()` 拿，不调 `.get()`——即使不禁用缓存，也不会污染命中率统计

**为什么不用更简单的方案（比如每个 condition 跑之前全部清空）？**
"因为续跑。5500 轮不可能不中断——ARK 限流、网络抖动、进程 OOM 都可能中断。续跑时你必须保证缓存状态和中断前一致，否则续跑的前半段和后半段不是同一个实验条件。这就是为什么 fresh/resume 必须互斥：你要么从头开始（清缓存），要么精确续跑（不清）。没有'半清'的中间状态。"

---

### 3.3 难点 3：C0 baseline 的公平性——当 baseline 注定失败时怎么做对比

**初始思路**：
最自然的实验设计：C0（全关）vs C4（全开），看 C4 比 C0 好多少。

**遇到的问题**：
实际一跑就发现问题：C0 在 100+ 轮后必然触发 token 溢出——上下文体积线性增长，25000 token 的硬截断保护会强制丢弃历史。这时候 C0 的质量会断崖式下跌，但这不是因为"压缩好"——是因为 C0 被截断了。

如果直接用 C0 全量（包含截断后）和 C4 对比，相当于拿一个"已经被截肢的 baseline"来证明"完整的系统更好"——这在方法论上是作弊。

**分析根因**：
这里的关键问题是：C0 不是一个"公平的 baseline"，它是一个"不可行的 baseline"。在工程上，全量上下文注入在长会话中注定失败。用"失败后的 C0"来对比，会人为夸大其他 condition 的效果。

**最终方案**：
C0 分两段汇报：

- **C0-pre**：第 1 轮到首次触发 `degradation: "context_overflow_forced_trim"` 之前。**仅 C0-pre 用于与 C1/C2 对比 A 层质量影响。**
- **C0-post**：首次硬截断之后。**仅用于论证"无压缩工程上不可行"**，禁止用 C0-post 的低分论证"压缩提升质量"。

报告强制在"关键发现"章节写入此分段约束。

**这是我在实验设计上最满意的一个决策**——它承认了方法的局限性，同时给出了严谨的解决方案，而不是在结论里偷偷摸摸用不公平对比。如果专家追问实验设计的严谨性，这个例子是最有力的回击。

---

### 3.4 难点 4：LLM judge 的可靠性——"用 LLM 评价 LLM"的信任危机

**初始思路**：
直接调 ARK API，temperature=0，单次打分。

**遇到的问题**：
仔细想：temperature=0 到底能不能保证确定性？这取决于 provider 的实现——有些 provider 的 temperature=0 只是把 logits 的 softmax 温度设为极小值，但并行计算中的浮点累加顺序不确定性（GPU warp scheduling）仍然会导致 token 级别的不一致。

更重要的是——即使 LLM 每次给出一致的分数，这个分数本身可靠吗？LLM judge 有没有系统性偏差（比如倾向于给长回答高分）？

**分析根因**：
"LLM judge 不可靠"不是一个能完全解决的问题——它是一个需要被量化和管理的风险。

**最终方案**：
三层防御，不依赖"temperature=0 就确定"的假设：

1. **能不 judge 就不 judge**：8 类 turn type 中，5 类用规则评分（NDCG/Recall/事实校验/购物车对账）——只有 3 类（comparison / long_range_reference / adversarial）需要 judge 采样
2. **自适应折叠**：dry-run 阶段 3 次 judge → 计算分歧率 → 根据分歧率决定 pilot/full 的调用次数。这不是预设 temperature=0 可靠——是实测验证它是否可靠
3. **二元 rubric**：4 个维度每个只有 0/1，不让 judge 打"0.5 分"或"7/10 分"。二元判断的模糊空间比连续打分小得多

**如果专家追问"分歧率≥20% 怎么办"**：
"这是一个真实的风险。我在 spec 里写了——如果分歧率≥20%，需要在 dry-run summary 里标红，由人工决定：要么增加 judge 次数到 5 次取中位数，要么修改 rubric 让判断标准更具体，要么承认这个 turn type 不适合 LLM judge 并弃用。不会在分歧率过高的情况下硬拿 judge 分数做结论。"

---

### 3.5 难点 5：Rebase 后的 API 漂移——handle_message 签名变更

**背景**：
13 个 eval task 在 `feat/rag-eval-overhaul` 分支上开发了 19 个 commits。开发完成 merge 到 main 时，发现 main 上的 `handle_message` 签名已经从 `(self, request)` 变成了 `(self, user_id: str, request: ChatRequest)`——因为 main 上并行了 user-switching 功能，引入了 `user_id` 参数。

但 eval runner 的 `_invoke_agent()` 仍按旧签名调用 `agent.handle_message(request)`——如果直接跑 pilot，runtime 立即 TypeError。

**为什么这个问题值得讲**：
这看起来只是改一个参数，但背后反映的是真实工程中的常见问题——**并行开发的功能在 merge 时的接口不兼容**。如何处理这个问题，体现的是工程素养。

**解决过程**：
1. 我没有简单地"改一行代码"——而是分析了 `user_id` 在 eval 场景下的语义：eval 不是生产用户，不应该复用 `ANONYMOUS_USER_ID`
2. 设计了 `_eval_user_id = f"eval_{stage}_runner"`——确保 eval 数据在生产 session_store 中完全不可见
3. 这个 user_id 和 eval 的 session_id 命名空间一致（都带 stage 前缀），形成完整的隔离体系
4. 增加了单测验证 `handle_message` 被以正确签名调用

**经验提炼**：
"并行分支 merge 时的 API 漂移是真实风险。我的教训是：如果两个分支会修改同一个函数的签名，应该在开发阶段就做依赖声明（比如在接口上加 `**kwargs` 做向前兼容）——而不是等到 merge 后才发现。这也是为什么我现在写代码时会在关键函数签名上留扩展空间。"

---

### 3.6 难点 6：Cache Key 设计——精准 vs 泛化的平衡

**初始思路**：
B1（RecommendationMemoryCache）的 key = `(query, category, constraints)` 的 hash——相同 query + 类目 + 约束 → 命中缓存。

**遇到的问题**：
实际测试发现：
1. **过度精准**："推荐一款500以内的保湿精华"和"500以下保湿精华推荐"完全是两个 key——语义相同但字符串不同，缓存无法命中
2. **约束变更不可感知**：用户先问"推荐一款精华，500以内"→写缓存；后问"推荐一款精华，300以内"——如果只 hash query，两个不同预算的请求会错误命中同一个缓存

**分析根因**：
缓存 key 需要在两个维度上做平衡：
- **特异性**：key 要精确到能区分不同约束（不同预算不该命中同一缓存）
- **泛化性**：key 要模糊到能在语义相同表述变化时命中（"500以内"和"500以下"应该命中）

**最终方案**：两级 key + probe 校验

```python
# B1 的两级键
exact_key = hash(query + category + plan_hash)        # 完全相同 → 直接命中
semantic_key = hash(embedding(query) + category)      # 语义相似 → 候选命中

# 命中后不直接返回——先过 hard_filter 校验
def probe(plan, product_map):
    rows = self._items.get(key)
    for row in rows:
        product = product_map.get(row["product_id"])
        if product and hard_filter(product, plan.hard_constraints):
            return True    # 只有通过当前约束校验才确认命中
    return False
```

两级 key 解决泛化性：exact 匹配优先，semantic 匹配兜底。
probe + hard_filter 解决特异性：即使 semantic 命中了，也要过当前约束校验——预算变了就拒绝。

**如果专家追问"embedding 近似匹配会不会引入误差"**：
"会。所以我们设计了 probe() 中的 hard_filter 作为最后一道防线——embedding 相似只是 '候选命中'，必须通过硬约束校验才确认。另外我们也区分了 would_hit（probe 口径）和 effective_hit（实际命中口径），确保在消融实验中不会因为缓存命中口径不一致导致结论偏差。"

---

### 3.7 难点 7：1100 轮脚本的对抗轮设计——如何系统性地测试 Agent 的鲁棒性

**初始思路**：
1100 轮脚本 = 100 商品 × 10 种提问模板 + 一些额外测试。模板覆盖不同意图类型即可。

**遇到的问题**：
排完模板后发现一个盲区：所有模板都是"正常用户的正确使用方式"。真正的用户会：
- 说"那个"而不指明商品
- 说"要便宜的，但只买大牌"（自相矛盾）
- 突然从美妆切到数码
- 说"刚才说不要日系，现在算了"
- 指向一个从未推荐过的商品

如果不测试这些场景，评测报告只能说明"正常情况下的性能"，无法说明"对抗/边界情况下的鲁棒性"。

**分析根因**：
评测的完整性不是由轮次数量决定的——是由场景覆盖度决定的。1000 轮正常查询 + 0 轮对抗测试 ≠ 完整的鲁棒性评估。

**最终方案**：
在 1000 轮正常查询中**穿插** 75 轮对抗轮（不集中堆尾——避免 Agent "意识到"在测试）：

| 对抗类型 | 轮数 | 测试目的 |
|----------|------|----------|
| D1 含糊指代 | 15 | "那个/上一个"——上下文解析准确率 |
| D2 矛盾约束 | 10 | "便宜但大牌"——矛盾检测 + clarification 触发 |
| D3 跨类目切换 | 10 | 美妆→数码——状态重置速度 |
| D4 约束撤销 | 10 | "不要日系→算了"——约束编辑正确性 |
| D5 模糊主体 | 15 | "他/这款"——指代消解 robustness |
| D6 错指代攻击 | 15 | 指代不存在的商品——拒答正确率 |

穿插策略：每 15 个正常轮插入 1 个对抗轮，对抗子类型随机打散。

**关键洞察**：
"对抗轮的价值不在于'测试系统能不能崩溃'——而在于找到系统的脆弱边界。D2（矛盾约束）如果 Agent 不触发 clarification 而是硬选了一个结果，说明意图编译器缺少矛盾检测；D6（错指代攻击）如果 Agent 编造了一个商品，说明语义解析层缺少'不存在就承认不存在'的 guard。"

---

### 3.8 经验总结：做完这个项目我学到了什么

> **在技术讲述结束时、或 Q&A 被问到"你从项目中学到了什么"时，直接引述以下内容。**

1. **"压缩"不是目标，"选择性注入"才是**。命名决定了设计方向——从"上下文压缩"改名为"上下文控制"后，整个设计思路从"怎么减少信息"变成了"怎么保证重要信息不丢"。这个命名变更本身就是最重要的设计决策。

2. **消融实验的公平性比显著性更重要**。一个不公平的 baseline（C0-post）会污染所有结论。C0-pre/post 的分段约束是我在这个项目中最满意的设计决策。

3. **LLM 评测 LLM 需要自检机制**。不能预设 LLM judge 可靠——需要先在 dry-run 阶段测分歧率，再用实测数据决定下游策略。自适应折叠的设计哲学是：**不让假设替代实测**。

4. **缓存隔离的维度设计决定了实验可信度**。15 个独立 namespace 看起来有点 overengineer——但如果少一个维度（比如 stage 不分目录），就会出现 dryrun 的缓存泄漏到 pilot 的 bug，而这类 bug 极难排查。

5. **接口签名要留扩展空间**。handle_message 签名漂移的教训——如果一开始就写成 `(self, **kwargs)` 或者预留 `user_id=None` 的默认值，就不会有 merge 时的兼容性问题。

---

## 4. Q&A 预设库

### 4.1 评测方法论相关（核心防御）

#### Q1: "你怎么保证你评测结论的可信度？LLM judge 自己也是 LLM，这不就循环论证了吗？"

**回答策略**：

"这是一个很好的问题，也是我在设计评测体系时考虑最多的风险。我做了三层防护：

第一层：**能做规则评分的绝对不用 LLM judge**。retrieval 的 NDCG/Recall 是基于 ground truth ideal_top 计算；followup_factual 是基于商品 JSON 的真值校验；cart_action 是 CartService 末态对账。这 5 类 turn type 都不依赖 LLM judge。

第二层：**需要 LLM judge 的先用分歧率验证**。4 个二元维度（命中/流畅/无幻觉/未越权），dry-run 阶段每个采样 turn 调 3 次——如果 3 次打分不一致的比例（disagreement_rate）超过 20%，说明 provider 的非确定性过大，整个 judge 方案需要重新审视。低于 5% 才降为 1 次。

第三层：**judge prompt 版本化入库**（`prompts/long_session_judge_v1.md`），rubric 固定为 0/1 二元判断，不给 judge 评分自由度——要么对了要么错了，不允许打 0.5 分。

这三层加起来，我的态度是：LLM judge 是一个受限的、自检的、可复现的评估工具，不是一个黑箱裁判。"

#### Q2: "C0（全关）必然不如 C4（全开），你这实验设计不就是验证了一个已知结论？"

**回答策略**：

"这个问题有两个层面。

第一：C0 不是用来证明'压缩好'的——是用来证明'不压缩不可行'的。C0 的价值在于量化无压缩时的退化曲线：在哪一轮触发硬截断？截断前的质量（C0-pre）和 C1/C2 的差距是多少？这是工程上的边界测量。

第二：真正的科学贡献在逐层拆解。C0→C1 测 A1 的纯粹边际；C1→C2 测 A2 在 A1 之上的增量；C2→C3 测 B1 在 A1+A2 上的增量；C3→C4 测 B2 再往上叠加。这是一个累积消融矩阵，不是 A/B test。

类比：药物临床试验不会只设'不吃药 vs 吃复方药'两个组，而是会拆解每个成分的贡献。我做的就是这个拆解。"

#### Q3: "你的实验只有 100 个商品，行业级应用可能有百万级商品。你的结论能推广吗？"

**回答策略**：

"诚实讲：不能直接推广，但实验框架可以。

100 商品的约束是刻意为之——1100 轮 × 5 condition = 5500 轮的实验成本已经很高了（粗估 9+ 小时串行 + ~17000 次 ARK 调用）。如果上 10000 商品，成本增长不是线性的——每次检索的候选集变大，LLM selection 的 prompt 也变大，成本可能是指数级的。

但实验框架本身与商品数量无关：condition 矩阵的开关语义、命中率双口径、LLM judge 自适应折叠、断点续跑的 hash 校验——这些设计在百万级商品场景下同样适用。真正需要调整的是 context budget（从 25K 升到更大值）和 B1/B2 缓存的 key 设计（需要考虑商品更新导致的缓存失效策略）。"

### 4.2 架构设计相关

#### Q4: "为什么不用 LangChain / AutoGPT / CrewAI 这些框架？你的 Agent 和它们有什么区别？"

**回答策略**：

"我评估过 LangChain 和 AutoGPT，最终决定不用。原因：

1. **LangChain 的抽象成本太高**：它的 Chain/Agent/Tool 抽象层让简单的逻辑变得复杂，调试时 trace 很难穿透框架层。我的 Agent 只有 4 层（SemanticParser → Retriever → Reranker → Ranker），每层的输入输出都是强类型的 Pydantic Model，debug 时直接看 JSON。

2. **上下文控制是刚需，框架没解决**：LangChain 有 ConversationBufferMemory，AutoGPT 有 message history——但它们都没有我这种分层的上下文控制（A1 截断 + A2 快照）。在 100+ 轮长会话中，你需要精确控制什么进 LLM 上下文、什么不进。框架的黑盒 memory 做不到。

3. **工具调用是结构化路由，不是 ReAct loop**：AutoGPT 的 ReAct 模式是 'think → act → observe → think...'，每一轮可能多次 LLM 调用。我的 Agent 是 compiler-style：一次 SemanticParser 解析 → IntentCompiler 编译 → 路由到具体 tool → 执行。每轮 LLM 调用次数由 turn_type 和缓存命中情况决定，不是固定的 3-5 次 loop。

总结：框架适合快速原型，但当你需要精确的系统行为控制和分层的评测消融时，自己控制每层的输入输出是必要的。"

#### Q5: "你的 Reranker 为什么选 CrossEncoder + LLM 兜底，而不是全部用 LLM 或者全部用 CrossEncoder？"

**回答策略**：

"这是成本-延迟-效果的三维 trade-off：

- 全 CrossEncoder：快（<10ms）、免费，但在对比意图和复杂纠偏场景下效果不足——CrossEncoder 只能做 query-document 对的相关性打分，无法理解'用户刚才说不喜欢日系，现在说算了'这种约束撤销。
- 全 LLM：效果好，但慢（2-3s per rerank）+ 贵（每次 rerank 消耗 token）。
- 混合方案：用 CrossEncoder 覆盖 90% 的常规检索场景，LLM 仅在三种高价值场景触发（对比意图、低置信度、用户纠偏），同时 LLM 重排失败静默降级到规则打分。

三种场景触发的设计不是凭空想的——是从用户行为分析出发：这恰好是用户最在意推荐质量、最可能产生不满的场景。在这些场景下加 LLM 的边际收益最大。"

#### Q6: "你的上下文控制（A1+A2）本质上不就是 LongMem / MemGPT 的思路吗？有什么不同？"

**回答策略**：

"有本质区别。

MemGPT 的思路是让 LLM 自主管理自己的记忆——LLM 决定什么写入长期记忆、什么留在工作记忆。这引入了三个问题：(1) LLM 可能写入错误记忆（幻觉）；(2) LLM 记忆管理本身消耗 token；(3) 记忆管理行为不可控、不可审计。

我的方案是**显式规则驱动的上下文管理**：
- A1 窗口截断是基于轮次位置确定性截断，不依赖 LLM 判断
- A2 结构化快照是固定的 4 个字段，由状态机维护，LLM 不参与
- 每轮的 context 体积可以精确回溯（trace 中记录 context_payload_tokens）

核心哲学差异：MemGPT 说 '让 LLM 管理自己的记忆'，我说 '不要让 LLM 管理它不可靠的东西，用确定性规则管理上下文，把 LLM 的注意力留给真正需要推理的任务'。"

### 4.3 幻觉与可靠性相关

#### Q7: "你的 Agent 怎么防止幻觉？比如胡乱推荐不存在的商品、或者编造商品属性？"

**回答策略**：

"三层防护：

第一层（检索层）：Agent 只推荐从商品数据库中检索到的商品——它没能力'创造'商品。所有推荐的 product_id 必须来自 retriever 返回的候选集。

第二层（回答层）：Response 生成时，prompt 中带 `response_contract`——明确的回答模板和 forbidden 声明（如'不要编造价格'、'不要声称疗效'）。同时传入 `product_evidence`（商品的实际字段），约束 LLM 只能引用这些字段。

第三层（后处理层）：HallucinationChecker 对回答做后处理校验。如果检测到回答中引用的价格/成分/功效与商品 JSON 不符，触发 hallucination_corrected 事件，修正后重新输出。

另外，我的 trace 系统中 `branch_flags.fallback = 'hallucination_check'` 记录每一次幻觉修正事件，可以在评测报告中量化幻觉发生率。"

#### Q8: "ARK API 挂了怎么办？你的系统会怎样？"

**回答策略**：

"三个层面的容错：

1. **LLMClientWithBreaker**：接 circuit breaker 模式——连续失败 N 次后进入熔断状态，直接返回 fallback 文本而不是持续重试。

2. **FakeLLMClient**：开发和测试时可以用 FakeLLMClient 完全替代真实 LLM——它返回 rule-based 响应，确保即使没有 LLM 也能验证系统逻辑。

3. **retry + degradation 标记**：评测框架中每轮最多 retry 3 次（2s/4s/8s 指数退避），3 次都失败后打标签 `degradation: 'ark_failure_skip'`，trace 落盘，继续下一轮——不中断整个 session。

但在生产环境中，ARK API 完全不可用确实是单点故障——这是当前架构的已知局限。解决方案方向是引入 fallback model（如开源模型部署在本地 vLLM），这是后续的优化方向。"

### 4.4 工程实践相关

#### Q9: "你的测试覆盖率怎么样？怎么保证代码改动不出问题？"

**回答策略**：

"当前 504 个测试通过。测试分布在几个层次：

1. **单元测试**：每个模块的独立测试（agent、semantic_layer、memory_cache、ranker 等）
2. **集成测试**：API endpoint 测试 + WebSocket 测试
3. **评测专项测试**：56 个 long_session 相关测试（trace schema、runner fresh/resume、judge scoring、memory probe purity 等）

关键防护：
- **Trace Schema 校验**：JSON Schema 定义 30 个 required keys + 类型规则，每条 trace 行落盘后立即校验
- **断点续跑 hash 校验**：脚本/商品/条件配置的 sha256 指纹一致才允许续跑
- **Cache purity 测试**：probe() 连续调用 100 次，stats() 输出与 0 次完全一致"

#### Q10: "如果让你现在重新设计这个系统，你会改什么？"

**回答策略**：

"两个地方：

1. **SemanticParser 应该用 streaming parse**：当前是先完整解析 semantic frame 再路由到 tool。更好的方案是边解析边流式发送给下游——减少首字延迟，用户感知更好。

2. **预计算 embedding 应该上 GPU**：当前 bge-small-zh-v1.5 在 CPU 上做 embedding 推理，100 商品的向量构建约 2 秒。如果扩展到 10000 商品，需要用 GPU 批量推理 + 向量数据库（如 pgvector 或 Milvus）做 ANN 检索，不能 brute-force 余弦相似度。

但整体架构思路我不会改——分层的上下文控制 + 混合检索 + Reranker + 消融评测这套框架已经被证明是有效的。"

### 4.5 项目视野相关

#### Q11: "这个项目下一步你打算做什么？"

**回答策略**：

"按优先级排序：

1. **补齐 pilot readiness 的 4 个缺口**（handle_message 签名修复、token 计数抽取、tool_calls 解析、ARK 稳定性 smoke），启动 pilot 500 轮评测。这是接下来最重要的——没有真实数据支撑，所有理论分析都是空洞的。

2. **向量数据库迁移**：当前是 in-memory brute-force 检索，商品量上去后必须上 pgvector/Milvus。

3. **个性化推荐**：当前完全是 session-level 的上下文推荐。引入 user-level 的偏好学习后，B1 语义记忆缓存可以从 session 级扩展到 user 级。

4. **多模态输入**：客户端已经有语音输入（豆包 STT），下一步可以加图片输入——用户拍照问'这件衣服搭什么裤子'，需要视觉 + 文本的多模态 RAG。"

---

## 5. 关键数字速查表

| 指标 | 数值 |
|------|------|
| 数据集商品数 | 100（4 类目 × 25） |
| 类目 | 美妆护肤 / 数码电子 / 服饰运动 / 食品生活 |
| 后端模块数 | ~80 个 Python 文件 |
| 测试通过数 | 504 passed |
| LLM API | 豆包 ARK（Doubao Pro, ep-20260514111645-lmgt2） |
| Embedding 模型 | bge-small-zh-v1.5（本地 CPU） |
| Reranker 模型 | BGE-reranker-v2-m3（CrossEncoder，本地） |
| 评估条件数 | 5（C0-C4）× 3 stage |
| 评估总轮次 | 5500（1100 × 5 condition） |
| 每轮 LLM 调用 | ~2-3 次（非固定，依赖 turn_type + 缓存命中） |
| C0 硬截断 token 上限 | 25000（5 个开关配置之一） |
| Cache 隔离目录 | 15 个（3 stage × 5 condition） |
| 对抗轮次 | 75（6 种类型） |
| LLM judge 维度 | 4（命中/流畅/无幻觉/未越权） |
| Trace 字段数 | 30+（schema validated） |
| 断点续跑 hash 数 | 4（script/product/condition + meta） |
| Dry-run smoke | 13 真实 ARK 调用，0 失败 |
| 端到端延迟 | 4.3-6.6 秒/turn（实测） |
| Android APK | `client/app/build/outputs/apk/debug/app-debug.apk` |

---

## 6. 答辩当日 Checklist

### Demo 前
- [ ] 后端已启动并确认 `/health` 返回 200
- [ ] Cloudflare tunnel 或 adb reverse 已测试连通
- [ ] Android APK 已安装并能正常连接后端
- [ ] 聊天历史已清空（干净 session）
- [ ] 准备好截图 backup（防止 Live Demo 出问题）
- [ ] 环境变量 `ARK_API_KEY` 已设置

### 技术讲述
- [ ] 架构图可展示（白板或幻灯片）
- [ ] 5 个 condition 矩阵表可展示
- [ ] 关键数字熟练（见 §5 速查表）
- [ ] 每层技术点的 2-3 句精炼话术已记熟

### Q&A
- [ ] Q&A 预设库过一遍（至少 §4.1 评测方法论 3 个问题）
- [ ] 弱点诚实承认 + 讲清已有处理（C0-post、B1/B2 caveat、LLM judge 分歧率）
- [ ] 准备好"如果重做会改什么"的答案

### 心态
- [ ] 被追问 = 好事，说明专家感兴趣
- [ ] 不知道就说不知道 + 给一个思考方向
- [ ] 每个答案尽量带量化数据支撑
- [ ] 不要过度防御——这是求职面试，展示学习能力和思考深度比"全对"更重要

---

*本文档在答辩当日使用。Commit: `docs/superpowers/specs/2026-06-25-defense-preparation.md`*
