# SoulDance ShopGuide Agent 比赛技术说明

## 1. 项目概述：从商品问答到可验证导购决策流

SoulDance ShopGuide 是一个面向电商导购场景的多轮智能导购系统。它的目标不是把商品信息检索出来后交给大模型自由回答，而是把真实购物对话中的模糊表达、多轮追问、反选排除、评论噪声、缓存复用和购物动作，统一编排成一个可验证、可交互、可加速的导购决策流程。

真实导购里，用户很少用标准搜索词表达需求。他们会说：

```text
想要一个化妆的，送给妈妈
更贵一点
不要这个品牌
第一款和第三款怎么选
就这个来两件
```

这些表达背后包含了类目理解、送礼场景、价格方向、品牌反选、商品引用、对比决策和购物车动作。普通 RAG 问答如果只是“检索商品 -> 把商品和评论塞给 LLM -> 生成回答”，很容易出现以下问题：

- 上下文继承错误：用户换了购物对象，系统还沿用上一轮任务。
- 商品卡不可信：LLM 文本主推一个商品，客户端商品卡却展示另一个商品。
- 约束被绕过：用户说不要某品牌、不要酒精、预算 4000 以内，结果仍出现违规商品。
- 评论证据污染：手机商品里混入食品评论，或者护肤商品里负面风险被正向文案盖掉。
- 性能不可控：相同问题重复走完整检索、排序和 LLM selection，响应变慢。

因此，ShopGuide 的核心不是“让大模型多说几句导购话”，而是把自然语言购物需求转成结构化、可复核、可落地的购物决策。

## 2. 核心问题：真实导购为什么不能只靠普通 RAG

真实电商导购至少同时面对四类问题。

第一，用户表达不标准。`化妆的` 需要识别成美妆护肤，`电脑` 在当前商品库里默认对应笔记本电脑，`鞋` 又不能强行映射成某一种鞋，而要根据用途继续澄清。

第二，对话跨轮发生。用户会先说 `我要华为手机`，下一句说 `不要华为，换一款`；也会先问电脑，下一句说 `我想要鞋`。系统必须判断这一轮是补充条件、商品追问、澄清回答，还是新购物任务。

第三，商品证据嘈杂。商品描述、FAQ 和评论都可以作为证据，但不是所有文本都适合进入推荐理由。`物流快` 对拍照手机帮助有限，`好吃` 出现在手机评论里应被忽略，`刺痛/泛红` 出现在敏感肌面霜评论里则要作为风险保留。

第四，推荐结果必须可信。LLM 可以参与理解和表达，但不能自由生成商品 ID，不能绕过价格、品牌、类目、成分等硬约束，也不能控制购物车状态。

ShopGuide 将这些问题合并成一个工程目标：

```text
真实导购 = 多轮语言理解 + 商品决策 + 可信证据 + 可执行动作
```

## 3. 整体方案：把导购拆成连续决策流程

ShopGuide 将一次导购拆成连续阶段：

```text
理解需求
-> 维护任务
-> 检索召回
-> 约束过滤
-> 证据治理
-> 候选决策
-> 最终校验
-> 交互输出
```

主链路使用豆包 Ark OpenAI-compatible API。LLM 参与三件事：

- 语义理解：把用户自然语言解析成结构化意图和约束。
- 候选内选择：只在后端候选池里选择已有 `product_id`。
- 自然语言表达：基于最终商品和证据摘要生成简短导购结论。

后端负责：

- Session 任务状态。
- taxonomy 类目解析。
- 预算、品牌、类目、成分、价格上下限等硬约束。
- RAG 检索、排序和证据治理。
- cache 命中安全校验。
- 购物车状态机。
- 商品卡最终准入。
- WebSocket / REST 事件协议。

完整链路如下：

