from __future__ import annotations

from typing import Any, Callable


class GatewayRouter:
    """基于意图的可扩展网关路由器。"""

    def __init__(self):
        self._handlers: dict[str, Callable[..., list[dict]]] = {}
        self._fallback_intent = "fallback"

    def register(self, intent: str, handler: Callable[..., list[dict]]) -> None:
        """注册一个意图处理器。"""
        self._handlers[intent] = handler

    def route(self, intent: str, request: Any) -> list[dict]:
        """根据意图路由请求到对应处理器，未注册则使用 fallback。"""
        handler = self._handlers.get(intent) or self._handlers.get(self._fallback_intent)
        if handler is None:
            return [{"type": "error", "message": f"No handler for intent '{intent}' and no fallback registered"}]
        return handler(request)
