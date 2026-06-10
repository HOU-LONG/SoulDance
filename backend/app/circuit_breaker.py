from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """熔断器状态机。

    状态流转：
        CLOSED  -> 连续失败达到阈值 -> OPEN
        OPEN    -> 超过 recovery_timeout -> HALF_OPEN
        HALF_OPEN -> 成功 -> CLOSED
        HALF_OPEN -> 失败 -> OPEN
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def can_execute(self) -> bool:
        """判断当前是否允许执行请求。"""
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if self._last_failure_time is not None:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    return True
            return False
        # HALF_OPEN: 允许一个探测请求
        return True

    def record_success(self) -> None:
        """记录一次成功请求。"""
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """记录一次失败请求。"""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
        elif self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    async def call(self, fn: Callable[..., Any], fallback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """在熔断器保护下执行异步函数，失败时调用 fallback。

        注意：仅适用于 async 函数（返回值），不适用于 async generator。
        对于流式输出请使用 call_stream()。
        """
        if not self.can_execute():
            return await fallback(*args, **kwargs)
        try:
            result = await fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            return await fallback(*args, **kwargs)

    async def call_stream(self, generator_fn, fallback_gen, *args: Any, **kwargs: Any):
        """在熔断器保护下执行异步生成器，失败时切换至 fallback 生成器。"""
        if not self.can_execute():
            async for chunk in fallback_gen(*args, **kwargs):
                yield chunk
            return
        try:
            async for chunk in generator_fn(*args, **kwargs):
                yield chunk
            self.record_success()
        except Exception:
            self.record_failure()
            async for chunk in fallback_gen(*args, **kwargs):
                yield chunk
