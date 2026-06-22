from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator


class ConcurrencyGuard:
    """并发控制器，管理 LLM 调用信号量和 WebSocket 连接数。"""

    def __init__(self, max_llm_calls: int = 10, max_connections: int = 50):
        self.max_llm_calls = max_llm_calls
        self.max_connections = max_connections
        self._llm_semaphore = asyncio.Semaphore(max_llm_calls)
        self._active_connections = 0

    @property
    def active_connections(self) -> int:
        return self._active_connections

    async def acquire_llm(self) -> None:
        """获取一个 LLM 调用许可。"""
        await self._llm_semaphore.acquire()

    def release_llm(self) -> None:
        """释放一个 LLM 调用许可。"""
        self._llm_semaphore.release()

    @asynccontextmanager
    async def llm_slot(self) -> AsyncGenerator[None, None]:
        """LLM 调用许可的异步上下文管理器。"""
        await self.acquire_llm()
        try:
            yield
        finally:
            self.release_llm()

    def connection_enter(self) -> None:
        """WebSocket 连接建立时调用。"""
        if self._active_connections >= self.max_connections:
            raise RuntimeError(f"Max connections ({self.max_connections}) reached")
        self._active_connections += 1

    def connection_exit(self) -> None:
        """WebSocket 连接断开时调用。"""
        if self._active_connections > 0:
            self._active_connections -= 1