```text
用户输入
  -> LLM 语义理解：推荐 / 追问 / 反选 / 对比 / 购物车 / 闲聊
  -> Session 任务状态：current_task / focus_product / pending_clarification / pending_recovery
  -> RetrievalPlan：类目、预算、品牌、成分、软偏好
  -> Memory Router：尝试复用结构化推荐决策
  -> RAG 召回：BM25 / BGE embedding
  -> Hard Filter：预算、品牌、类目、成分、价格上下限
  -> EvidenceBundle：support / risk / ignored
  -> LLM Candidate Selection：候选池内选择 product_id
  -> Backend Final Validation：复核商品合法性、主推一致性、数量上限
  -> 输出事件：文本、商品卡、澄清、恢复、对比、购物车、语音
```

这个流程保证了两件事：大模型有足够语义能力理解真实用户表达，后端又能对商品和动作做最终裁决。

## 4. 一次请求如何被处理

以用户输入为例：

```text
推荐一款手机，预算4000，拍照优先
```

系统首先通过 LLM semantic parser 判断这是商品推荐请求，并提取结构化信息：

```json
{
  "intent": "recommend_product",
  "constraint_edits": {
    "add": {
      "sub_category": "智能手机",
      "price_max": 4000,
      "soft_preferences": {
        "priority": "拍照"
      }
    }
  }
}
```

这一步只描述“用户想要什么”，不决定最终推荐哪款商品。

随后后端把语义结果写入 session 状态，并生成 `RetrievalPlan`：

```text
category = 数码电子
sub_category = 智能手机
price_max = 4000
soft_preferences.priority = 拍照
retrieval_query = 手机 拍照 预算4000
```

在检索前，系统先经过 Memory Router。如果相同或兼容的结构化推荐决策已经存在，就尝试复用缓存；如果没有命中，再进入 RAG 检索和排序。

检索后，后端执行 hard filter，过滤掉预算外、类目不符、品牌或成分不符合要求的商品。随后 EvidenceBundle 对商品内部评论、FAQ 和描述做内容级治理，计算哪些证据支持当前需求，哪些是风险，哪些与当前需求无关。

然后 LLM Candidate Selection 只在候选池内选择商品。它输出的是结构化 JSON，而不是自由文本：

```json
{
  "should_recommend": true,
  "need_clarification": false,
  "selected_product_ids": ["p_xxx", "p_yyy"],
  "reasons": {
    "p_xxx": "匹配拍照优先，价格在预算内",
    "p_yyy": "作为更高性价比备选"
  }
}
```

后端再次校验：

```text
product_id 必须来自候选池
商品必须存在
商品必须满足 hard filter
商品数量最多 4 个
第一张商品卡必须是唯一 primary
```

最后 Response Writer 基于最终允许的商品和证据摘要生成简短导购文本，WebSocket 再输出标准事件：

```text
assistant_state
text_delta
assistant_state(selection)
text_delta
products_start
product_item
products_done
quick_actions
done
```

`product_item` 的语义是最终可见商品卡，不是 RAG 候选。

## 5. LLM 的角色与边界

ShopGuide 当前主链路使用豆包 Ark OpenAI-compatible API。系统中没有让 LLM 直接做全局 planner，也没有让 LLM 直接操作购物车或生成可展示商品卡。

LLM 在系统里有三个受控角色。

### 5.1 语义理解

Semantic prompt 负责把自然语言解析成结构化 IR，包括：

```text
intent
constraint_edits
query_intent
cart_operation
references
response_goal
clarification_question
```

它可以识别：

```text
推荐商品
商品 follow-up
品牌反选
价格方向
结构化对比
购物车动作
闲聊 / 不明确输入
```

后端 rule guard 会补齐硬约束，例如 `不要酒精`、`不要 Apple`、`10000以上`、`4000以内`。这样即使 LLM 漏掉关键约束，后端仍会保留安全边界。

### 5.2 候选池内选择

Selection prompt 只接收后端筛出的候选商品。LLM 只能返回候选里的 `product_id`，不能编造商品，也不能选择候选池外的商品。

后端会丢弃以下结果：

