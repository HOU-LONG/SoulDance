# Reranker 补齐实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 补齐 reranker 模块 Final Review 给出的 4 个 Important findings：把 reranker 全链路改为 async（含 LLMReranker 接入项目现有 async LLMClient）、reranker 内部使用 asyncio.wait_for 接入 TimeoutBudget 超时、main.py 把 InMemoryMetrics 与 reranker 共享、并清理硬编码注释与一致性问题。

**Architecture:** Reranker 协议改为 async；CrossEncoderReranker 用 `asyncio.to_thread` 跑 sentence-transformers 的同步 predict；LLMReranker 直接 await `llm_client._json_completion`；HybridReranker async 编排；AdaptiveRetriever 提供 async search 路径；ShopGuideAgent.retrieve_and_rank 改为 async；所有调用点（业务代码 + 测试）跟进。Reranker 内部用 `asyncio.wait_for` 包 `TimeoutBudget.rerank_cross_seconds` 与 `rerank_llm_seconds`，超时走静默降级。

**Tech Stack:** Python asyncio、pytest-asyncio（项目已用）、sentence-transformers、现有 async LLMClient。

## Global Constraints

- **不引入新依赖**：复用现有 asyncio、pytest-asyncio。
- **Reranker 协议全面 async**：所有四种实现的 `rerank` 方法都是 `async def`，返回 `list[ProductRetrievalResult]`。
- **CrossEncoderReranker 内部使用 `asyncio.to_thread`** 跑 sentence-transformers 的同步 `predict`，避免阻塞 event loop。
- **LLMReranker 调用 `await self.llm_client._json_completion(messages)`**（项目现有 async 接口，返回 JSON 字符串），不再依赖不存在的 `chat_json_sync`。
- **TimeoutBudget 接入**：CrossEncoderReranker 用 `asyncio.wait_for(..., timeout=budget.rerank_cross_seconds)`；LLMReranker 用 `asyncio.wait_for(..., timeout=budget.rerank_llm_seconds)`。超时走 fallback 路径并打点。
- **build_reranker 签名**：新增 `timeout_budget: TimeoutBudget | None = None` 参数；默认值 `TimeoutBudget()`。
- **InMemoryMetrics 共享**：`create_app` 中把 `metrics = InMemoryMetrics()` 提前到 `build_reranker(...)` 之前，传入。
- **向后兼容**：所有现有同步测试改为 `@pytest.mark.asyncio` 并 `await retrieve_and_rank(...)`；保证全部测试通过。
- **降级哲学不变**：所有失败路径（含 timeout）都静默回退、打点、不向上抛错。
- **commit 粒度**：每个 Task 单独 commit，消息带 `Co-Authored-By: Claude <noreply@anthropic.com>`。

---

## 文件结构

| 路径 | 类型 | 改动 |
|---|---|---|
| `server/backend/app/rag/reranker.py` | 修改 | 4 个 Reranker 改为 async，CrossEncoder 用 to_thread，LLM 改 await async client，全部加 wait_for；build_reranker 接收 timeout_budget |
| `server/backend/app/adaptive_retriever.py` | 修改 | 新增 `async def search_async`；hybrid 分支异步路径用它；保留同步 `search()` 不变（reranker=None 时） |
| `server/backend/app/agent.py` | 修改 | `retrieve_and_rank` 改为 `async def`；调用 `adaptive_retriever.search_async`；调用方加 await |
| `server/backend/app/tools/retrieval.py` | 修改 | 调用 `await self._agent.retrieve_and_rank(...)` |
| `server/backend/app/main.py` | 修改 | metrics 提前；build_reranker 传 metrics 和 llm_client 和 timeout_budget；reranker 注入 ShopGuideAgent 不变 |
| `server/tests/test_reranker.py` | 修改 | 所有测试加 `@pytest.mark.asyncio`，调用前加 `await` |
| `server/tests/test_reranker_scenarios.py` | 不动 | 纯逻辑函数，仍为 sync |
| `server/tests/test_hybrid_retrieval.py` | 修改 | reranker 相关测试加 async 标记；其余不动 |
| `server/tests/test_agent_core.py` | 修改 | 10 个 `retrieve_and_rank` 调用点改为 async 并加 await（约 7 个测试） |
| `server/tests/test_bugfix_phase3.py` | 修改 | 3 个 `retrieve_and_rank` 调用点改为 async |

---

## Task 1：Reranker 协议与 NoOpReranker 改 async

**Files:**
- Modify: `server/backend/app/rag/reranker.py`
- Modify: `server/tests/test_reranker.py`

**Interfaces:**
- Produces:
  - `class Reranker(Protocol)`: `async def rerank(query, candidates, *, top_k, scenario) -> list[ProductRetrievalResult]`
  - `class NoOpReranker`: `async def rerank(...)` 立即返回 `candidates[:top_k]`

