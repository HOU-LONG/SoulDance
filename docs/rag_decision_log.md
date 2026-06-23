# ShopGuide RAG Decision Log

## 2026-06-23 检索半统一 + 评测扩展 + 消融实验

### 决策背景

距答辩窗口期，需同时收敛两类问题：
- 检索链路的工程债：两条 dense 路径（内存矩阵 / SQLite chunk 循环点积）并存、融合策略不一致（加权和 vs RRF）、权重全部硬编码。
- 评测覆盖缺口：5 条核心场景距答辩要求的 20 类场景差距过大；DSL 不支持多轮、品牌过滤、订单状态机、异常路径等断言。

### 决策

**1. 检索半统一（不引入向量库）**

- Dense 路径统一到内存矩阵（`numpy` 点积），删除 SQLite chunk 循环点积的旧路径。
- BM25 保留 chunk 级 + group-by-product max，长尾召回不丢。
- 100 商品规模不需要 Milvus / Qdrant / pgvector，等数据量 > 1 万再说。
- `ProductChunk.embedding` 表保留作为冷启动持久化缓存（`load_dense_index_from_db`）。

**2. 检索超参全部进 `config.py` + 环境变量**

新增 `RetrievalConfig`：
- `fusion_strategy ∈ {weighted, rrf, dense_only, bm25_only}`
- `dense_weight: float`（仅 weighted）
- `rrf_k: int`（仅 rrf）
- `top_k_recall / top_k_final`

所有检索器构造接收 `RetrievalConfig`，环境变量驱动消融实验：

```bash
RETRIEVAL_FUSION_STRATEGY=rrf RETRIEVAL_RRF_K=30 ./start_backend.sh
RETRIEVAL_FUSION_STRATEGY=weighted RETRIEVAL_DENSE_WEIGHT=0.5 ./start_backend.sh
```

**3. 评测 DSL 扩展**

- `EvalScenario` 支持 `steps: [EvalStep]` 多轮 + `fault` fixture 注入 + `golden_id` 链接金标
- `EvalExpectation` 新增 11 个字段（品牌过滤 / 价格区间 / clarification / no_match / comparison / order_status / cart_quantity / error_kind / subset / explanation_terms / focus_product）
- Runner 新增 `${var_name}` 占位符（在 message / payload / expect 三处替换）
- 默认走真 LLM，`--fake-llm` 用于离线 CI 烟囱

**4. 评测场景库扩展到 22 个**

按主题分文件：
- `core.json` (5) - baseline
- `recommend.json` (8) - 推荐类，全部标 `golden_id` 用于 IR 指标
- `multi_turn.json` (5) - 多轮 + 指代消解
- `edge.json` (3) - 边缘
- `cart_order.json` (3) - CRUD + 状态机
- `failure.json` (3) - LLM 超时 / 幻觉 / WS 断线

**5. 消融实验脚本 + 答辩用数据**

`scripts/run_ablation.py` 跑 9 个配置矩阵 × 8 推荐场景，CSV 输出 Recall@K / NDCG@K。

实测结论：
- `dense_only` 显著弱于其他（NDCG@5 = 0.426 vs 0.505+）
- `weighted` 和 `rrf` 在 100 商品规模下等价（α ∈ [0.3, 0.8]、k ∈ [30, 100] 全部 NDCG@5 = 0.513）
- 当前 MVP 权重 `0.65 / 0.35` 不需要调
- 小数据集下精细调权无意义，瓶颈在 LLM 语义解析而非检索权重

**6. Bug 修复（评测过程暴露）**

- `LLMClientWithBreaker._json_completion` 缺失 → `ComparisonEngine` 报 AttributeError
- `_stream_no_retrieval_events` 无超时 → 整条 WS 可能被 LLM 卡死
- `memory_cache` 命中后跳过 `feedback_ranker.apply` → 跨 session 个性化数据泄漏

详细原因与修法见 `server/tests/test_bugfix_phase3.py`。

### Release Acceptance 集成

`server/scripts/run_release_acceptance.py` 新增 `eval-full` check：真 LLM 跑全场景，门槛 80%，没 API key 自动 skip。`eval-runner` 退化为 fake LLM 烟囱测试，保证离线 CI 友好。

### 评测当前基线（真 LLM）

```
23/27 = 85.2% 通过率
```

剩 4 个 fail 是产品改进点（非评测脚本 bug）：
- `multi_turn_cancel_constraint`：LLM 把"酒精可以接受"误识别为新意图
- `recommend_drink_no_carbonated`：LLM 把"无糖"识别为成分排除
- `recommend_phone_budget_range`：LLM 未解析"5000-8000 元"价格区间
- `recommend_cheaper_running_shoes`：cheaper 软偏好未触发价格升序

这些是答辩可以坦诚说的"已知优化项"。

---

## 2026-05-25 Interaction Naturalness Pass

Goal: make the backend behave more like a low-pressure shopping guide without breaking the existing Android contract.

## Decisions

- Keep hard constraints deterministic. Negative requirements such as `不要含酒精` and `不要日系品牌` remain hard filters.
- Add a small interaction policy in the backend instead of relying on free-form LLM behavior.
- Ask clarification only for high-risk vague requests. Example: `推荐一款手机` asks whether the user values camera, battery, or value.
- Stream product cards earlier. The backend sends one deterministic understanding sentence, then product cards, then grounded explanation.
- Keep new events optional. Android can progressively render `quick_actions`, `comparison_result`, and bundle events.
- Resolve cart and comparison references from session state, not from the LLM.

## Verification Scenarios

- `推荐防晒霜，但不要含酒精的，也不要日系品牌`
- `推荐一款手机`
- `推荐防晒霜` then `第一款和第二款哪个更适合油皮？`
- `下周去三亚度假，帮我搭配一套从防晒到穿搭的方案`
- `把刚才那款加到购物车` then `数量改成2`
- No-match recovery with an impossible budget.

