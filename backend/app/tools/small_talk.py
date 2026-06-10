from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class SmallTalkTool:
    name = "small_talk"
    description = "闲聊回应"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        intent = kwargs.get("intent", "small_talk")
        async for event in self._agent._stream_no_retrieval_events(request, intent):
            yield event
