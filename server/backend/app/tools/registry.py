from __future__ import annotations

from .base import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, intent: str) -> Tool | None:
        return self._tools.get(intent)

    async def execute(self, intent: str, request, context, **kwargs):
        tool = self.get(intent)
        if tool is None:
            tool = self.get("small_talk")
            kwargs.setdefault("intent", intent)
        if tool is None:
            yield {"type": "error", "message": f"no tool for intent: {intent}"}
            return
        async for event in tool.execute(request, context, **kwargs):
            yield event
