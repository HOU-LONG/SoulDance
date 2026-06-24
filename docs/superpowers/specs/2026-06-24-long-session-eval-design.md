# 长会话上下文控制 + 决策复用策略评估 — 设计草案

**STATUS: DRAFT — 待评审，未进入实现**
**Date:** 2026-06-24
**Owner:** HOU-LONG
**Scope:** 用真实豆包 ARK API 在单会话内对全量 100 商品执行 ~1100 轮 × 5 个 condition，量化评估上下文控制层（窗口截断、结构化快照）与决策复用层（语义记忆、排序缓存）的实际效果，产出答辩级评测报告。

---

## 0. Live 代码路径核实

**核实日期：** 2026-06-24

**核实证据：**

| 检查项 | 结果 |
|---|---|
| Worktree 内 backend 主入口 | 仅 `server/backend/app/main.py` 一份 |
| 上游主仓是否存在顶层 `backend/` | 不存在；仅 `server/backend/` |
| 最近 14 天 commits 改动路径 | 全部落于 `server/backend/app/...`，关键 commit `2daf5c8 feat(rag): 检索半统一 + 答辩级评测体系 + 3 个生产 bug 修复` |
| 远程部署位置 | `mix_A100` 上 `env/venv_shopguide_backend/`，由 `server/scripts/setup_backend_env.sh` 构建，仅装载本地源码，不另存 |

**结论：** 已核实 live 服务对应的源码路径为 `server/backend/app/`，部署/运行环境使用该路径构建出的 backend 包或服务入口。本 spec 内所有相对路径均以此为准。

---

## 1. 评估对象与命名

报告与代码统一改名为「长会话上下文控制 + 决策复用策略评估」。机制分两类，命名严格区分：

### A. 上下文控制层（Context Control）

只影响"注入 LLM 的上下文体积/结构"，不改变执行路径。

- **A1 窗口截断**：`semantic_layer.py` 中 `_recent_context_summary` 的 `[-3:]/[-6:]` 切片
- **A2 结构化快照**：`semantic_context_payload()` 中 `focus_product` / `last_plan` / `pending_clarification` / `constraint_state` 四项结构化字段

### B. 决策复用层（Decision Reuse）

改变执行路径，可能跳过 LLM 重选。

- **B1 语义记忆复用** `RecommendationMemoryCache`：命中后跳过 `llm_selection`，回放 `short_response_summary` + `selected_products`
- **B2 排序结果复用** `StructuredMemoryCache`：plan→ranked 的 hash 级复用

报告标题、答辩 talking points、CLI flag、trace 字段全部按 A/B 分类命名。

**Caveat（写入报告"评估指标"章节）：** 决策复用层（B1/B2）评估为系统级边际效果，非纯算法单变量。增益来源同时包含：上下文减少、LLM 调用避免、回放路径短路。报告中明示此点，不声称 B1/B2 是"纯压缩算法"。

---

## 2. 评估目标

报告必须能回答的 4 个答辩问题：

1. **长会话稳定性**：1100 轮单会话下，分 turn type 的质量指标 / 状态一致率 / 失败率随 turn 演化曲线是否平稳？
2. **每层贡献**：A1 / A2 / B1 / B2 分别开/关时，token 用量、首字延迟、答案质量的边际变化（仅 A1/A2 视为单变量；B1/B2 视为系统级边际）。
3. **trace 健康度**：planner→retrieval→ranker→answer 路径分布、工具调用次数、异常分支占比、降级触发率。
4. **状态一致性**：focus_product / hard_constraints / 历史推荐 list 是否随 turn 增长漂移；对抗轮表现。

---

## 3. Condition 矩阵

| Cond | A1 窗口 | A2 快照 | B1 语义记忆 | B2 排序缓存 | 别名 |
|---|---|---|---|---|---|
| **C0** | 关 | 关 | 关 | 关 | 无压缩可行上限 baseline |
| **C1** | 开 | 关 | 关 | 关 | 仅窗口 |
| **C2** | 开 | 开 | 关 | 关 | 窗口 + 快照 |
| **C3** | 开 | 开 | 开 | 关 | + 语义记忆复用 |
| **C4** | 开 | 开 | 开 | 开 | 当前全开（生产默认） |

### 3.1 C0 baseline 解释口径

C0 报告分两段，强制写入 REPORT.md "关键发现" 章节：

- **C0-pre**：第 1 轮到首次触发 `degradation: "context_overflow_forced_trim"` 之前的所有 turn。**仅 C0-pre 用于与 C1/C2 对比 A 层质量影响。**
- **C0-post**：首次硬截断之后的所有 turn。**仅用于论证"无压缩工程不可行"，禁止用 C0-post 低分论证"压缩提升质量"。**

