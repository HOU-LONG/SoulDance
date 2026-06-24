from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, RetrievalPlan, SessionContext


class ScenarioBundleTool:
    name = "scenario_bundle"
    description = "Build grouped scenario bundle recommendations"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        plan = kwargs.get("plan") or RetrievalPlan(
            intent="scenario_bundle",
            retrieval_mode="decompose_parallel",
            retrieval_query=request.message,
        )
        user_id = kwargs.get("user_id", "anonymous")
        for event in await self._agent._build_bundle_events(user_id, request, plan):
            yield event