- [ ] **Step 1：修改 `reranker.py` 中的 `Reranker` Protocol 与 `NoOpReranker`**

把 `Reranker.rerank` 和 `NoOpReranker.rerank` 改为 `async def`：

```python
@runtime_checkable
class Reranker(Protocol):
    async def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 15,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]: ...


class NoOpReranker:
    async def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 15,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]:
        return list(candidates[:top_k])
```

- [ ] **Step 2：把 `TestNoOpReranker` 全部测试改为 async**

每个测试方法前加 `@pytest.mark.asyncio`，方法签名加 `async`，调用 `rerank` 处加 `await`：

```python
import pytest

class TestNoOpReranker:
    @pytest.mark.asyncio
    async def test_preserves_input_order(self):
        candidates = [_result("p1", 0.9), _result("p2", 0.8), _result("p3", 0.7)]
        result = await NoOpReranker().rerank("q", candidates, top_k=10)
        assert [r.product.product_id for r in result] == ["p1", "p2", "p3"]

    @pytest.mark.asyncio
    async def test_truncates_to_top_k(self):
        candidates = [_result(f"p{i}", 1.0 - i * 0.01) for i in range(20)]
        result = await NoOpReranker().rerank("q", candidates, top_k=5)
        assert len(result) == 5
        assert [r.product.product_id for r in result] == [f"p{i}" for i in range(5)]

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self):
        result = await NoOpReranker().rerank("q", [], top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_scenario_kwarg_is_accepted(self):
        candidates = [_result("p1", 0.9)]
        result = await NoOpReranker().rerank("q", candidates, top_k=5, scenario=RerankScenario.COMPARISON)
        assert result == candidates
```

- [ ] **Step 3：跑 NoOp 测试确认通过**

Run: `cd server && python -m pytest tests/test_reranker.py::TestNoOpReranker -v`
Expected: 4 个 PASS

- [ ] **Step 4：commit**

```bash
git add server/backend/app/rag/reranker.py server/tests/test_reranker.py
git commit -m "$(printf 'refactor(rerank): convert Reranker protocol and NoOpReranker to async\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 2：CrossEncoderReranker 改 async + wait_for 超时

**Files:**
- Modify: `server/backend/app/rag/reranker.py`
- Modify: `server/tests/test_reranker.py`

**Interfaces:**
- Consumes: `TimeoutBudget`（`backend.app.timeout_policy`）
- Produces: `CrossEncoderReranker(model, *, metrics=None, output_top_k=15, timeout_seconds: float = 0.5)`
  - `async def rerank(...)`：在 `asyncio.wait_for` 内部 `await asyncio.to_thread(self.model.predict, pairs)`；超时或异常 → fallback + 打点

- [ ] **Step 1：改 CrossEncoderReranker 为 async**

```python
class CrossEncoderReranker:
    def __init__(
        self,
        model,
        *,
        metrics=None,
        output_top_k: int = 15,
        timeout_seconds: float = 0.5,
    ):
        self.model = model
        self.metrics = metrics
        self.output_top_k = output_top_k
        self.timeout_seconds = timeout_seconds

    async def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 15,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]:
        if not candidates:
            return []
        cap = min(top_k, self.output_top_k)
        pairs = [[query, self._passage_text(c)] for c in candidates]
        try:
            scores = await asyncio.wait_for(
                asyncio.to_thread(self.model.predict, pairs),
                timeout=self.timeout_seconds,
            )
            scores = list(scores)
        except asyncio.TimeoutError:
            _LOG.warning("CrossEncoderReranker.predict timed out after %ss", self.timeout_seconds)
            if self.metrics is not None:
                self.metrics.increment("retrieval.reranker.fallback.cross_failed")
            return list(candidates[:cap])
        except Exception:
            _LOG.warning("CrossEncoderReranker.predict failed", exc_info=True)
            if self.metrics is not None:
                self.metrics.increment("retrieval.reranker.fallback.cross_failed")
            return list(candidates[:cap])

        if self.metrics is not None:
            self.metrics.increment("retrieval.reranker.cross.calls")

        scored = list(zip(candidates, scores))
        scored.sort(key=lambda item: float(item[1]), reverse=True)
        reranked: list[ProductRetrievalResult] = []
        for candidate, score in scored[:cap]:
            reranked.append(
                ProductRetrievalResult(
                    product=candidate.product,
                    score=float(score),
                    evidence_chunks=candidate.evidence_chunks,
                )
            )
        return reranked
