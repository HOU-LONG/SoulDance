from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class CartTool:
    name = "cart_operation"
    description = "购物车操作"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        cart = kwargs.get("cart_service")
        if cart is None:
            yield {"type": "error", "message": "cart service not available"}
            return
        cart_event = await self._agent.try_handle_cart_message(request, cart)
        if cart_event is not None:
            yield {"type": "cart_update", **cart_event}
            yield {"type": "done"}