```text
候选池外 product_id
不存在的 product_id
违反预算的商品
违反品牌排除的商品
违反类目/子类目的商品
违反成分排除的商品
```

因此 LLM selection 是候选池内 reranker，而不是自由推荐器。

### 5.3 自然语言表达

Response prompt 接收的是最终商品和摘要证据：

```text
allowed_products
selected_primary
hard_constraints_applied
review_summary
forbidden_claims
```

它只能生成 `text_delta`，不能修改：

```text
product_item
商品价格
商品顺序
购物车
事件类型
hard filter 结果
```

如果 LLM 文案把备选商品写成主推，后端会回退到确定性文案，保证文本主推和商品卡 primary 一致。

## 6. Cache：缓存可验证决策，而不是缓存最终回答

ShopGuide 的 cache 设计服务于导购可信性，而不是简单保存 LLM 回复全文。

普通回答缓存通常是：

```text
query -> final answer text
```

这种方式在导购场景有风险：用户上下文变化、预算变化、品牌排除变化、商品库存或价格变化时，旧回答会失去适用边界。

ShopGuide 缓存的是结构化导购决策：

```text
query + taxonomy + hard_constraints + soft_preferences
-> selected_product_ids + roles + reasons + short_response_summary
```

### 6.1 Recommendation Memory

Recommendation Memory 是高层缓存，缓存最终推荐决策。

缓存内容包括：

```text
normalized_query
taxonomy
hard_constraints
soft_preferences
selected_product_ids
roles
reasons
short_response_summary
catalog_fingerprint
prompt_version
```

命中条件包括：

```text
query 规范化后一致或高度兼容
taxonomy 一致
hard constraints 一致
soft preferences 兼容
商品仍存在
当前请求不是 product_followup
```

命中后可以跳过：

```text
retriever
ranker
LLM product selection
```

但不会跳过：

```text
product_id 存在性校验
taxonomy 校验
hard filter
最终商品卡事件渲染
```

### 6.2 Structured Rank Cache

Structured Rank Cache 是低层缓存，缓存 `RetrievalPlan -> RankedProduct` 的排序结果。

cache key 包含：

```text
intent
retrieval_mode
category
sub_category
price_min
price_max
include_brands
exclude_brands
exclude_terms
exclude_brand_regions
soft_preferences
retrieval_query
```

因此下面两个请求不会共用缓存：

```text
推荐防晒霜，不要酒精
推荐防晒霜，酒精可以接受
```

它们的 hard constraints 不同，必须走不同决策路径。

### 6.3 可观测性

WebSocket `assistant_state` 会暴露：

```text
memory_mode = miss / exact_hit / semantic_hit / disabled_for_followup
```

`/health` 会返回：

```text
memory_cache
recommendation_memory
structured_rank_cache
```

这个设计可以概括为：快，但不乱快。缓存提升速度，但每次命中后仍要重新通过商品和约束校验。

## 7. 数据治理与 EvidenceBundle

ShopGuide 的商品数据来自本地电商商品库，统一加载为结构化 schema：

```text
product_id
title
brand
category
sub_category
price
image_path
skus
marketing_description
faqs
reviews
brand_region
extracted_terms
review_rating
```

系统启动时会从真实商品数据构建 taxonomy，并维护 alias。

类目 alias 示例：

```text
手机 -> 智能手机
电脑 -> 笔记本电脑
跑鞋 -> 跑步鞋
化妆 / 化妆品 / 彩妆 -> 美妆护肤
鞋 -> 服饰运动泛类目
```

品牌 alias 示例：

```text
华为 / HUAWEI
苹果 / Apple
小米 / Xiaomi
荣耀 / HONOR
耐克 / Nike
```

### 7.1 为什么不提前删除无关评论

无关评论是否无关，依赖当前用户需求。

同一句评论对不同需求会有不同作用。例如：

```text
“机身偏重”
```

对于拍照优先用户，它可能只是轻微风险；对于轻薄便携用户，它是强风险。因此系统不在入库前静态删除评论，而是在运行时按当前需求治理证据。

