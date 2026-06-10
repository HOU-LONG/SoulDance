from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class ClarifyTool:
    name = "clarification"
    description = "澄清请求"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        plan = kwargs.get("plan")
        context_action = kwargs.get("context_action", "same_task")
        for event in self._agent._build_clarification_events(context, plan, context_action):
            yield event
