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
        user_id = kwargs.get("user_id", "anonymous")
        if request.type == "cart_action":
            cart_event = self._agent.execute_cart_action(
                user_id,
                request.session_id,
                request.action or "add_to_cart",
                request.product_id,
                request.quantity,
                cart,
            )
            yield {"type": "cart_update", **cart_event}
            yield {"type": "done"}
            return
        cart_event = await self._agent.try_handle_cart_message(
            user_id,
            request,
            cart,
            compiled_ir=kwargs.get("compiled_ir"),
        )
        if cart_event is not None:
            yield {"type": "cart_update", **cart_event}
            yield {"type": "done"}