### 7.2 EvidenceBundle 内容级 reranker

系统将商品描述、FAQ 和评论切成 evidence chunks，再根据当前需求分成：

```text
support_chunks   支持当前推荐的证据
risk_chunks      风险、负面反馈或约束冲突
ignored_chunks   与当前需求无关或跨类目噪声
```

示例一：用户要拍照手机。

```text
夜拍清晰 / 抓拍快 / 影像旗舰 -> support_chunks
物流快 / 包装好 -> 不作为强推荐证据
好吃 / 入口香甜 -> ignored_chunks
```

示例二：用户要敏感肌面霜。

```text
温和 / 修护屏障 / 舒缓 -> support_chunks
刺痛 / 泛红 / 过敏 -> risk_chunks
```

默认商品卡不会返回 raw evidence，只返回结论型 reason 和商品基础信息。用户主动问“为什么推荐”“评论怎么说”时，系统才基于内部 EvidenceBundle 输出更详细解释。

## 8. 导购动作如何落到统一交互协议

ShopGuide 不只返回一段文本，而是将导购动作统一成客户端可渲染的事件协议。

系统支持：

```text
推荐商品
主动澄清
无匹配恢复
商品 follow-up
品牌反选
结构化对比
自然语言购物车
语音输入
语音播报
```

多轮上下文不是简单保存 `last_message`，而是保存：

```text
current_task
constraint_state
focus_product_id
last_recommendations
context_events
pending_clarification
pending_recovery
cart_memory
```

因此系统可以判断：

```text
更贵一点        -> 对当前 focus 商品做价格方向 follow-up
我要鞋          -> 新购物任务
稳妥不踩雷      -> 上一轮澄清问题的回答
不要这个品牌    -> 排除当前主推商品品牌
第一款和第三款  -> 引用最近可见推荐集
就这个来两件    -> 购物车加购当前主推商品，数量为 2
```

## 9. 多模态语音能力

ShopGuide 支持语音输入和语音播报，语音能力通过 adapter 接入导购链路。

语音输入链路：

```text
用户语音
-> /api/stt
-> STTAdapter
-> 识别文本
-> 标准导购链路
```

语音播报链路：

```text
导购文本
-> TTSAdapter
-> 语音合成服务
-> 音频事件 / 音频结果
```

相关配置：

```text
STT_ENABLED
STT_PROVIDER
STT_BASE_URL
STT_AUDIO_FORMAT
STT_SAMPLE_RATE

TTS_ENABLED
TTS_PROVIDER
TTS_BASE_URL
TTS_DEFAULT_VOICE
TTS_RESPONSE_FORMAT
```

语音并不改变商品决策逻辑。它复用同一套语义理解、检索、证据治理、候选选择、最终校验和事件输出流程。

## 10. 工程实现

### 10.1 技术栈

后端：

```text
Python 3.12
FastAPI
Uvicorn
WebSocket streaming
Pydantic v2
HTTPX
OpenAI-compatible SDK
Pytest
```

LLM 与检索：

```text
豆包 Ark OpenAI-compatible API
BM25
BGE small zh embedding
Sentence Transformers
jieba
rank-bm25
```

语音：

```text
STTAdapter
TTSAdapter
Doubao ASR / TTS compatible configuration
Qwen3-TTS compatible configuration
```

### 10.2 依赖环境

后端环境：

```text
env/venv_shopguide_backend
```

语音模型环境：

```text
env/venv_vllm_cu128
env/conda_gcc12
```

核心依赖：

```text
fastapi
uvicorn
openai
httpx
websockets
pydantic
numpy
jieba
rank-bm25
sentence-transformers
pytest
pytest-asyncio
python-multipart
```

### 10.3 配置说明

比赛演示主链路使用豆包 Ark：

```bash
LLM_PROVIDER=doubao
ARK_API_KEY=运行时密钥
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/
ARK_MODEL=ep-20260514111645-lmgt2
```