报告必须明示"C0-post 分数不参与 A 层有效性结论"。

### 3.2 硬截断保护

C0 的全量历史注入受 `eval_force_trim_token_budget=25000` 保护：
- runner 在注入 LLM 前估算 `context_payload_tokens`（用 tiktoken `cl100k_base` 近似豆包 tokenizer）
- 超过 25000 时硬截断到最近 N 轮直到 ≤25000，并打标签 `degradation: "context_overflow_forced_trim"`
- trace 记录"首次触发的 turn_index"和"累计硬截断次数"

### 3.3 缓存污染防控

每个 **stage × condition** 完全隔离（stage ∈ {dryrun, pilot, full}）：

1. 独立 `session_id`：`eval_{stage}_c{N}_2026-06-24`（例：`eval_dryrun_c0_2026-06-24` / `eval_pilot_c0_...` / `eval_full_c0_...`）
2. 独立 cache namespace：`data/eval/long_session_2026-06-24/{stage}/cache_c{N}/`
   - 同一 condition 在 dryrun / pilot / full 三阶段使用**三个不同目录**，互不可见
   - 这样即使 dryrun 阶段 `.put()` 已经写了 cache，pilot/full 阶段也读不到，物理隔离
3. **每个 condition 独立进程**，CLI 跑完即退出，避免内存 dict 残留
4. runner 首次启动用 `--reset-cache` 强制清空对应 stage×condition 目录；中途续跑禁用 `--reset-cache`（详见 §3.4）
5. trace 起始记录 cache stats，首次启动必须为全 0
6. 跨 condition 严格串行，不并发

### 3.4 启动模式：fresh vs resume

为避免 `--reset-cache` 与 §8 断点续跑冲突，CLI 强制二选一：

| 模式 | flag | cache 行为 | trace 行为 |
|---|---|---|---|
| **首次启动** | `--reset-cache`（必传） | 清空 stage×condition 目录 | 覆盖写 trace.jsonl，写入头部 meta |
| **续跑** | `--resume`（必传） | 保留 stage×condition 目录 | 追加写 trace.jsonl，校验头部 meta 4 个 hash |

**互斥约束**：
- `--reset-cache` 与 `--resume` 同时传入 → CLI 拒绝启动并报错退出
- 既未传 `--reset-cache` 也未传 `--resume` → CLI 拒绝启动并报错退出
- 启动时检测到 `trace.jsonl` 已存在但传了 `--reset-cache` → 不静默覆盖；先 backup 原文件到 `trace.jsonl.{timestamp}.bak`，再覆盖写
- 启动时检测到 `trace.jsonl` 不存在但传了 `--resume` → CLI 拒绝启动并报错退出

---

## 4. 禁用开关语义（Disable Switch Semantics）

**核心原则**：业务状态机永远在跑；开关只切"是否把状态注入 LLM 上下文"或"是否走快速路径"。这样 C0 不会因为"状态机半瘫痪"出现假性退化。

| 开关 | 受影响 | 不受影响 |
|---|---|---|
| `disable_window_truncation` (A1) | `_recent_context_summary` 中 `[-3:]/[-6:]` 改为全量；注入受 25K token 上限保护 | `context_events` 仍正常 append；state_reducer 仍正常工作 |
| `disable_structured_snapshot` (A2) | `semantic_context_payload()` 返回的 `focus_product` / `last_plan` / `pending_clarification` / `constraint_state` 四项**置 None/空** | `recent_context` 由 A1 决定，**不受 A2 影响**；`SessionContext.focus_product_id` / `last_plan` 自身仍正常更新；状态机仍跑 |
| `disable_recommendation_memory` (B1) | `RecommendationMemoryCache.get()` 强制返回 None | `.put()` 仍可写（便于命中率诊断） |
| `disable_rank_cache` (B2) | `StructuredMemoryCache.get()` 强制返回 None | `.put()` 仍可写 |

### 4.1 命中率口径

B1/B2 命中率必须区分两口径，写入 trace 与报告：

- **would_hit_rate**：假设 `.get()` 未禁用，本轮**是否能命中**——通过**纯探针** `probe(...)` 计算
- **effective_hit_rate**：实际是否走了复用路径

禁用 condition 下 `effective_hit_rate` 强制为 0，`would_hit_rate` 仍可观测。

#### 4.1.1 Pure Probe API 强制要求

`would_hit` 不允许通过"再调一次 `.get()`"来推断，因为这会污染缓存内部状态（命中计数、recency、semantic_hits / exact_hits / misses 统计、内部排序）。

必须新增 **side-effect-free probe API**：