```

确保 `reranker.py` 顶部已经有 `import asyncio`，没有就加。

- [ ] **Step 2：改 TestCrossEncoderReranker 所有测试为 async**

所有方法加 `@pytest.mark.asyncio`，签名加 `async`，调用 `rerank` 处加 `await`。新增一个 timeout 测试：

```python
class SlowEncoder:
    """Encoder that sleeps longer than the timeout."""

    def __init__(self, score=0.9, delay_s=1.0):
        self.score = score
        self.delay_s = delay_s

    def predict(self, pairs):
        import time
        time.sleep(self.delay_s)
        return [self.score] * len(pairs)


class TestCrossEncoderReranker:
    # ... existing tests, all with @pytest.mark.asyncio and await ...

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_input_order(self):
        from backend.app.rag.reranker import CrossEncoderReranker

        c1 = self._result_with_title("p1", "a", 0.5)
        c2 = self._result_with_title("p2", "b", 0.5)
        metrics = StubMetrics()
        rer = CrossEncoderReranker(
            SlowEncoder(delay_s=1.0),
            metrics=metrics,
            timeout_seconds=0.05,
        )

        result = await rer.rerank("q", [c1, c2], top_k=10)
        assert [r.product.product_id for r in result] == ["p1", "p2"]
        assert metrics.counters.get("retrieval.reranker.fallback.cross_failed", 0) == 1
```

把现有 6 个测试逐一加 `@pytest.mark.asyncio` 和 `await`，并把 helper class `_result_with_title` 不需要改。`FakeEncoder` / `BrokenEncoder` / `StubMetrics` 不需要改（仍是同步 stub，被 to_thread 调用即可）。

- [ ] **Step 3：跑测试**

Run: `cd server && python -m pytest tests/test_reranker.py::TestCrossEncoderReranker -v`
Expected: 7 个 PASS（原 6 + 新增 1 timeout）

- [ ] **Step 4：commit**

```bash
git add server/backend/app/rag/reranker.py server/tests/test_reranker.py
git commit -m "$(printf 'refactor(rerank): make CrossEncoderReranker async with asyncio.wait_for timeout\n\n- run sentence-transformers predict via asyncio.to_thread\n- bind timeout_seconds default to 0.5 (matches TimeoutBudget)\n- timeout triggers fallback.cross_failed metric\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 3：LLMReranker 改 async + 接入 async LLMClient + 超时

**Files:**
- Modify: `server/backend/app/rag/reranker.py`
- Modify: `server/tests/test_reranker.py`

**Interfaces:**
- Consumes: 项目现有 `LLMClient._json_completion(messages, temperature=0) -> str`（async，返回 JSON 字符串）
- Produces: `LLMReranker(llm_client, *, metrics=None, top_n=8, timeout_seconds: float = 4.0)`
  - `async def rerank(...)`：构造 messages → `await asyncio.wait_for(llm_client._json_completion(messages), timeout=timeout_seconds)` → `json.loads(text)` → 解析

- [ ] **Step 1：改 LLMReranker 为 async**

```python
import json

class LLMReranker:
    SYSTEM_PROMPT = (
        "你是电商导购的重排器。根据用户查询，对候选商品按相关性从高到低排序。"
        "必须只输出 JSON 数组，格式为 [{\"product_id\": \"...\", \"rank\": 1}]。"
        "不要输出任何解释。"
    )

    def __init__(
        self,
        llm_client,
        *,
        metrics=None,
        top_n: int = 8,
        timeout_seconds: float = 4.0,
    ):
        self.llm_client = llm_client
        self.metrics = metrics
        self.top_n = top_n
        self.timeout_seconds = timeout_seconds

    async def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 8,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]:
        if not candidates:
            return []
        cap = min(top_k, self.top_n)
        input_window = list(candidates[:cap])

        try:
            ranked_ids = await self._invoke_llm(query, input_window)
        except asyncio.TimeoutError:
            _LOG.warning("LLMReranker timed out after %ss", self.timeout_seconds)
            self._record_fallback()
            return input_window
        except Exception:
            _LOG.warning("LLMReranker.invoke failed", exc_info=True)
            self._record_fallback()
            return input_window

        if ranked_ids is None:
            self._record_fallback()
            return input_window

        return self._reorder(ranked_ids, input_window)

    async def _invoke_llm(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
    ) -> list[str] | None:
        payload = [
            {
                "product_id": c.product.product_id,
                "title": c.product.title,
                "brand": c.product.brand,
                "price": c.product.price,
                "evidence": [chunk.excerpt for chunk in c.evidence_chunks[:3]],
            }
            for c in candidates
        ]
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"用户查询：{query}\n候选商品：{payload}\n请输出排序后的 JSON。"
                ),
            },
        ]
        raw = await asyncio.wait_for(
            self.llm_client._json_completion(messages),
            timeout=self.timeout_seconds,
        )
        if self.metrics is not None:
            self.metrics.increment("retrieval.reranker.llm.invoked")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return None
        return self._parse_response(parsed)

    @staticmethod
    def _parse_response(response) -> list[str] | None:
        if not isinstance(response, list):
            return None
        seen: list[str] = []
        for item in response:
            if not isinstance(item, dict):
                return None
            pid = item.get("product_id")
            if not isinstance(pid, str):
                return None
            seen.append(pid)
        return seen if seen else None

    def _reorder(
        self,
        ranked_ids: list[str],
        candidates: list[ProductRetrievalResult],
    ) -> list[ProductRetrievalResult]:
        by_id = {c.product.product_id: c for c in candidates}
        valid_ranked = [by_id[pid] for pid in ranked_ids if pid in by_id]
        if not valid_ranked:
            self._record_fallback()
            return candidates
        used = {c.product.product_id for c in valid_ranked}
        tail = [c for c in candidates if c.product.product_id not in used]
        return valid_ranked + tail

    def _record_fallback(self) -> None:
        if self.metrics is not None:
            self.metrics.increment("retrieval.reranker.fallback.llm_failed")
```

