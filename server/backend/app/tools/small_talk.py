from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class SmallTalkTool:
    name = "small_talk"
    description = "闲聊回应"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        user_id = kwargs.get("user_id", "anonymous")
        # ToolPlanner 路径下 tool_plan.tool == "chitchat"，旧路径下走 intent kwarg。
        # 默认 "small_talk"，product_followup tool 调过来时传 intent="unclear_input" 等保留兼容。
        intent = kwargs.get("intent", "small_talk")
        async for event in self._agent._stream_no_retrieval_events(user_id, request, intent):
            yield event