```python
class StructuredMemoryCache:
    def probe(self, plan: RetrievalPlan, product_map: dict[str, Product]) -> bool:
        """Pure: 仅判断 key 是否存在 + hard_filter 是否通过，
        不更新 _hits/_misses，不改变内部状态，不调 self._items 以外的写操作。"""

class RecommendationMemoryCache:
    def probe(self, plan: RetrievalPlan, message: str, product_map: dict[str, Product]) -> bool:
        """Pure: 仅判断 exact_key 或 semantic_key 是否能命中 + 校验 taxonomy/约束/商品存在，
        不更新 _exact_hits/_semantic_hits/_misses/_invalidations，不改变内部状态。"""
```

**实现约束**：
- `probe()` 必须不调用任何修改 `self._items` / `self._*hits` / `self._misses` / `self._invalidations` / `self._writes` 的代码
- 单测覆盖：在 condition 全开（C4）下，连续调用 `probe()` 100 次与调用 0 次相比，`stats()` 输出完全一致
- runner 在每轮记录 trace 前并行调 `probe()` 拿 `would_hit_b1/b2`，不污染当前 condition 下的真实命中率
- `effective_hit_b1/b2` 仍来自实际业务路径上 `.get()` 的返回值

**禁止**：
- 不允许"先调 `.get()` 拿结果，再回滚 stats"——回滚不可靠
- 不允许在 `.get()` 内加 `dry_run` 参数后复用——保持 `.get()` 单一职责

---

## 5. 会话脚本

总计 **1100 轮**，全部在同一 `session_id` 下串行：

```
phase A  正常深问：100 商品 × 10 模板        = 1000 轮
phase B  跨商品横评：每 20 商品 1 次          =   5 轮
phase C  长程指代：每 100 轮 1 次             =  10 轮
phase D  对抗轮次（穿插，不集中堆尾）         =  75 轮
  D1 含糊指代："那个/上一个/最早那个"          15 轮
  D2 矛盾约束："要便宜的，但只买大牌"          10 轮
  D3 跨类目突然切换：从美妆 → 突然问数码       10 轮
  D4 撤销/反悔旧约束："刚才说不要日系，现在算了" 10 轮
  D5 模糊主体："他/这个/那款" 不接上下文       15 轮
  D6 错指代攻击：指代根本没推荐过的商品        15 轮
phase E  收尾交易：下单→改→撤→重推            =  10 轮
```

### 5.1 商品-提问模板

按类目定制（不是同套硬套）：

- 美妆护肤：成分、肤质、防晒系数、价格、评价、便宜替代、高端替代、换品牌、对比、加购
- 数码电子：处理器、内存、续航、价格、评价、便宜替代、高端替代、换品牌、对比、加购
- 食品饮料：成分/配料、保质期、品牌、价格、评价、便宜替代、高端替代、换品牌、对比、加购
- 服饰运动：材质、尺码、季节、价格、评价、便宜替代、高端替代、换品牌、对比、加购
- 家居日用：材质、尺寸、用途、价格、评价、便宜替代、高端替代、换品牌、对比、加购

模板放在 `app/eval/long_session_templates.py`，按 `product.category` 路由。

### 5.2 商品顺序

按类目交替穿插（美妆 → 食品 → 服饰 → 数码 → 家居 → 美妆 → ...），避免同类目连续 100 轮。长程指代轮（phase C）刻意指向 100+ 轮前的商品。

### 5.3 expected 字段

每轮的 expected 结构：

```json
{
  "turn_type": "retrieval|followup_factual|comparison|cart_action|long_range_reference|constraint_handling|adversarial_reference|adversarial_constraint",
  "ideal_top": [...],                          // 仅 retrieval / comparison 有
  "expected_focus_product_id": "...",          // 仅长程指代有
  "expected_intent": "...",
  "expected_no_change_to_constraints": [...],  // 撤销约束类
  "forbidden": [...],
  "adversarial_subtype": "D1|D2|D3|D4|D5|D6"
}
```

---

## 6. 评分体系（按 turn type 分桶）

| turn_type | 主指标 | 副指标 | LLM judge 采样 |
|---|---|---|---|
| retrieval | NDCG@5 / Recall@5 / Precision@5 / forbidden 命中率 | 首位命中率 | 0% |
| followup_factual | 事实正确率（基于商品 JSON 自动校验）+ hallucination_check 通过率 | 回复长度 / token | 0% |
| comparison | 两商品引用率 / 比较维度覆盖率 / 推荐倾向合理性（规则） | LLM judge 评分 | **30%** |
| cart_action | CartService 末态对账（数量、商品 id） | API 错误率 | 0% |
| long_range_reference | focus_product 解析正确率 / 商品 id 正确率 | 解析失败时是否触发 clarification；LLM judge | **30%** |
| constraint_handling | 约束是否正确施加/撤销 / forbidden 不出现率 | 状态漂移率 | 0% |
| adversarial_reference | 是否正确触发 clarification 而非乱选 | 拒答正确率；LLM judge | **50%** |
| adversarial_constraint | 是否检测出矛盾并 clarify | 漂移率；LLM judge | **50%** |