- [ ] **Step 2：改 FakeLLMClient 和 TestLLMReranker 为 async**

`FakeLLMClient` 改为提供 async `_json_completion` 方法（返回 JSON 字符串）：

```python
class FakeLLMClient:
    """Stub LLM client. responses queue feeds _json_completion return values."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    async def _json_completion(self, messages, temperature: float = 0):
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("no fake response queued")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, str):
            return response
        # 自动序列化非 string 响应，匹配真实接口语义
        import json
        return json.dumps(response)
```

每个 LLMReranker 测试加 `@pytest.mark.asyncio`、`async def`、`await rer.rerank(...)`。

新增 timeout 测试：

```python
class SlowLLMClient:
    def __init__(self, delay_s=1.0, response=None):
        self.delay_s = delay_s
        self.response = response if response is not None else "[]"

    async def _json_completion(self, messages, temperature: float = 0):
        await asyncio.sleep(self.delay_s)
        return self.response


@pytest.mark.asyncio
async def test_llm_reranker_timeout_falls_back(self):
    from backend.app.rag.reranker import LLMReranker
    c1 = self._result("p1")
    metrics = StubMetrics()
    rer = LLMReranker(SlowLLMClient(delay_s=1.0), metrics=metrics, timeout_seconds=0.05)
    result = await rer.rerank("q", [c1], top_k=8)
    assert [r.product.product_id for r in result] == ["p1"]
    assert metrics.counters.get("retrieval.reranker.fallback.llm_failed", 0) == 1
```

把这个测试和现有 5 个测试一起放在 `TestLLMReranker` 内部。

- [ ] **Step 3：跑测试**

Run: `cd server && python -m pytest tests/test_reranker.py::TestLLMReranker -v`
Expected: 6 个 PASS（原 5 + 新增 1 timeout）

- [ ] **Step 4：commit**

```bash
git add server/backend/app/rag/reranker.py server/tests/test_reranker.py
git commit -m "$(printf 'refactor(rerank): make LLMReranker async and use existing _json_completion\n\n- await llm_client._json_completion (project already-async API)\n- asyncio.wait_for with timeout_seconds default 4.0\n- timeout triggers fallback.llm_failed metric\n- FakeLLMClient now async to match real client\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 4：HybridReranker 改 async

**Files:**
- Modify: `server/backend/app/rag/reranker.py`
- Modify: `server/tests/test_reranker.py`

**Interfaces:**
- Produces: `HybridReranker(cross, llm, *, metrics=None, low_confidence_threshold=0.05)`
  - `async def rerank(...)`：`await self.cross.rerank(...)` → upgrade_scenario → 视场景 `await self.llm.rerank(...)`

- [ ] **Step 1：改 HybridReranker 为 async**

```python
class HybridReranker:
    def __init__(
        self,
        cross: "Reranker",
        llm: "Reranker | None",
        *,
        metrics=None,
        low_confidence_threshold: float = 0.05,
    ):
        self.cross = cross
        self.llm = llm
        self.metrics = metrics
        self.low_confidence_threshold = low_confidence_threshold

    async def rerank(
        self,
        query: str,
        candidates: list[ProductRetrievalResult],
        *,
        top_k: int = 15,
        scenario: RerankScenario | None = None,
    ) -> list[ProductRetrievalResult]:
        from .reranker_scenarios import RerankScenario as _Scenario, upgrade_scenario

        pre = scenario or _Scenario.DEFAULT
        cross_result = await self.cross.rerank(query, candidates, top_k=top_k, scenario=pre)

        scores = [r.score for r in cross_result]
        final_scenario = upgrade_scenario(pre, scores, self.low_confidence_threshold)
        self._record_scenario(final_scenario)

        llm_triggers = {_Scenario.COMPARISON, _Scenario.REFINEMENT, _Scenario.LOW_CONFIDENCE}
        if final_scenario in llm_triggers and self.llm is not None:
            return await self.llm.rerank(query, cross_result, top_k=top_k, scenario=final_scenario)
        return cross_result

    def _record_scenario(self, scenario: RerankScenario) -> None:
        if self.metrics is None:
            return
        self.metrics.increment(f"retrieval.reranker.scenario.{scenario.value}")
