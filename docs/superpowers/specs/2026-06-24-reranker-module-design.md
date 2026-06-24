# Reranker 模块设计

**日期**：2026-06-24
**关联设计**：`2026-06-20-shopguide-gap-fill-design.md` 里程碑 B（B3 混合检索链路）
**范围**：在现有 `HybridRetriever`（BM25 + 向量 + RRF/weighted 融合）与业务规则打分 `rank_products` 之间，补齐独立的 **Reranker** 层。

---

## 一、背景与缺口

当前检索链路：

```text
约束提取 → HybridRetriever（BM25 + 向量 + RRF/weighted）
        → hard_filter（硬过滤）
        → rank_products（规则打分：类目/品牌/价格/评价）
        → Top N
```

- `HybridRetriever.rrf_fuse` 只做位次融合，无法对语义相关性做精排。
- `ranker.py::rank_products` 是基于属性匹配的规则打分，**不是语义判别**。
- 当 BM25 与向量分数接近时，缺少一个独立的判别器在召回与业务打分之间做精排，导致检索 Top 30 → Top 8 的环节没有真正的"重排"。

里程碑 B3 中明确列了 `reranker.py`（轻量交叉编码器或 LLM 重排），目前仓库尚未实现。

---

## 二、目标与非目标

### 目标

1. 引入独立 Reranker 模块，对 `HybridRetriever` 输出做语义重排。
2. 采用 **交叉编码器为主、LLM 兜底** 的混合方案：
   - 默认走本地 BGE-reranker-v2-m3。
   - 在对比意图、低置信度、用户纠偏/重推这三种关键场景下，触发 LLM 重排作为兜底。
3. 失败路径**静默降级**，不向上抛错、不向用户暴露错误。
4. 不引入新依赖（复用 `sentence-transformers`）。

### 非目标

- 训练自定义 reranker 模型。
- 个性化 reranker（按用户画像调权）。
- A/B 实验框架（延后到 stage 18）。
- LLM 重排接 circuit_breaker（二期视监控数据决定）。

---

## 三、模块边界与文件布局

### 新增模块

```
server/backend/app/
├── rag/
│   ├── reranker.py              # 新增：Reranker 协议 + 三种实现 + 工厂
│   ├── reranker_scenarios.py    # 新增：RerankScenario 枚举与触发判断
│   ├── fusion.py                # 现有：不改动
│   └── ...
└── llm_client.py                # 现有：LLMReranker 复用此客户端
```

### 对外接口

```python
class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 15,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]: ...
```

### 具体实现

| 类 | 职责 |
|---|---|
| `CrossEncoderReranker` | 本地 BGE-reranker-v2-m3，默认实现 |
| `LLMReranker` | list-wise，调用 LLM 给出新排序 + 简要重排理由 |
| `HybridReranker` | 组合上面两个，按 `scenario` 决策是否触发 LLM |
| `NoOpReranker` | 关闭重排或模型不可用时使用 |

### 职责单一性

Reranker 只回答一个问题：给定 `query` 和一批 `(product, evidence_chunks)`，返回新的排序和重排分数。
- **不**做硬过滤
- **不**做业务规则打分
- **不**直接实例化 LLM 客户端（注入式依赖）

---

## 四、数据流与触发逻辑

### 完整链路（reranker 嵌入后）

```text
用户输入
  ↓ 意图识别 / 约束提取
  ↓
HybridRetriever.search_with_evidence(plan, top_k=30)
  ↓  返回 list[ProductRetrievalResult]，含 evidence_chunks
  ↓
RerankScenario 判断（在 AdaptiveRetriever 里）
  ↓
HybridReranker.rerank(query, candidates[:30], top_k=15, scenario)
  ├─ 1) CrossEncoderReranker 对所有候选打分 → 新顺序
  ├─ 2) 若 scenario 命中 LLM 触发条件 → LLMReranker 只重排前 8 条
  └─ 3) 返回 list[ProductRetrievalResult]，分数=cross_score（或 LLM 微调后）
  ↓
hard_filter（再次确认硬过滤，防止重排后异常）
  ↓
rank_products(filtered, plan, retrieval_scores=重排分, limit=Top 8)
  ↓
返回最终 Top 8
```

### Top K 漏斗

