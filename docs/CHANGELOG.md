# 更新日志 (CHANGELOG)

## v2.0 — 事实锚定管道 (Fact-Grounded Pipeline)

### 概述

v2.0 核心升级聚焦于消除 LLM 幻觉、增强跨轮一致性、提升中文分词精度，以及简化内部链路架构。所有改动对现有 API 用户无破坏性影响，WebSocket 协议、REST 端点、事件类型均保持不变。

---

### 解决的问题

#### P0: LLM 幻觉导致虚构商品

**症状**: AI 编造不存在的商品型号和虚假价格。例如用户询问手机推荐，LLM 回复"小米 17 Max ¥6499"，而数据库中实际无此商品。

**根因**: LLM 在生成推荐文本时没有强制绑定到数据库中的真实商品。模型基于训练数据中的模式自由生成，缺乏外部事实约束。

**修复**: 引入事实锚定管道，由两个核心模块组成：

- **FactContextBuilder** (`fact_context.py`): 构建 `[[product_id]]` 锚点事实表，将所有可引用商品的 ID、名称、价格、品牌、规格等结构化事实注入 LLM 上下文。该事实表成为 LLM 生成推荐文本的唯一商品信息来源。
- **AnchorValidator** (`anchor_validator.py`): 流式循环状态机，在 LLM 逐 chunk 输出的过程中实时校验每个 `[[product_id]]` 锚点引用。校验对普通文本零延迟通过，仅在遇到锚点标记时执行数据库验证。若校验失败，立即中止流式输出并回退到安全回复。

**影响**: LLM 再也不能编造商品。所有推荐必须通过事实表引用真实商品 ID，非法 ID 在流式输出阶段即被拦截。

---

#### P1: 前后回答矛盾

**症状**: 同一轮对话中，LLM 先说"未找到该产品"，随后在同一回复的推荐列表中又列出该产品；或多轮对话中前后推荐结论互相冲突。

**根因**: 缺乏跨轮事实一致性校验机制。LLM 每次生成独立地基于当前 prompt 采样，无记忆上次已否认或不存在的查询。

**修复**: 引入 **ConsistencyTracker** (`consistency_tracker.py`)，提供两层保护：

- **Denial cache（否认缓存）**: 记录 LLM 已声明不存在的查询。后续轮次中，若检索系统再次命中同一商品，直接过滤，不再出现于推荐列表。
- **Focus drift 检测**: 监控对话焦点是否在相邻轮次之间发生无声明漂移。检测到漂移时写入提示词，引导 LLM 显式说明立场变化。

**影响**: 同一商品不会在同一会话中既被否认又被推荐，对话立场可追溯。

---

#### P2: 上下文丢失

**症状**: 服务异常或降级后，要求用户重新输入已确认的信息（如偏好、预算、已选择的商品），体验割裂。

**修复**: 实现 3 阶段 Session Checkpoint（`session_store.py` 新增 `checkpoint()` / `recover()` 方法）：

| 阶段 | 触发时机 | 保存内容 |
|------|---------|---------|
| Turn Start | 每轮对话开始 | 当前查询意图、用户偏好快照 |
| Post-Retrieve | 检索完成后 | 检索结果、匹配商品列表 |
| Turn End | 每轮对话结束 | 已确认事实、已推荐商品、对话摘要 |

同时，`degradation.py` 中所有 fallback 提示文案升级为上下文感知：当从 checkpoint 恢复时，降级提示会引用用户已确认的信息（如"根据您之前确认的偏好……"），而非冷启动。

**影响**: 服务降级后不再要求用户重复输入，恢复时自动引用已确认的上下文。

---

#### P3: CJK-ASCII 分词断裂

**症状**: 用户输入"小米17Max"无法匹配数据库中的"小米 17 Max"。搜索返回空结果或无关联商品。

**根因**: jieba 分词器将"17Max"识别为一个连续 token，而数据库商品标题中"17"和"Max"被空格分隔为两个独立 token。中文与 ASCII 字符、数字与字母之间的边界未被词法层面处理。

**修复**: 在 `embedding_retriever.py` 中新增 `_normalize_cjk_ascii()` 预处理函数，在以下边界自动插入空格：

- CJK 字符与 ASCII 字符之间（如 `小米17` → `小米 17`）
- 数字与字母之间（如 `17Max` → `17 Max`）

