import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.app.circuit_breaker import CircuitBreaker, CircuitState
from backend.app.llm_client import FakeLLMClient


class FailingLLM(FakeLLMClient):
    def __init__(self, fail_count=5):
        self.fail_count = fail_count
        self.calls = 0

    async def generate_response(self, user_message, plan, ranked_products, focus_product=None):
        self.calls += 1
        if self.calls <= self.fail_count:
            raise RuntimeError("LLM failure")
        return "success"


class SuccessLLM(FakeLLMClient):
    async def generate_response(self, user_message, plan, ranked_products, focus_product=None):
        return "success"


def test_circuit_starts_closed():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_circuit_counts_failures_while_closed():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 2


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_circuit_allows_request_in_half_open():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    # simulate time passing
    cb._last_failure_time = 0.0
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_closes_on_half_open_success():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.0)
    cb.record_failure()
    cb.record_failure()
    cb._last_failure_time = 0.0
    assert cb.can_execute() is True
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_circuit_reopens_on_half_open_failure():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.0)
    cb.record_failure()
    cb.record_failure()
    cb._last_failure_time = 0.0
    assert cb.can_execute() is True
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_open_circuit_blocks_execution():
    cb = CircuitBreaker(failure_threshold=1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


@pytest.mark.asyncio
async def test_wrapper_uses_fallback_when_open():
    from backend.app.llm_client import LLMClientWithBreaker

    failing_llm = FailingLLM(fail_count=10)
    wrapper = LLMClientWithBreaker(failing_llm, failure_threshold=1, recovery_timeout=60.0)

    # first call fails but wrapper catches exception and falls back
    result = await wrapper.generate_response("msg", None, [])
    assert wrapper.breaker.state == CircuitState.OPEN
    assert "结论" in result or "没有找到" in result

    # second call should also fallback to FakeLLMClient
    result2 = await wrapper.generate_response("msg", None, [])
    assert "结论" in result2 or "没有找到" in result2


@pytest.mark.asyncio
async def test_wrapper_resets_to_closed_on_success():
    from backend.app.llm_client import LLMClientWithBreaker

    failing_llm = FailingLLM(fail_count=1)
    wrapper = LLMClientWithBreaker(failing_llm, failure_threshold=2, recovery_timeout=0.0)

    # first call fails but wrapper catches and falls back; breaker still closed
    result = await wrapper.generate_response("msg", None, [])
    assert wrapper.breaker.state == CircuitState.CLOSED
    assert "结论" in result or "没有找到" in result

    # wait then call again; half-open -> success -> closed
    await asyncio.sleep(0.01)
    result2 = await wrapper.generate_response("msg", None, [])
    assert result2 == "success"
    assert wrapper.breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_wrapper_forwards_success_when_closed():
    from backend.app.llm_client import LLMClientWithBreaker

    success_llm = SuccessLLM()
    wrapper = LLMClientWithBreaker(success_llm)
    result = await wrapper.generate_response("msg", None, [])
    assert result == "success"
    assert wrapper.breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_wrapper_all_methods_are_wrapped():
    from backend.app.llm_client import LLMClientWithBreaker

    class CountingLLM(FakeLLMClient):
        def __init__(self):
            self.count = 0

        async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
            self.count += 1
            return "{}"

        async def select_products(self, user_message, plan, candidates):
            self.count += 1
            return "{}"

        async def classify_contextual_followup(self, message, context):
            self.count += 1
            return "{}"

        async def generate_response(self, user_message, plan, ranked_products, focus_product=None):
            self.count += 1
            return "ok"

        async def stream_response(self, user_message, plan, ranked_products, focus_product=None):
            self.count += 1
            yield "ok"

        async def stream_chitchat_response(self, user_message, intent, context=None):
            self.count += 1
            yield "ok"

    counting = CountingLLM()
    wrapper = LLMClientWithBreaker(counting)

    await wrapper.parse_semantic_frame("hi")
    await wrapper.select_products("msg", None, [])
    await wrapper.classify_contextual_followup("hi", {})
    await wrapper.generate_response("msg", None, [])
    async for _ in wrapper.stream_response("msg", None, []):
        pass
    async for _ in wrapper.stream_chitchat_response("hi", "small_talk"):
        pass

    assert counting.count == 6