| 阶段 | 数量 |
|---|---|
| 召回（HybridRetriever） | 30 |
| 交叉编码器输入 | 30 |
| 交叉编码器输出 | 15 |
| LLM 触发时输入 | 8（前 8 条做 list-wise） |
| 最终 Top | 8 |

### RerankScenario 触发判定

`server/backend/app/rag/reranker_scenarios.py`：

```python
class RerankScenario(str, Enum):
    DEFAULT = "default"                # 仅交叉编码器
    COMPARISON = "comparison"          # 对比意图 → LLM 兜底
    LOW_CONFIDENCE = "low_confidence"  # Top1/Top2 差距 < 阈值 → LLM 兜底
    REFINEMENT = "refinement"          # 用户纠偏/重推 → LLM 兜底

def detect_scenario(
    plan: RetrievalPlan,
    cross_scores: list[float],
    session_context: SessionContext | None = None,
) -> RerankScenario:
    # comparison: plan.intent in {"compare_products", "compare"}
    # refinement: session_context.last_intent in {"not_satisfied", "refine"}
    #             或 plan 中标记 is_refinement=True
    # low_confidence: cross_scores 已得出后判断 |scores[0] - scores[1]| < threshold
    # default: 其他
```

**触发优先级**：`COMPARISON > REFINEMENT > LOW_CONFIDENCE > DEFAULT`（强意图优先）。

### 评分语义

- 交叉编码器分数：BGE-reranker 输出 logits 后做 sigmoid，归一化到 `[0, 1]`。
- 业务打分阶段：把这个分数 × 5 作为 `retrieval_score` 传给 `rank_products`（保持与现有 `_score_product` 中 `score = retrieval_score * 5` 兼容）。
- `ProductRetrievalResult.score` 字段被覆盖为重排分；原 RRF 分数保留在 `metadata.rrf_score`（新增字段）方便排查。

### LLM 重排输出契约

- 输入：前 8 条的 `{product_id, title, brand, price, evidence[:3]}`。
- 输出：严格 JSON `[{"product_id": "xxx", "rank": 1, "reason": "..."}]`。
- 解析失败、`product_id` 不在候选集 → 静默回退到交叉编码器结果。
- 通过 `response_contract` 模块做结构化校验。

### 可观测性

每次重排都打点：

```
retrieval.reranker.scenario.{default|comparison|low_confidence|refinement}
retrieval.reranker.cross.latency_ms
retrieval.reranker.llm.invoked
retrieval.reranker.llm.latency_ms
retrieval.reranker.llm.parse_error
retrieval.reranker.fallback.no_model
retrieval.reranker.fallback.cross_failed
retrieval.reranker.fallback.llm_failed
```

---

## 五、降级、超时与配置

### 超时分级

扩展 `timeout_policy.TimeoutBudget`：

```python
@dataclass(frozen=True)
class TimeoutBudget:
    intent_seconds: float = 3.0
    retrieval_seconds: float = 2.0
    rerank_cross_seconds: float = 0.5    # 新增：交叉编码器单次重排上限
    rerank_llm_seconds: float = 4.0       # 新增：LLM 重排上限
    selection_seconds: float = 4.0
    response_first_chunk_seconds: float = 12.0
    tts_seconds: float = 10.0
```

**0.5s 依据**：BGE-reranker-v2-m3 在 GPU 上 30 对约 30~80ms，CPU 约 200~400ms。0.5s 是安全上限。
**4s 依据**：list-wise LLM 重排首字延迟通常 1~3s，4s 兜底。

### 降级链

```text
触发 reranker
  ↓
[1] 模型未加载/初始化失败 → NoOpReranker（直接返回输入顺序）
    打点 retrieval.reranker.fallback.no_model
  ↓
[2] CrossEncoderReranker.rerank(...) 超时或抛错
    打点 retrieval.reranker.fallback.cross_failed
    返回 RRF 原始顺序
  ↓
[3] LLM 触发场景下，LLMReranker 超时/解析失败/返回非法 product_id
    打点 retrieval.reranker.fallback.llm_failed
    回退到交叉编码器结果（不再次回退到 RRF）
```

**所有失败路径**都返回**有效结果**，绝不抛错到上层 `AdaptiveRetriever`。

### 熔断（二期）

LLM 重排接 `circuit_breaker.CircuitBreaker`，连续失败 N 次后短路 M 秒。一期不实现，留扩展点；二期视监控数据决定。

