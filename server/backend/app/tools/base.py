from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from ..models import ChatRequest, SessionContext


class Tool(Protocol):
    name: str
    description: str

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        ...