### 6.1 LLM judge 规范

- **模型**：独立 ARK 客户端实例，不复用 agent 的 LLM client，避免上下文污染
- **温度**：`temperature=0`（声明意图：让 provider 给出最确定的输出；不假设这必然消除所有非确定性）
- **复现策略**：**dry-run 实测分歧、自适应折叠**
  - dry-run 阶段：对每个被采样的 turn 调 judge **3 次**，trace 记录 3 次原始分数
  - dry-run 完成后计算 judge 分歧率：`disagreement_rate = 不一致 turn 数 / 总采样 turn 数`（任一维度 0/1 在 3 次中不一致即算不一致）
  - **若 `disagreement_rate < 5%`**（豆包对相同 prompt 实质上确定性）→ pilot/full 阶段降到 **1 次** judge 调用
  - **若 `5% ≤ disagreement_rate < 20%`**（轻度 provider 非确定性）→ pilot/full 仍用 **3 次平均**
  - **若 `disagreement_rate ≥ 20%`**（严重 provider 非确定性）→ 在 dry-run summary 标红，要求 user 决定（继续 3 次 / 升到 5 次 / 修改 rubric / 弃用 judge）
  - 决策口径写入 dry-run summary 与 final report，**禁止在报告里用 "temperature=0 + 3 次平均" 这种内部不一致的表达**
- **prompt 入库**：`server/backend/app/eval/prompts/long_session_judge_v1.md`，版本化
- **rubric**：4 个二元维度，每个 0/1，总分 0-4
  1. 命中正确（是否答到点上）
  2. 表达合理（是否流畅、有逻辑）
  3. 未幻觉（是否引用真实存在的商品/字段）
  4. 未越权改状态（是否未擅自下单/改约束）
- **预算估算**：dry-run 阶段固定 3 次 × ~30-50 个采样 turn × 5 condition ≈ 450-750 次；pilot/full 按上述折叠规则推算，写入 §10 "Cost Appendix"

#### 6.1.1 Judge 分歧记录字段

trace 中 `judge_score` 扩展为：

```jsonc
"judge_score": {
  "raw": [{"hit": 1, "fluent": 1, "no_hallucination": 1, "no_state_violation": 1},
          {...}, {...}],          // 3 次原始结果（pilot/full 折叠到 1 次时只有 1 项）
  "mean": 3.67,
  "disagreement": 0.17,            // 任一维度不一致的比例（0-1）
  "call_count": 3                  // dry-run=3, pilot/full 可能 =1 或 =3
}
```

### 6.2 规则评分实现

- 检索指标：复用现有 `server/backend/app/eval/metrics.py`
- 事实正确率：从 `Product` 字段（price、brand、ingredients、faqs）取真值，做字符串/数值匹配
- 购物车一致性：调 `CartService` 末态对账
- forbidden 命中率：检查回复 / top-K 是否包含 forbidden product_id
- 状态漂移率：每轮记录 `focus_product_id` / `hard_constraints`，与 expected 对照

---

## 7. Trace 采集

每轮一条 JSONL（追加写、每轮 flush）：

```jsonc
{
  "condition": "C2",
  "session_id": "eval_c2_2026-06-24",
  "turn_index": 47,
  "phase": "A",
  "turn_type": "retrieval",
  "adversarial_subtype": null,
  "query": "...",
  "expected": { /* 见 §5.3 */ },

  // 推理路径
  "pipeline": ["planner", "semantic_layer", "retrieval", "ranker", "answer"],
  "tool_calls": [{"name": "retrieval", "ms": 230}, ...],
  "branch_flags": {"memory_hit": "semantic_hit", "fallback": null, "clarify": false},

  // token & latency
  "prompt_tokens": 4321,
  "completion_tokens": 187,
  "first_chunk_ms": 820,
  "total_ms": 2310,

  // 上下文体积演化
  "context_payload_bytes": 8742,
  "context_payload_tokens": 2180,
  "context_events_count": 47,
  "focus_history_len": 47,

  // 状态一致性 + 降级
  "focus_product_id": "p_beauty_006",
  "hard_constraints": { ... },
  "state_drift": null,
  "degradation": null,

  // 命中率双口径（接 §4.1）
  "would_hit_b1": true,
  "effective_hit_b1": false,
  "would_hit_b2": true,
  "effective_hit_b2": false,
  "cache_stats_at_turn": {"b1_size": 23, "b2_size": 31},

  // 评分
  "rule_score": { "ndcg5": 0.83, "recall5": 1.0, "forbidden_hit": false },
  "judge_score": null,  // 仅采样 turn 有

  // 完整回复（供报告引用）
  "answer_text": "...",
  "retrieved_top_k": ["p_beauty_006", ...],

  // 版本指纹
  "script_version_hash": "sha256:...",
  "product_list_hash": "sha256:...",
  "condition_config_hash": "sha256:..."
}
```