### 新增配置项

`Settings`（`server/backend/app/config.py`）：

```python
rerank_enabled: bool = True
rerank_model_dir: str = "model/bge-reranker-v2-m3"
rerank_model_id: str = "BAAI/bge-reranker-v2-m3"
rerank_device: str = "cuda:0"
rerank_input_top_k: int = 30
rerank_output_top_k: int = 15
rerank_llm_enabled: bool = True
rerank_llm_top_n: int = 8
rerank_low_confidence_threshold: float = 0.05
```

对应环境变量：
`RERANK_ENABLED`、`RERANK_MODEL_DIR`、`RERANK_DEVICE`、`RERANK_INPUT_TOP_K`、`RERANK_OUTPUT_TOP_K`、`RERANK_LLM_ENABLED`、`RERANK_LLM_TOP_N`、`RERANK_LOW_CONFIDENCE_THRESHOLD`。

### 模型下载与缓存

复用现有 `server/scripts/download_embedding_model.py` 的模式，新增 `server/scripts/download_reranker_model.py`：

- 默认从 ModelScope 镜像下载 BGE-reranker-v2-m3 到 `rerank_model_dir`。
- 启动时 Reranker 实例化优先从本地路径加载；本地缺失则使用 `NoOpReranker` + 启动日志告警，**不阻塞服务启动**。

### 与现有降级模块的边界

`degradation.fallback_text_for_failure` 不新增 `rerank_failed` 分支：reranker 失败只静默降级到 RRF 排序，不向用户输出文案。仅在 metrics 层打点。

### 进程内复用

`CrossEncoderReranker` 在 `create_app` 中**单例**注入，与 `embedding_retriever.model` 同生命周期。同进程多次请求共享同一加载好的模型，避免每请求重复加载（约 3s 加载时间）。

---

## 六、改动清单

| 类型 | 路径 | 说明 |
|---|---|---|
| 新增 | `server/backend/app/rag/reranker.py` | 协议、四种实现、工厂 |
| 新增 | `server/backend/app/rag/reranker_scenarios.py` | RerankScenario + 触发判断 |
| 新增 | `server/scripts/download_reranker_model.py` | 模型下载脚本 |
| 新增 | `server/tests/test_reranker.py` | Reranker 单元测试 |
| 新增 | `server/tests/test_reranker_scenarios.py` | 场景判断单元测试 |
| 修改 | `server/backend/app/adaptive_retriever.py` | 接入 reranker，调用顺序：hybrid → reranker → hard_filter → rank_products |
| 修改 | `server/backend/app/main.py` | 单例注入 `HybridReranker` |
| 修改 | `server/backend/app/config.py` | 新增 9 个配置项 |
| 修改 | `server/backend/app/timeout_policy.py` | 新增 `rerank_cross_seconds`、`rerank_llm_seconds` |
| 修改 | `server/tests/test_hybrid_retrieval.py` | 扩展 3 个集成测试 |

---

## 七、测试计划

### 单元测试

`server/tests/test_reranker.py`：

| 测试 | 覆盖点 |
|---|---|
| `test_noop_reranker_preserves_order` | NoOp 严格按输入顺序返回 |
| `test_cross_encoder_reorders_by_query_relevance` | mock fake encoder，验证按分数降序 |
| `test_cross_encoder_truncates_to_output_top_k` | 输入 30 条，输出 15 条 |
| `test_cross_encoder_handles_empty_candidates` | 空输入返回空，不抛错 |
| `test_cross_encoder_evidence_chunks_preserved` | 重排后 `evidence_chunks` 不丢失、不打乱 |
| `test_cross_encoder_timeout_returns_input_order` | 模拟超时，验证降级，打点 `fallback.cross_failed` |
| `test_llm_reranker_parses_valid_json` | LLM 返回合规 JSON，验证最终排序 |
| `test_llm_reranker_falls_back_on_invalid_product_id` | 非法 product_id，回退到交叉编码器 |
| `test_llm_reranker_falls_back_on_parse_error` | 非 JSON 返回，回退 |
| `test_hybrid_reranker_default_skips_llm` | DEFAULT 场景不触发 LLM |
| `test_hybrid_reranker_low_confidence_triggers_llm` | Top1/Top2 差距 < 0.05 触发 LLM |
| `test_hybrid_reranker_comparison_triggers_llm` | `intent == "compare_products"` 触发 LLM |
| `test_hybrid_reranker_refinement_triggers_llm` | refinement 标记触发 LLM |
| `test_hybrid_reranker_priority_comparison_over_low_conf` | 两个场景同时命中，按 comparison 处理 |