```

- [ ] **Step 2：改 TestHybridReranker 全部测试为 async**

所有方法加 `@pytest.mark.asyncio`，调用 hybrid.rerank 处加 `await`。

- [ ] **Step 3：跑测试**

Run: `cd server && python -m pytest tests/test_reranker.py tests/test_reranker_scenarios.py -v`
Expected: 全部 PASS（含本次新增 timeout 测试，总数 35 + 2 = 37）

- [ ] **Step 4：commit**

```bash
git add server/backend/app/rag/reranker.py server/tests/test_reranker.py
git commit -m "$(printf 'refactor(rerank): make HybridReranker async\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 5：build_reranker 接入 metrics 与 timeout_budget

**Files:**
- Modify: `server/backend/app/rag/reranker.py`
- Modify: `server/tests/test_reranker.py`

**Interfaces:**
- Produces: `build_reranker(settings, *, llm_client=None, metrics=None, timeout_budget=None) -> Reranker`
  - 内部把 `timeout_budget.rerank_cross_seconds` / `rerank_llm_seconds` 注入 reranker 构造

- [ ] **Step 1：修改 build_reranker**

```python
def build_reranker(
    settings,
    *,
    llm_client=None,
    metrics=None,
    timeout_budget=None,
) -> "Reranker":
    if not getattr(settings, "rerank_enabled", False):
        return NoOpReranker()

    if timeout_budget is None:
        from ..timeout_policy import TimeoutBudget
        timeout_budget = TimeoutBudget()

    model_dir = getattr(settings, "rerank_model_dir", "")
    device = getattr(settings, "rerank_device", "cpu")

    try:
        model = _load_cross_encoder(model_dir, device)
    except Exception:
        _LOG.warning("Reranker model load failed at %s", model_dir, exc_info=True)
        if metrics is not None:
            metrics.increment("retrieval.reranker.fallback.no_model")
        return NoOpReranker()

    cross = CrossEncoderReranker(
        model,
        metrics=metrics,
        output_top_k=getattr(settings, "rerank_output_top_k", 15),
        timeout_seconds=timeout_budget.rerank_cross_seconds,
    )
    if getattr(settings, "rerank_llm_enabled", False) and llm_client is not None:
        llm = LLMReranker(
            llm_client,
            metrics=metrics,
            top_n=getattr(settings, "rerank_llm_top_n", 8),
            timeout_seconds=timeout_budget.rerank_llm_seconds,
        )
        return HybridReranker(
            cross,
            llm,
            metrics=metrics,
            low_confidence_threshold=getattr(settings, "rerank_low_confidence_threshold", 0.05),
        )
    return cross
```

- [ ] **Step 2：跑 build_reranker 测试**

Run: `cd server && python -m pytest tests/test_reranker.py::TestBuildReranker -v`
Expected: 4 个 PASS（不需要改测试，timeout_budget 是可选）

- [ ] **Step 3：commit**

```bash
git add server/backend/app/rag/reranker.py
git commit -m "$(printf 'feat(rerank): plumb TimeoutBudget through build_reranker\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 6：AdaptiveRetriever 提供 async search

**Files:**
- Modify: `server/backend/app/adaptive_retriever.py`

**Interfaces:**
- Produces: `AdaptiveRetriever.search_async(plan, top_k=30) -> list[tuple[Product, float]]`：async 版本，走 hybrid + reranker 路径；hybrid 失败时回退到 base retriever 的同步 search 渐进放松循环

- [ ] **Step 1：在 AdaptiveRetriever 中新增 search_async**

在现有 `search` 同级新增：

```python
    async def search_async(self, plan: RetrievalPlan, top_k: int = 30) -> list[tuple[Product, float]]:
        """Async path: hybrid retrieval → optional reranker → fallback to sync search if hybrid fails."""
        self.last_evidence_by_product = {}
        if self.hybrid_retriever is not None:
            try:
                from .rag.types import format_chunk_evidence

                if hasattr(self.hybrid_retriever, "search_with_evidence"):
                    hybrid_results = self.hybrid_retriever.search_with_evidence(plan, top_k=top_k)
                else:
                    raw_results = self.hybrid_retriever.search(plan, top_k=top_k)
                    if raw_results:
                        if self.metrics is not None:
                            self.metrics.increment("retrieval.hybrid.success")
                        return raw_results
                    hybrid_results = []
                if hybrid_results:
                    if self.reranker is not None:
                        from .rag.reranker_scenarios import detect_pre_scenario
                        pre_scenario = detect_pre_scenario(plan)
                        hybrid_results = await self.reranker.rerank(
                            plan.retrieval_query or "",
                            hybrid_results,
                            top_k=top_k,
                            scenario=pre_scenario,
                        )
                    self.last_evidence_by_product = {
                        result.product.product_id: [
                            text
                            for text in (format_chunk_evidence(chunk) for chunk in result.evidence_chunks)
                            if text
                        ]
                        for result in hybrid_results
                    }
                    if self.metrics is not None:
                        self.metrics.increment("retrieval.hybrid.success")
                    return [(result.product, result.score) for result in hybrid_results]
                if self.metrics is not None:
                    self.metrics.increment("retrieval.fallback.used")
            except Exception:
                if self.metrics is not None:
                    self.metrics.increment("retrieval.fallback.used")
                pass

        # Fallback: identical sync logic from search()
        return self.search(plan, top_k=top_k)
