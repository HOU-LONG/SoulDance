from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class ProductFollowupTool:
    name = "product_followup"
    description = "Handle focused product follow-up, explanation, and replacement recommendations"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        user_id = kwargs.get("user_id", "anonymous")
        compiled_ir = kwargs.get("compiled_ir")
        async for event in self._agent._stream_followup(user_id, request, compiled_ir):
            yield event