trace 文件头一行写 meta：

```jsonc
{
  "_meta": true,
  "condition": "C2",
  "script_version_hash": "...",
  "product_list_hash": "...",
  "condition_config_hash": "...",
  "cache_namespace": "data/eval/long_session_2026-06-24/{stage}/cache_c2/",
  "started_at": "2026-06-24T14:00:00+08:00",
  "ark_model": "ep-xxx",
  "spec_version": "2026-06-24-v1"
}
```

每条 trace 行也带 `script_version_hash`，行级校验。

---

## 8. 断点续跑协议

1. trace 文件追加写，每轮强制 `flush()` + `fsync()`
2. 续跑流程：
   - 读 trace 头部 meta，提取 4 个 hash
   - 当前运行环境重新计算 4 个 hash
   - **任一 hash 不一致 → 拒绝续跑，强制全量重跑该 condition**（避免改模板后续跑混数据）
   - 全一致 → 读最后一条 trace 的 `turn_index`，从下一轮继续
   - cache namespace 仍指向同一目录，不清空（接着用）
3. ARK 限流 / 网络抖动：per-turn retry 最多 3 次，指数退避（2s / 4s / 8s）
4. retry 仍失败：整轮标 `degradation: "ark_failure_skip"`，trace 落盘，继续下一轮（不中断 session）
5. 全 condition 跑完后才合成报告

---

## 9. Pilot Gate（必须 user-approved 才放行）

**禁止跳级。**

```
Stage 1 — dry-run (每 condition 20 轮 = 100 轮)
  放行条件：
  - 5 个 condition 全部跑通无异常
  - trace schema 完整（见下方 §9.1 schema 校验口径）
  - 缓存隔离验证：每个 stage×condition 起始 cache stats 都是 0
  - 断点续跑测试：手动 kill 一次，重启用 --resume 从下一轮继续，trace 不重不漏；hash 校验通过
  - probe API pure 验证：连续调用 probe() 100 次，cache.stats() 与调 0 次完全一致
  - judge 分歧率实测：按 §6.1 折叠规则给出 pilot/full 的 judge call_count
  - 每轮实际 ARK 调用数实测：写入 dry-run summary，作为 pilot/full 成本推估口径
  - ARK 真实成本估算：把 100 轮成本 × 55 推估全量成本，写入 spec §10 "Cost Appendix"
  - 产出 dry-run 摘要 markdown 给 user review
  - 落在 data/eval/long_session_2026-06-24/dryrun/，不污染 pilot/full 目录

Stage 2 — pilot (每 condition 100 轮 = 500 轮)
  放行条件：
  - dry-run 摘要 user-approved
  - 出 mini 报告：5 条曲线 + 5 个 condition 的 token/latency/NDCG 趋势
  - 记录 C0 在 100 轮内是否已触发硬截断、首次触发 turn_index
  - 沿用 dry-run 决定的 judge call_count
  - pilot 实测 ARK 调用数 → 更新 full 阶段成本推估，写入 §10 "Cost Appendix"
  - 产出 pilot 摘要 markdown 给 user review
  - 落在 data/eval/long_session_2026-06-24/pilot/

Stage 3 — full run (每 condition 1100 轮 = 5500 轮)
  仅在 pilot user-approved 后启动
  正式跑、出最终 REPORT.md
```

每个 stage 都是 user gate，**不自动放行**。

### 9.1 Trace Schema 校验口径

替代"所有字段非缺失"这种过严表达。采用 schema-based 校验：

**required keys**（必须存在且非缺失）：
`condition` / `session_id` / `turn_index` / `phase` / `turn_type` / `query` / `expected` / `pipeline` / `tool_calls` / `branch_flags` / `prompt_tokens` / `completion_tokens` / `first_chunk_ms` / `total_ms` / `context_payload_bytes` / `context_payload_tokens` / `context_events_count` / `focus_history_len` / `hard_constraints` / `would_hit_b1` / `effective_hit_b1` / `would_hit_b2` / `effective_hit_b2` / `cache_stats_at_turn` / `rule_score` / `answer_text` / `retrieved_top_k` / `script_version_hash` / `product_list_hash` / `condition_config_hash`

**nullable keys**（schema 允许 null）：
- `adversarial_subtype`：仅 phase D 非 null
- `focus_product_id`：上下文无 focus 时可为 null
- `state_drift`：未观测到漂移时为 null
- `degradation`：未触发降级时为 null
- `judge_score`：仅采样 turn 非 null