```

注意：保留现有同步 `search()` 完全不变；reranker 调用从同步 search 移除（在 Task 9 完成后再清掉，本任务先双轨）。等 Task 7 把 agent 切到 search_async 后，Task 8 会清理同步 search 中的 reranker 重复代码。

实际上为了避免双轨混乱，**本任务直接把同步 `search` 中的 reranker 调用块删除**——因为同步 search 调用方在改 async 后不再被业务代码使用，仅为测试兼容存在；reranker 必须走 async 路径。

修改同步 `search()`，把原来的 reranker 块移除（让同步 search 又回到不知道 reranker 的状态）：

```python
    def search(self, plan: RetrievalPlan, top_k: int = 30) -> list[tuple[Product, float]]:
        """Sync path: hybrid retrieval without reranker. Kept for backward compat;
        async path (search_async) is the canonical entry for reranker usage."""
        self.last_evidence_by_product = {}
        if self.hybrid_retriever is not None:
            try:
                from .rag.types import format_chunk_evidence

                if hasattr(self.hybrid_retriever, "search_with_evidence"):
                    hybrid_results = self.hybrid_retriever.search_with_evidence(plan, top_k=top_k)
                else:
                    raw_results = self.hybrid_retriever.search(plan, top_k=top_k)
                    if raw_results:
                        if self.metrics is not None:
                            self.metrics.increment("retrieval.hybrid.success")
                        return raw_results
                    hybrid_results = []
                if hybrid_results:
                    self.last_evidence_by_product = {
                        result.product.product_id: [
                            text
                            for text in (format_chunk_evidence(chunk) for chunk in result.evidence_chunks)
                            if text
                        ]
                        for result in hybrid_results
                    }
                    if self.metrics is not None:
                        self.metrics.increment("retrieval.hybrid.success")
                    return [(result.product, result.score) for result in hybrid_results]
                if self.metrics is not None:
                    self.metrics.increment("retrieval.fallback.used")
            except Exception:
                if self.metrics is not None:
                    self.metrics.increment("retrieval.fallback.used")
                pass

        # Relaxation loop (unchanged)
        merged: dict[str, tuple[Product, float]] = {}
        for round_index in range(self.policy.max_rounds):
            relaxed_plan = self._build_relaxed_plan(plan, round_index)
            retrieved = self.retriever.search(relaxed_plan.retrieval_query, top_k=top_k)
            for product, score in retrieved:
                if product.product_id in merged:
                    existing_product, existing_score = merged[product.product_id]
                    merged[product.product_id] = (existing_product, max(existing_score, score))
                else:
                    merged[product.product_id] = (product, score)
            if len(merged) >= self.policy.min_candidates:
                break
        return sorted(merged.values(), key=lambda item: item[1], reverse=True)[:top_k]
```

- [ ] **Step 2：跑现有同步 search 测试 + 集成测试，验证零回归**

Run: `cd server && python -m pytest tests/test_adaptive_retriever.py tests/test_hybrid_retrieval.py -v`
Expected: 全部 PASS

- [ ] **Step 3：commit**

```bash
git add server/backend/app/adaptive_retriever.py
git commit -m "$(printf 'feat(rerank): add AdaptiveRetriever.search_async with async reranker path\n\n- search_async: hybrid + await reranker + fallback to sync search\n- sync search: keeps original behavior, no reranker call\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 7：ShopGuideAgent.retrieve_and_rank 改 async

**Files:**
- Modify: `server/backend/app/agent.py`
- Modify: `server/backend/app/tools/retrieval.py`

**Interfaces:**
- Produces: `ShopGuideAgent.retrieve_and_rank` 变为 `async def`，内部 `await self.adaptive_retriever.search_async(...)`；所有调用方加 `await`

- [ ] **Step 1：改 agent.py 中 retrieve_and_rank 为 async**

