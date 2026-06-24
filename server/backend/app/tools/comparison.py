from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class CompareProductsTool:
    name = "compare_products"
    description = "Compare recent or explicitly referenced real products"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        user_id = kwargs.get("user_id", "anonymous")
        for event in await self._agent._build_comparison_events(user_id, request):
            yield event
