from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class TimeoutBudget:
    intent_seconds: float = 3.0
    retrieval_seconds: float = 2.0
    selection_seconds: float = 4.0
    response_first_chunk_seconds: float = 12.0
    tts_seconds: float = 10.0


async def run_with_timeout(
    awaitable: Awaitable[T],
    timeout_seconds: float,
    fallback: T,
) -> T:
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return fallback