```python
    async def retrieve_and_rank(self, plan: RetrievalPlan, limit: int = 8, session_id: str = "") -> list[RankedProduct]:
        cached_base: list[RankedProduct] | None = None
        if self.memory_cache and plan.intent in {"recommend_product", "product_followup"}:
            cached_base = self.memory_cache.get(plan, self.product_map)

        if cached_base is not None:
            ranked = list(cached_base)
        else:
            retrieved = await self.adaptive_retriever.search_async(plan, top_k=30)
            # ... rest of the method body unchanged ...
```

把 line 163 的 `retrieved = self.adaptive_retriever.search(plan, top_k=30)` 改为 `retrieved = await self.adaptive_retriever.search_async(plan, top_k=30)`。

- [ ] **Step 2：改 agent.py 中的所有内部调用方**

- Line 449：`ranked = [item for item in self.retrieve_and_rank(plan, session_id=request.session_id) ...]` → `ranked = [item for item in await self.retrieve_and_rank(plan, session_id=request.session_id) ...]`
- Line 968：`ranked = self.retrieve_and_rank(slot_plan, session_id=request.session_id)` → `ranked = await self.retrieve_and_rank(slot_plan, session_id=request.session_id)`

调用 retrieve_and_rank 的方法本身都是 async（line 449 在 `_stream_followup`、line 968 在另一个 async 方法中）。请按 grep 结果挨个检查每个调用点周边的方法签名是否是 async；若不是，**当前 task 不允许冒犯进一步把调用方改 async**——遇到这种情况停下来标记 BLOCKED，由 controller 介入。

- [ ] **Step 3：改 tools/retrieval.py**

Line 27：`ranked = self._agent.retrieve_and_rank(plan, session_id=request.session_id)`

先查这个方法所在类是否 async：grep 出方法体上下文。如果是 async（很可能因为 tool 接口是 async stream），直接加 `await`：

```python
ranked = await self._agent.retrieve_and_rank(plan, session_id=request.session_id)
```

- [ ] **Step 4：跑 agent 与 tools 相关测试**

Run: `cd server && python -m pytest tests/test_agent_core.py tests/test_bugfix_phase3.py tests/test_tool_dispatch.py -v --tb=short`
Expected: 期待会有 ~10 个 sync 测试失败（因为调用 sync 方法签名后变 coroutine 没 await）；这些测试在 Task 8 修复。本步骤只确保业务代码本身的逻辑改完不抛 ImportError/AttributeError。

- [ ] **Step 5：commit**

```bash
git add server/backend/app/agent.py server/backend/app/tools/retrieval.py
git commit -m "$(printf 'refactor(rerank): make ShopGuideAgent.retrieve_and_rank async\n\n- await adaptive_retriever.search_async\n- update agent.py and tools/retrieval.py callers to use await\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 8：测试调用方改 async

**Files:**
- Modify: `server/tests/test_agent_core.py`
- Modify: `server/tests/test_bugfix_phase3.py`

**Interfaces:** 无新接口；只调整测试到 async。

- [ ] **Step 1：列出所有 retrieve_and_rank 调用位置**

Run: `cd server && grep -nE "agent\.retrieve_and_rank|probe_agent\.retrieve_and_rank" tests/`

把每一处所在的测试函数加 `@pytest.mark.asyncio`（顶部 `import pytest` 已有则不加），方法签名前加 `async`，调用前加 `await`。

涉及的测试函数预估约 7 个（test_agent_core.py 的 5-6 处加 test_bugfix_phase3.py 的 2 处）。改造模板：

修改前：
```python
def test_something():
    ...
    ranked_a = agent.retrieve_and_rank(plan, session_id="A_session")
```

修改后：
```python
@pytest.mark.asyncio
async def test_something():
    ...
    ranked_a = await agent.retrieve_and_rank(plan, session_id="A_session")
```

- [ ] **Step 2：跑修改后的测试**

Run: `cd server && python -m pytest tests/test_agent_core.py tests/test_bugfix_phase3.py -v --tb=short`
Expected: 全部 PASS

- [ ] **Step 3：跑 hybrid retrieval 与 reranker 测试一并验证**

Run: `cd server && python -m pytest tests/test_reranker.py tests/test_reranker_scenarios.py tests/test_hybrid_retrieval.py tests/test_agent_core.py tests/test_bugfix_phase3.py tests/test_adaptive_retriever.py tests/test_tool_dispatch.py -v --tb=short`
Expected: 全部 PASS

- [ ] **Step 4：commit**

```bash
git add server/tests/test_agent_core.py server/tests/test_bugfix_phase3.py
git commit -m "$(printf 'test(rerank): convert retrieve_and_rank callers to async\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 9：main.py 提前 metrics 创建、传入 reranker

**Files:**
- Modify: `server/backend/app/main.py`