Embedding：

```bash
USE_EMBEDDING=1
EMBEDDING_MODEL_DIR=model/bge-small-zh-v1.5
EMBEDDING_DEVICE=cuda:0
```

Session、购物车和缓存：

```bash
SHOPGUIDE_SESSION_DIR=data/sessions
SHOPGUIDE_CART_PATH=data/carts.json
SHOPGUIDE_MEMORY_CACHE_PATH=cache/shopguide_memory.jsonl
```

语音：

```bash
STT_ENABLED=true
STT_PROVIDER=doubao_ws
STT_BASE_URL=http://127.0.0.1:18090

TTS_ENABLED=true
TTS_PROVIDER=doubao_chunked_v3
TTS_BASE_URL=http://127.0.0.1:18880
```

API key 只通过运行时环境变量注入，不写入源码、文档、缓存或日志。

### 10.4 目录结构

```text
backend/app/
  main.py                 FastAPI 入口，REST/WebSocket API
  agent.py                ShopGuide Agent 编排主链路
  intent_compiler.py      LLM 语义理解入口
  semantic_layer.py       语义 IR、fallback、安全 guard
  state_reducer.py        session 状态更新
  query_builder.py        RetrievalPlan 构建
  taxonomy.py             类目解析与 alias 映射
  ranker.py               商品排序
  knowledge_base.py       EvidenceBundle 与证据处理
  memory_cache.py         推荐缓存与检索缓存
  reference_resolver.py   多轮引用解析
  constraint_filter.py    预算、品牌、成分硬过滤
  cart.py                 购物车状态机
  stt_adapter.py          STT 接口适配
  tts_adapter.py          TTS 接口适配
  prompts/                semantic / selection / response prompt

tests/
  test_agent_core.py      Agent 核心行为测试
  test_api.py             REST/WebSocket 测试
  test_stt_adapter.py     STT 适配测试
  test_tts_adapter.py     TTS 适配测试

docs/
  interaction_protocol.md
  semantic_layer.md
  compiler_style_agent_architecture.md
  rag_memory_reranker_impl.md
  stt_deployment.md
```

## 11. API 与事件协议

### 11.1 REST API

```text
GET  /health
GET  /api/products
GET  /api/products/{product_id}
POST /api/debug/retrieval_plan
GET  /api/debug/session
GET  /api/debug/sessions

GET  /api/cart
POST /api/cart/add
POST /api/cart/update_quantity
POST /api/cart/remove
POST /api/cart/clear
POST /api/cart/checkout

POST /api/stt
POST /api/feedback
```

### 11.2 WebSocket API

入口：

```text
/ws/chat
```

请求示例：

```json
{
  "type": "user_message",
  "session_id": "demo_001",
  "message": "推荐一款手机，预算4000，拍照优先",
  "input_type": "text",
  "tts_enabled": false
}
```

主要事件：

```text
assistant_state          当前阶段、intent、retrieval_mode、memory_mode
text_delta               流式文本
clarification_request    主动澄清问题
filter_recovery_options  无匹配恢复选项
products_start           商品卡开始
product_item             最终可见商品卡
products_done            商品卡结束
quick_actions            快捷追问按钮
comparison_result        结构化商品对比
cart_update              购物车更新
done                     本轮结束
```

商品卡结构：

```json
{
  "type": "product_item",
  "role": "primary",
  "product": {
    "product_id": "p_xxx",
    "name": "商品名称",
    "brand": "品牌",
    "category": "美妆护肤",
    "sub_category": "精华",
    "price": 300,
    "main_image_url": "/assets/products/...",
    "tags": ["美妆护肤", "精华", "中国"],
    "reason": "匹配送礼场景，口碑稳妥"
  }
}
```

正式商品卡不返回 raw evidence。默认只返回商品基础信息、图片、价格、标签和短 reason。

## 12. 测试验证

核心测试命令：