该预处理同时应用于用户查询分词和数据库标题索引，确保两端 token 化一致。

**影响**: 中英文混合、数字型号等常见用户输入格式可正确匹配数据库商品。

---

#### P4: Product Analysis 命中但不告知 LLM

**症状**: ProductMatcher 正确匹配了商品，但 LLM 仍然回答"库中无此商品"。匹配结果在管道中途丢失，未到达 LLM。

**根因**: 匹配结果没有注入到 LLM prompt 中。LLM 仅收到原始用户消息，对匹配结果毫不知情。

**修复**: `product_analysis.py` 中，当商品命中时，将结构化商品事实（名称、价格、品牌、规格）构造为 `enriched_message`，直接注入 LLM prompt，作为 LLM 生成回复的必读上下文。

**影响**: ProductMatcher 命中后 LLM 能正确引用匹配结果，不再出现"命中但回答没有"的情况。

---

### 架构升级

#### 链路简化：LLM 调用 3 次 → 2 次

删除 `IntentCompiler`（LLM 语义解析路径），将意图解析从独立 LLM 调用改为基于规则 + 检索反馈的 UnifiedPlan 计算，LLM 总调用次数从 3 次降为 2 次（召回一次、生成一次）。

**UnifiedPlan** (`models.py` 新增) 是合并 ToolPlan、SemanticFrame、RetrievalPlan 的单一决策载体，扁平化字段设计，消除了之前分散在多个中间表示中的冗余和同步逻辑。

#### 新增模块

| 模块 | 路径 | 职责 |
|------|------|------|
| FactContextBuilder | `server/backend/app/fact_context.py` | 构建 `[[pid]]` 锚点事实表，LLM 唯一商品信息来源 |
| AnchorValidator | `server/backend/app/anchor_validator.py` | 流式循环状态机，逐 chunk 锚点校验（零普通文本延迟） |
| ConsistencyTracker | `server/backend/app/consistency_tracker.py` | 跨轮 denial cache + focus drift 检测 |
| UnifiedPlan | `server/backend/app/models.py` | 合并 ToolPlan + SemanticFrame + RetrievalPlan 的单一数据结构 |

#### 删除模块

| 模块 | 原因 |
|------|------|
| `intent_compiler.py` | IntentCompiler LLM 语义解析路径被规则化 + UnifiedPlan 方案替代 |
| `_merge_tool_plan_into_ir()` | workaround 方法，随 UnifiedPlan 统一而不再需要 |

#### 修改模块

| 模块 | 改动 |
|------|------|
| `semantic_layer.py` | 4 个核心函数（`rule_semantic_frame`、`_merge_rule_guards` 等）重写为 UnifiedPlan 扁平字段输出 |
| `embedding_retriever.py` | 新增 `_normalize_cjk_ascii()` 分词预处理 |
| `product_analysis.py` | 命中商品时注入 `enriched_message` 到 LLM prompt |
| `state_reducer.py` | 新增 `apply_unified()` 方法，统一处理 UnifiedPlan |
| `query_builder.py` | 新增 `build_from_unified()` 方法，从 UnifiedPlan 构建检索查询 |
| `hallucination_checker.py` | 降级为纯价格偏差检测（锚点校验移交 AnchorValidator） |
| `session_store.py` | 新增 `checkpoint()` / `recover()` 方法，3 阶段状态保存 |
| `degradation.py` | 全部 fallback 文案改为上下文感知 |
| `llm_client.py` | 所有 `stream_response` / `generate_response` 签名追加 `fact_block` 参数 |

---

### API 兼容性

- **无破坏性 API 变更**。所有现有客户端无需任何修改即可升级。
- `SemanticFrame` / `ShoppingIntentIR` 类型别名指向 `UnifiedPlan`，旧代码中的类型引用继续有效。
- WebSocket 协议消息格式、REST 端点路径和参数、事件类型定义均保持不变。

---

### 升级指南

从 v1.x 升级到 v2.0 无需数据迁移或配置变更。直接部署新版本即可。建议升级后观察以下指标以确认效果：

- 虚构商品告警率（预期降至 0）
- 用户重复输入频率（预期显著下降）
- 中英文混合查询命中率（预期提升）