**Interfaces:** 不变。

- [ ] **Step 1：修改 create_app 顺序**

把当前 `metrics = InMemoryMetrics()` 与 `app.state.metrics = metrics` 两行（约 line 110-111）移到 `reranker = build_reranker(...)` 之前。

```python
    # Build metrics first so reranker can record into the same instance.
    metrics = InMemoryMetrics()

    # Reranker: now wired to real metrics + llm_client + timeout budget.
    reranker = build_reranker(
        settings,
        llm_client=llm_client if not isinstance(llm_client, FakeLLMClient) else None,
        metrics=metrics,
        timeout_budget=None,  # uses TimeoutBudget() default
    )
```

把 reranker 构造下方的 `metrics = InMemoryMetrics()` 那行删掉（保留 `app.state.metrics = metrics`）。删去原本的注释 `llm_client wiring deferred until sync chat_json_sync is available; cross-only / no-op for now`，改成：

```python
    # Reranker uses async LLMClient._json_completion; cross+LLM hybrid path active.
```

- [ ] **Step 2：跑全部测试**

Run: `cd server && python -m pytest tests/ -v --tb=short`
Expected: 全部 PASS

- [ ] **Step 3：commit**

```bash
git add server/backend/app/main.py
git commit -m "$(printf 'feat(rerank): wire metrics and llm_client into create_app reranker\n\n- InMemoryMetrics created before build_reranker so reranker metrics record\n- pass real llm_client (with circuit breaker) to enable LLM rerank path\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 10：清理与一致性

**Files:**
- Modify: `server/backend/app/rag/reranker.py`

**Interfaces:** 不变。

- [ ] **Step 1：清理 `_passage_text` 中硬编码 256 截断的注释**

```python
    @staticmethod
    def _passage_text(candidate: ProductRetrievalResult) -> str:
        """Choose the most relevant text for the (query, passage) cross-encoder input.

        Prefers the first evidence chunk excerpt (highest-scored match in retrieval),
        falling back to title + marketing description capped at 256 chars to keep
        the cross-encoder input within reasonable token budgets.
        """
        if candidate.evidence_chunks:
            text = candidate.evidence_chunks[0].excerpt.strip()
            if text:
                return text
        product = candidate.product
        title = product.title or ""
        marketing = getattr(product, "marketing_description", "") or ""
        joined = (title + " " + marketing).strip()
        return joined[:256]
```

- [ ] **Step 2：跑测试确保无回归**

Run: `cd server && python -m pytest tests/test_reranker.py -v`
Expected: 全部 PASS

- [ ] **Step 3：commit**

```bash
git add server/backend/app/rag/reranker.py
git commit -m "$(printf 'docs(rerank): document 256-char passage cap in CrossEncoderReranker\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
```

---

## Task 11：全量回归 + 验证最终评测

**Files:** 无新增；仅运行验证。

- [ ] **Step 1：跑全部后端测试**

Run: `cd server && python -m pytest tests/ -v --tb=short`
Expected: 405+ passed, 0 failed（与之前持平或略多，因新增 2 个 timeout 测试）

- [ ] **Step 2：跑两份评测集对照**

Run:
```bash
cd /home/huadabioa/houlong/SoulDance/server
RERANK_ENABLED=false python scripts/run_eval.py --scenarios /home/huadabioa/houlong/SoulDance/data/eval/core.json --fake-llm --min-pass-rate 0 2>&1 | grep -A 20 "attribution_summary" | tail -12 > /tmp/eval_core_off.txt
RERANK_ENABLED=true RERANK_LLM_ENABLED=false python scripts/run_eval.py --scenarios /home/huadabioa/houlong/SoulDance/data/eval/core.json --fake-llm --min-pass-rate 0 2>&1 | grep -A 20 "attribution_summary" | tail -12 > /tmp/eval_core_on.txt
diff /tmp/eval_core_off.txt /tmp/eval_core_on.txt
```

Expected: 两份输出指标完全一致（因本地无模型，build_reranker 回退到 NoOp）。

- [ ] **Step 3：写终审报告**

把测试结果（passed/skipped/failed 计数）+ 评测对照写入 `/home/huadabioa/houlong/SoulDance/.superpowers/sdd/reranker-followup-final-report.md`。

---

## 自检结论

- **Spec 覆盖**：Final Review 的 4 个 Important findings 全部对应到任务（async 改造 → Task 1-8；metrics 注入 → Task 9；timeout wrap → Task 2/3/5；LLM 接入 → Task 3）
- **Placeholder 扫描**：所有步骤含完整代码 / 命令 / 预期输出
- **类型一致性**：`Reranker.rerank` 全链路 async、所有四种实现一致；`build_reranker` 新 signature 一处定义、一处使用
- **commit 粒度**：11 个 Task 各一次 commit
