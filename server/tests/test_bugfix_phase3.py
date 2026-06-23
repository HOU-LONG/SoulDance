"""Bug 修复回归测试：

Bug 1: LLMClientWithBreaker 没有 _json_completion → comparison_engine 报 AttributeError
Bug 2: _stream_no_retrieval_events 没超时 → 整条 ws 可能被 LLM 卡死
Bug 3: memory_cache 命中后跳过 feedback_ranker.apply，跨 session 个性化数据泄漏
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.app.agent import (
    DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS,
    ShopGuideAgent,
    _stream_with_first_chunk_timeout,
)
from backend.app.llm_client import FakeLLMClient, LLMClientWithBreaker
from backend.app.memory_cache import StructuredMemoryCache
from backend.app.models import (
    ChatRequest,
    HardConstraints,
    Product,
    RankedProduct,
    RetrievalPlan,
)


# ---------- Bug 1: LLMClientWithBreaker._json_completion ----------


class _JsonStubClient(FakeLLMClient):
    def __init__(self, payload: str = '{"ok": true}'):
        self.payload = payload
        self.calls = 0

    async def _json_completion(self, messages: list[dict[str, str]], temperature: float = 0) -> str:
        self.calls += 1
        return self.payload


def test_llm_client_with_breaker_exposes_json_completion():
    """ComparisonEngine 直接调 breaker._json_completion 不应抛 AttributeError。"""
    stub = _JsonStubClient('{"hello": "world"}')
    breaker = LLMClientWithBreaker(stub)
    result = asyncio.run(breaker._json_completion([{"role": "user", "content": "x"}]))
    assert result == '{"hello": "world"}'
    assert stub.calls == 1


def test_llm_client_with_breaker_json_completion_fallback_on_failure():
    """底层 _json_completion 抛异常时返回空 JSON 兜底（让下游走 rule-based 降级）。"""

    class _FailingClient(FakeLLMClient):
        async def _json_completion(self, messages, temperature=0):
            raise RuntimeError("upstream down")

    breaker = LLMClientWithBreaker(_FailingClient())
    result = asyncio.run(breaker._json_completion([{"role": "user", "content": "x"}]))
    assert result == "{}"


# ---------- Bug 2: _stream_with_first_chunk_timeout ----------


async def _slow_first_chunk(*, delay: float):
    await asyncio.sleep(delay)
    yield "late chunk"


async def _normal_stream(chunks: list[str]):
    for chunk in chunks:
        yield chunk


async def _hang_after_first(first_chunk: str, hang_seconds: float):
    yield first_chunk
    await asyncio.sleep(hang_seconds)
    yield "should never be reached"


def test_stream_first_chunk_timeout_returns_empty_when_too_slow():
    """首块超时后，包装迭代器应直接终止，不抛异常。"""

    async def main():
        chunks: list[str] = []
        async for chunk in _stream_with_first_chunk_timeout(
            _slow_first_chunk(delay=2.0),
            first_chunk_timeout=0.05,
            chunk_timeout=0.05,
        ):
            chunks.append(chunk)
        return chunks

    assert asyncio.run(main()) == []


def test_stream_first_chunk_timeout_yields_chunks_when_fast():
    """流速正常时不应受超时影响。"""

    async def main():
        chunks: list[str] = []
        async for chunk in _stream_with_first_chunk_timeout(
            _normal_stream(["a", "b", "c"]),
            first_chunk_timeout=1.0,
            chunk_timeout=1.0,
        ):
            chunks.append(chunk)
        return chunks

    assert asyncio.run(main()) == ["a", "b", "c"]


def test_stream_chunk_timeout_terminates_mid_stream_when_subsequent_chunks_hang():
    """首块到了但后续 chunk 卡死：迭代终止，不卡死。已发出的首块保留。"""

    async def main():
        chunks: list[str] = []
        async for chunk in _stream_with_first_chunk_timeout(
            _hang_after_first("first", hang_seconds=2.0),
            first_chunk_timeout=1.0,
            chunk_timeout=0.1,
        ):
            chunks.append(chunk)
        return chunks

    assert asyncio.run(main()) == ["first"]


# ---------- Bug 3: memory_cache 命中后必须 apply feedback_ranker ----------


class _RecordingFeedbackRanker:
    """记录每次被调用时的 session_id，便于断言 cache 命中后仍被调用。"""

    def __init__(self):
        self.calls: list[str] = []

    def apply(self, ranked: list[RankedProduct], session_id: str) -> list[RankedProduct]:
        self.calls.append(session_id)
        # 按 session_id 第一个字符做"个性化"重排（只是为了证明被调用了）
        if session_id.startswith("A"):
            return list(reversed(ranked))
        return ranked


class _StaticRetriever:
    """固定返回前 N 个商品，让 ranking 完全确定。"""

    def __init__(self, products: list[Product]):
        self.products = products

    def search(self, query, top_k: int = 20) -> list[tuple[Product, float]]:
        return [(p, 1.0 / (i + 1)) for i, p in enumerate(self.products[:top_k])]


def _build_simple_products() -> list[Product]:
    return [
        Product(
            product_id=f"p_{i}",
            title=f"Product {i}",
            brand="B",
            category="美妆护肤",
            sub_category="防晒",
            price=100.0 + i,
            image_path="",
            chunk=f"chunk {i}",
            search_text=f"product {i}",
        )
        for i in range(3)
    ]


def test_memory_cache_hit_still_applies_feedback_ranker_per_session():
    """关键断言：cache 命中后必须按当前 session_id 重新走 feedback_ranker。

    场景：session A 先查 → cache miss → 写入基础排序，A 的反馈把顺序反转
          session B 后查相同 plan → cache 命中 → 应该按 B 的反馈处理（不反转），
          而不是直接 return 已被 A 反转过的列表。
    """
    products = _build_simple_products()
    ranker = _RecordingFeedbackRanker()
    agent = ShopGuideAgent(
        products,
        FakeLLMClient(),
        _StaticRetriever(products),
        memory_cache=StructuredMemoryCache(),
        feedback_ranker=ranker,
    )
    plan = RetrievalPlan(
        intent="recommend_product",
        retrieval_mode="hybrid_retrieval",
        category="美妆护肤",
        hard_constraints=HardConstraints(category="美妆护肤", sub_category="防晒"),
        retrieval_query="防晒",
    )

    # Session A 先查：cache miss → 写入 → A 的 ranker 反转
    ranked_a = agent.retrieve_and_rank(plan, session_id="A_session")
    # Session B 后查（相同 plan）：cache 命中 → B 的 ranker 不反转
    ranked_b = agent.retrieve_and_rank(plan, session_id="B_session")

    # ranker 必须被两个 session 各调用一次
    assert ranker.calls == ["A_session", "B_session"]
    # B 看到的是基础顺序 p_0, p_1, p_2（未被 A 的反馈污染）
    assert [r.product.product_id for r in ranked_b] == ["p_0", "p_1", "p_2"]
    # A 看到的是反转后顺序
    assert [r.product.product_id for r in ranked_a] == ["p_2", "p_1", "p_0"]


def test_memory_cache_stores_base_ranking_not_personalized():
    """cache 内部存的应该是未被 feedback_ranker 处理过的基础结果。"""
    products = _build_simple_products()
    ranker = _RecordingFeedbackRanker()
    agent = ShopGuideAgent(
        products,
        FakeLLMClient(),
        _StaticRetriever(products),
        memory_cache=StructuredMemoryCache(),
        feedback_ranker=ranker,
    )
    plan = RetrievalPlan(
        intent="recommend_product",
        retrieval_mode="hybrid_retrieval",
        category="美妆护肤",
        hard_constraints=HardConstraints(category="美妆护肤", sub_category="防晒"),
        retrieval_query="防晒",
    )
    # 触发一次写入
    agent.retrieve_and_rank(plan, session_id="A_session")
    # 直接从 cache 读出来，应该是基础顺序，与 ranker 的反转无关
    cached = agent.memory_cache.get(plan, agent.product_map)
    assert cached is not None
    assert [r.product.product_id for r in cached] == ["p_0", "p_1", "p_2"]
