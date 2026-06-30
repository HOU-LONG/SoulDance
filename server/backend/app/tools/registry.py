from __future__ import annotations

import asyncio
import logging

from .base import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, intent: str) -> Tool | None:
        return self._tools.get(intent)

    async def execute(self, intent: str, request, context, **kwargs):
        kwargs.setdefault("intent", intent)
        tool = self.get(intent)
        if tool is None:
            tool = self.get("small_talk")
        if tool is None:
            yield {"type": "error", "message": f"no tool for intent: {intent}"}
            return

        try:
            async for event in tool.execute(request, context, **kwargs):
                yield event
        except asyncio.TimeoutError:
            logger.warning(f"[tool_registry] timeout executing {intent}")
            yield {"type": "error", "error_type": "tool_timeout", "tool": intent,
                   "message": "执行超时，请稍后重试或换个方式描述你的需求。"}
        except ValueError as exc:
            logger.warning(f"[tool_registry] value error in {intent}: {exc}")
            yield {"type": "error", "error_type": "tool_value_error", "tool": intent,
                   "message": "我暂时无法处理这个请求，请试试换个说法。"}
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.warning(f"[tool_registry] connection error in {intent}: {exc}")
            yield {"type": "error", "error_type": "tool_connection_error", "tool": intent,
                   "message": "服务暂时连接不上，请稍后重试。"}
        except Exception as exc:
            logger.error(f"[tool_registry] unhandled error in {intent}: {exc}", exc_info=True)
            yield {"type": "error", "error_type": "tool_internal_error", "tool": intent,
                   "message": "出了点问题，请重新描述你的需求。"}