```bash
env/venv_shopguide_backend/bin/python -m pytest tests/test_agent_core.py tests/test_api.py -q
```

当前核心后端测试覆盖：

```text
LLM semantic parse
LLM candidate selection
商品卡事件顺序
动态推荐数量
预算上下限
品牌 include / exclude
成分排除
多轮 follow-up
任务切换
pending clarification
pending recovery
结构化对比
购物车操作
memory cache
EvidenceBundle rerank
无关评论抗干扰
商品图片 URL
STT / TTS adapter
```

核心回归测试确保：

```text
商品卡不会在 LLM selection 前发送
product_item 只代表最终可见商品
LLM 不能选择候选池外商品
cache 命中不绕过 hard filter
文本主推和商品卡 primary 一致
无匹配需求不会乱推无关商品
```

## 13. 关键问题解决方案

### 13.1 `化妆的送妈妈` 不再落到食品礼盒

问题：用户说 `想要一个化妆的，送给妈妈`，系统如果只识别到 `送礼/妈妈`，就会沿泛礼物方向推荐，容易出现食品礼盒。

解决：

```text
化妆 / 化妆品 / 彩妆 -> 美妆护肤
recipient = 长辈
occasion = 送礼
```

因此系统会在美妆护肤大类内推荐适合作为礼物的商品，不会跳到食品或服饰。

### 13.2 `不要华为` 不再返回 HUAWEI

问题：用户先要华为手机，再说 `不要华为，换一款`，如果品牌别名不统一，系统会把 `华为` 和 `HUAWEI` 当成不同品牌。

解决：

```text
华为 / HUAWEI -> canonical brand
exclude_brands 写入 hard constraints
follow-up 重新 hard filter
```

商品卡发送前必须再次通过品牌过滤。

### 13.3 `更贵一点` 不跨类目

问题：用户在美妆任务后说 `更贵一点`，系统不能跳到服饰或食品。

解决：

```text
follow-up 默认继承上一轮 category/sub_category
更贵/更便宜只是相对 focus 商品的价格方向
无明确新类目时禁止跨类目漂移
```

### 13.4 文本主推和商品卡 primary 一致

问题：LLM 文案存在表达漂移风险，可能把备选 A 写成主推，但商品卡 primary 是 B。

解决：

```text
final_selected_products[0] 是唯一 primary
selected_primary、focus_product_id、product_item.role=primary 指向同一商品
LLM 文案漂移时回退到确定性文案
```

### 13.5 无关评论不进入推荐证据

问题：评论数据中会混入无关内容，例如手机商品出现 `好吃、入口香甜`。

解决：

```text
原始评论保留
运行时按当前需求切 evidence chunks
无关评论进入 ignored_chunks
response writer 只接收摘要证据
```

### 13.6 cache 命中不绕过 hard filter

问题：缓存如果直接复用最终回答，会导致预算或品牌约束失去校验边界。

解决：

```text
缓存结构化决策，不缓存最终长回答
命中后重建商品对象
重新执行 taxonomy 和 hard filter
再输出标准 product_item
```

## 14. 项目亮点 / 创新点

### 14.1 动态证据治理

ShopGuide 不只是召回商品，还对商品内部评论、FAQ 和描述做 evidence chunk 分级。系统根据当前用户需求动态划分 `support / risk / ignored`，既能抵抗无关评论注入，又能保留对用户重要的负面风险。

### 14.2 结构化导购决策缓存

系统缓存的是 `selected_product_ids`、taxonomy、constraints、reason 和 summary，而不是 LLM 最终回答文本。缓存命中后仍重新执行商品存在性、类目和 hard filter 校验，在提升速度的同时保证推荐安全。

### 14.3 事件化导购协议

推荐、澄清、恢复、对比、购物车和语音都通过统一 REST/WebSocket 协议输出。客户端不需要理解 RAG 中间状态，只消费最终可渲染事件，因此系统更接近真实导购产品，而不是只返回一段聊天文本的 demo。