`server/tests/test_reranker_scenarios.py`：单独测 `detect_scenario`，纯逻辑。

### 集成测试

扩展 `server/tests/test_hybrid_retrieval.py`：

- `test_hybrid_retrieval_with_reranker_disabled`：`RERANK_ENABLED=false` 时链路依然可用，结果与重排前一致
- `test_hybrid_retrieval_with_fake_reranker`：注入 fake reranker，验证 `AdaptiveRetriever` 正确把分数透传给 `rank_products`
- `test_hybrid_retrieval_reranker_failure_does_not_break_response`：注入抛错的 reranker，验证 API 返回 200 且产品列表非空

### 评测对照

`data/eval/shopguide_core_scenarios.json` 5 个场景在 `RERANK_ENABLED=true` 下运行，作为重排上线前后基线对比指标：

- `recall@8`：gold_product_ids 落在 Top 8 的比例
- `precision@3`：Top 3 中相关商品比例
- 通过 `server/scripts/run_eval.py` 输出对比 CSV

**验收门槛**：reranker 上线后 `recall@8` 和 `precision@3` 不下降。

### Ablation 评测

`data/eval/retrieval_ablation_scenarios.json` 已存在 7 个场景，新增维度：

- `rerank: off` vs `rerank: cross_only` vs `rerank: hybrid`
- 三组各跑一次，记录指标差异

---

## 八、分阶段上线

| 阶段 | 操作 | 回滚方式 |
|---|---|---|
| 1 | 合并代码，`RERANK_ENABLED=false` 上线 | 无需回滚 |
| 2 | 评测集回归通过后，开 `RERANK_ENABLED=true`、`RERANK_LLM_ENABLED=false`（仅交叉编码器） | 环境变量切回 false |
| 3 | 观察 24 小时指标（`reranker.cross.latency_ms` p95、`reranker.fallback.*` 频次），无异常后开 `RERANK_LLM_ENABLED=true` | 环境变量切回 false |
| 4 | 若 LLM 重排出现高频 fallback 或延迟超标，按需下调 `rerank_llm_top_n` 或关闭 LLM 兜底 | 同上 |

---

## 九、验收标准

- [ ] `python -m server.scripts.download_reranker_model` 能下载模型到 `rerank_model_dir`
- [ ] 模型缺失时启动不阻塞，日志输出告警并使用 `NoOpReranker`
- [ ] `RERANK_ENABLED=false` 时链路完整，无重排
- [ ] `RERANK_ENABLED=true`、`RERANK_LLM_ENABLED=false` 时交叉编码器生效，p95 延迟 < 500ms
- [ ] `RERANK_LLM_ENABLED=true` 时 comparison/low_confidence/refinement 场景能正确触发 LLM
- [ ] 任一失败路径不向用户抛错，全部静默降级并打点
- [ ] 现有 `test_hybrid_retrieval.py`、`test_api.py`、`test_order_flow.py` 全部通过
- [ ] 新增的 `test_reranker.py`、`test_reranker_scenarios.py` 全部通过
- [ ] `shopguide_core_scenarios.json` 评测 `recall@8`、`precision@3` 不下降

---

## 十、风险与注意事项

1. **模型加载失败回退**：模型路径不存在或加载异常时，必须回退到 `NoOpReranker`，避免阻塞服务启动。
2. **GPU 资源**：交叉编码器约 1.1GB 显存，与 embedding 模型共享 `cuda:0` 需要预留显存。可通过 `RERANK_DEVICE=cpu` 切到 CPU。
3. **LLM 解析风险**：list-wise 输出若不严格符合 JSON 契约，必须静默回退到交叉编码器结果，不向上抛错。
4. **延迟风险**：LLM 重排引入额外 1~4s 延迟，因此**只在三种关键场景**触发，默认走快速路径。
5. **评测一致性**：上线前后跑同一份评测集对比，确保 `recall@8` 和 `precision@3` 不下降。