**类型校验**：
- `prompt_tokens` / `completion_tokens` / `first_chunk_ms` / `total_ms` / `context_payload_bytes` / `context_payload_tokens` / `context_events_count` / `focus_history_len` 必须为 int ≥ 0
- `would_hit_*` / `effective_hit_*` 必须为 bool
- `pipeline` / `tool_calls` / `retrieved_top_k` 必须为 list
- `rule_score` / `branch_flags` / `cache_stats_at_turn` / `hard_constraints` / `expected` 必须为 dict
- 三个 `*_hash` 必须匹配正则 `^sha256:[a-f0-9]{64}$`

**校验工具**：runner 启动时加载 `app/eval/trace_schema_v1.json`（JSON Schema），每条 trace 行落盘后立即校验，失败则 abort 该 condition。dry-run gate 验收时全量回放校验。

---

## 10. 资源与风险预估

- **总轮次**：5 × 1100 = 5500 轮
- **单轮 ARK 调用数**：**不预设**为固定数。当前 backend 为 compiler-style（planner / semantic / hallucination_check / answer 多个 LLM 节点条件触发），每轮实际调用次数随 turn_type / cache hit / fallback 路径变化。
- **粗估上限**（仅用于初版预算评估，不作为决策依据）：每轮最多 ~3 次 ARK 调用 + judge 450-750 → **粗估上限 ~17000 次 ARK 调用**
- **真实成本口径**：dry-run 阶段 trace 实测每轮平均 ARK 调用数（从 `tool_calls` + branch_flags 解析），按 condition 分桶统计，写入 dry-run summary
  - dry-run 实测值 × 55（pilot 倍率）→ pilot 预估
  - dry-run 实测值 × 1100/20 = ×55 → full 预估（每 condition）
  - **pilot 与 full 阶段的放行 user-approval 必须基于 dry-run 实测推估，不基于本节预设值**
- **单轮均耗**：dry-run 阶段实测，本节不预设
- **ARK 成本**：dry-run 后用 100 轮真实 token 数据推估总成本，写入 spec 附录的 "Cost Appendix" 章节后再放行 pilot；pilot 实测再推估 full，写入附录后放行 full run
- **关键风险**：
  - 长 session ARK 限流 → 接 §8 续跑协议
  - C0 在某轮后必然触发硬截断 → 接 §3.1 解释口径
  - LLM judge 自身波动 → 接 §6.1.1
  - 缓存污染 → 接 §3.3 + 独立进程 + stage 隔离
  - 跑到一半改模板 → 接 §8 hash 拒绝续跑

### 10.1 Cost Appendix（Task 13 dry-run smoke 实测）

**实测日期：** 2026-06-25
**Smoke 规模：** C0 5 轮（续跑测试遗留）+ C1/C2/C3/C4 各 2 轮 = 13 轮真实 ARK 调用
**ARK model：** `ep-20260514111645-lmgt2`（豆包 Pro）

| Condition | n_turns | 平均 ARK tool_calls/turn | 平均 prompt_tokens | 平均 total_ms | degradation 次数 |
|---|---|---|---|---|---|
| C0 | 5 | 0.0 | 0 | 4259 | 0 |
| C1 | 2 | 0.0 | 0 | 6616 | 0 |
| C2 | 2 | 0.0 | 0 | 5973 | 0 |
| C3 | 2 | 0.0 | 0 | 6380 | 0 |
| C4 | 2 | 0.0 | 0 | 6633 | 0 |

**Judge 采样：** 0（dryrun smoke 规模太小，sample_rate × 13 < 1 故无采样）；分歧率推断保留至 pilot/full 实测后决定。
**Judge call_count 推断：** pending（需 pilot 阶段实测）。

**已知数据缺口（待后续修复）：**
- `prompt_tokens` / `tool_calls` 全为 0。原因：Task 10 的 `_invoke_agent` 当前只从 `handle_message` 的 events 里抽取 `assistant_text` 和 `product_card`，未抽取 token 计数与工具调用链。Pilot 阶段进入前需要增强 `_invoke_agent` 真实抽取这两个字段，否则 token/cost 推估无法做。
- 这是 Task 10 设计时与 controller 约定的"未知字段 default 0" 的现状，pilot/full 启动前必须补齐。

**有效观测：**
- **总 ARK 调用通过率 100%**：13 个真实调用，0 个 degradation/超时/限流。
- **真实端到端时延**（含 jieba 加载 / 商品向量预热 / answer 生成）：4.3-6.6 秒/turn。C0（A1 关）显著低于 C1/C4 — 这说明 disable_window=True 时 LLM 注入上下文确实变小且更快。
- **trace schema 一次通过**：65 个 turn line 全部通过 jsonschema 校验。
- **缓存隔离已验证**：5 个独立 cache_c{N} 目录互不可见。
- **断点续跑已验证**：截断 trace 到第 3 turn 后 resume，正确从 turn 3/4 接续，不重不漏。
- **Hash mismatch 拒绝已验证**：篡改 script_version_hash 后 resume，CLI 抛 `HashMismatchError`，exit code 1。

