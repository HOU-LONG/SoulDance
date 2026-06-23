from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class RetrieveProductsTool:
    name = "recommend_product"
    description = "检索并推荐商品"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        plan = kwargs.get("plan")
        compiled_ir = kwargs.get("compiled_ir")
        context_action = kwargs.get("context_action", "same_task")
        memory_hit = kwargs.get("memory_hit")
        if memory_hit is not None:
            async for event in self._agent._stream_recommendation_events(
                request, plan, memory_hit.ranked, context_action,
                memory_mode=memory_hit.mode, selected_override=memory_hit.ranked, cached_summary=memory_hit.summary,
            ):
                yield event
            return
        ranked = self._agent.retrieve_and_rank(plan, session_id=request.session_id)
        async for event in self._agent._stream_recommendation_events(request, plan, ranked, context_action):
            yield event