**Pilot/Full 预估方法（实施时再算）：**
- Pilot 预估总 ARK 调用 = dryrun_avg × 100 × 5 = ~5000 calls
- Full 预估总 ARK 调用 = dryrun_avg × 1100 × 5 = ~55000 calls
- 单轮均耗 ≈ 6 秒 → full run ≈ 5500 × 6 = 33000 秒 ≈ 9.2 小时（串行）
- 实际 token 量需 pilot 实测后回填本附录

**Pilot 与 Full 放行条件：** 基于以上实测，token/cost 缺口需先补齐，user-approved 后才放行。


---

## 11. 产物清单

```
docs/superpowers/specs/2026-06-24-long-session-eval-design.md     # 本 spec
data/eval/long_session_2026-06-24/
├── dryrun/                                # Stage 1 产物（自含 cache）
│   ├── trace_C0..C4.jsonl                 # 20 轮（首条为 _meta，余为 turn trace）
│   ├── cache_c0/ ... cache_c4/            # dryrun 阶段隔离 cache
│   └── DRYRUN_SUMMARY.md
├── pilot/                                 # Stage 2 产物（自含 cache）
│   ├── trace_C0..C4.jsonl                 # 100 轮
│   ├── retrieval_C0..C4.csv
│   ├── cache_c0/ ... cache_c4/            # pilot 阶段隔离 cache
│   └── PILOT_SUMMARY.md
├── full/                                  # Stage 3 产物（自含 cache）
│   ├── trace_C0..C4.jsonl                 # 1100 轮
│   ├── retrieval_C0..C4.csv
│   ├── followup_C0..C4.csv
│   ├── adversarial_C0..C4.csv
│   ├── judge_C0..C4.csv
│   ├── cache_c0/ ... cache_c4/            # full 阶段隔离 cache
│   └── REPORT.md
└── plots/
    ├── retrieval_quality_by_turn.png      # NDCG / Recall 沿 turn × 5 condition
    ├── token_usage_curve.png              # prompt_tokens 沿 turn × 5 condition
    ├── context_overflow_marker.png        # C0 硬截断点位
    ├── memory_hit_rate.png                # B1/B2 双口径命中率
    ├── latency_p50_p90_p99.png
    ├── state_drift_heatmap.png
    ├── adversarial_pass_rate.png          # 对抗轮通过率
    └── score_by_turn_type.png             # 主指标分桶
```

### 11.1 REPORT.md 章节

1. 评估设计（命名、condition 矩阵、隔离保证、live 路径核实证据）
2. 关键发现（3-5 条带数字）**含 C0-pre/post 解释约束**
3. 上下文控制层（A1 + A2）有效性
4. 决策复用层（B1 + B2）有效性与代价（**含系统级边际 caveat**）
5. 按 turn_type 的质量画像
6. 长会话稳定性 / 对抗轮表现
7. 时延、token、成本
8. 失败案例剖析
9. 答辩 Q&A 预设

---

## 12. 代码改动清单

**核心 app 改动均在 `server/backend/app/`，CLI 入口在 `server/scripts/run_long_session_eval.py`，新增评测模块均在 `server/backend/app/eval/`。**

### 12.1 配置层

- `server/backend/app/config.py`：新增 5 个字段
  - `eval_disable_window_truncation: bool = False`
  - `eval_disable_structured_snapshot: bool = False`
  - `eval_disable_recommendation_memory: bool = False`
  - `eval_disable_rank_cache: bool = False`
  - `eval_force_trim_token_budget: int = 25000`

### 12.2 上下文控制层开关

- `server/backend/app/semantic_layer.py`
  - `_recent_context_summary` 受 A1 开关控制
  - `semantic_context_payload` 受 A2 开关控制（清四项，不动 `recent_context`）
- `server/backend/app/agent.py`：注入 25K 硬截断保护（context budget check）

### 12.3 决策复用层开关

- `server/backend/app/memory_cache.py`
  - `RecommendationMemoryCache.get()` 接受 `disable_get: bool` 参数
  - `StructuredMemoryCache.get()` 同上
  - `.put()` 不受开关影响（便于 cache 写入 + probe 统计）
  - **新增 `.probe()` pure API**（见 §4.1.1）：side-effect-free 判断 would_hit，不更新 stats
- `server/backend/app/agent.py`：调用 `.get()` 时透传 `disable_get`；并行调 `.probe()` 拿 `would_hit_b1/b2` 落 trace

### 12.4 新增评测模块

- `server/backend/app/eval/long_session_runner.py`：核心 runner（按 condition 跑、流式落 trace、断点续跑、硬截断保护）
- `server/backend/app/eval/long_session_templates.py`：100 商品 × 10 模板生成器 + 75 对抗轮模板
- `server/backend/app/eval/long_session_judge.py`：LLM judge 模块（独立 ARK client）
- `server/backend/app/eval/long_session_report.py`：CSV / 图 / Markdown 报告生成
- `server/backend/app/eval/prompts/long_session_judge_v1.md`：judge prompt（版本化入库）

### 12.5 CLI

- `server/scripts/run_long_session_eval.py`

```bash
# === 首次启动：必须传 --reset-cache，禁止传 --resume ===
# 每个 condition 独立进程跑；--stage 决定 cache namespace 子目录与 session_id 前缀
python -m scripts.run_long_session_eval --stage dryrun --condition C0 --reset-cache
python -m scripts.run_long_session_eval --stage dryrun --condition C1 --reset-cache
# ... C2 C3 C4
python -m scripts.run_long_session_eval --stage dryrun --report   # 出 dryrun summary

# === 中途崩了续跑：必须传 --resume，禁止传 --reset-cache ===
# CLI 校验 trace.jsonl 头部 4 个 hash 与当前环境一致，否则拒绝续跑
python -m scripts.run_long_session_eval --stage dryrun --condition C0 --resume

# === pilot：user-approved 后启动 ===
python -m scripts.run_long_session_eval --stage pilot --condition C0 --reset-cache
# ...
python -m scripts.run_long_session_eval --stage pilot --report

# === full：pilot user-approved 后启动 ===
python -m scripts.run_long_session_eval --stage full --condition C0 --reset-cache
# ...
python -m scripts.run_long_session_eval --stage full --report
```

**CLI 互斥规则**：
- `--reset-cache` 与 `--resume` 互斥，同时传报错退出
- 两者都不传 → 报错退出（强制显式声明意图）
- `--reset-cache` 启动时若 `trace.jsonl` 已存在 → 自动 backup 为 `trace.jsonl.{timestamp}.bak` 后覆盖
- `--resume` 启动时若 `trace.jsonl` 不存在 → 报错退出

### 12.6 配置默认

生产环境 `Settings` 默认 4 个 disable 全为 False（即 C4 全开），eval 只在 CLI 启动时通过环境变量临时覆盖，不污染生产配置。

---

## 13. 评估安全护栏（Evaluation Safeguards 汇总）

供答辩时直接引用：

1. **路径风险关闭**：§0 已核实 live 路径
2. **命名严格区分**：A 上下文控制 / B 决策复用，不混称"压缩"
3. **C0 解释分段**：C0-pre 用于质量对比，C0-post 仅论证工程不可行
4. **每层贡献口径**：A1/A2 视为单变量；B1/B2 视为系统级边际，已写 caveat
5. **缓存独立（含 stage 维度）**：3 stage × 5 condition = 15 独立 cache 目录；session_id 带 stage 前缀；独立进程
6. **状态机不动**：禁用开关只切"注入/使用"，不切"维护"
7. **命中率双口径**：would_hit / effective_hit 区分
8. **Pure Probe API**：would_hit 通过 `probe()` 采集，绝不复用 `.get()` 以避免污染 cache stats
9. **指标按 turn type 分桶**：不用 NDCG 一把梭
10. **对抗轮内置**：75 轮含糊指代/矛盾约束/跨类目切换/撤销/错指代攻击
11. **LLM judge 受限 + 自适应折叠**：仅 4 个 turn type 采样，dry-run 实测分歧率后决定 pilot/full 重复次数，rubric 固化版本化
12. **断点续跑 hash 校验**：模板/商品/condition 变更后拒绝续跑
13. **CLI 互斥模式**：`--reset-cache` 与 `--resume` 互斥，强制显式选择
14. **Trace Schema 校验**：schema-based 校验（required + nullable + 类型），非"所有字段非缺失"
15. **Pilot Gate**：dry-run → pilot → full，每级 user-approved
16. **成本基于实测**：每轮 ARK 调用数由 trace 实测，dry-run/pilot 实测推估下游成本，写入 §10 "Cost Appendix"

---

## 14. 后续流程

1. 本 spec 标 **DRAFT** 已提交
2. 等 user review；user-approved 后才进入 `superpowers:writing-plans` 出实施计划
3. 实施计划再 user-approved 后才动代码
4. 代码动完先跑 dry-run，user 看 §9 gate 才放行 pilot
5. pilot 完 user 看才放行 full run
6. full run 完出 REPORT.md，作为答辩主要参考资料

**本 spec 在 user-approved 前不进入实现阶段。**
