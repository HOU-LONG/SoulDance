from __future__ import annotations

import pytest

from backend.app.agent import ShopGuideAgent
from backend.app.cart import CartService
from backend.app.data_loader import load_products
from backend.app.models import ChatRequest
from backend.app.tools.registry import ToolRegistry


class RecordingTool:
    name = "target_intent"
    description = "test target"

    def __init__(self):
        self.calls = []

    async def execute(self, request, context, **kwargs):
        self.calls.append((request, context, kwargs))
        yield {"type": "ok", "value": kwargs["value"]}


class FallbackTool:
    name = "small_talk"
    description = "fallback"

    async def execute(self, request, context, **kwargs):
        yield {"type": "fallback", "intent": kwargs.get("intent")}


@pytest.mark.asyncio
async def test_tool_registry_dispatches_registered_intent():
    registry = ToolRegistry()
    tool = RecordingTool()
    registry.register(tool)

    events = [
        event
        async for event in registry.execute(
            "target_intent",
            "request",
            "context",
            value=42,
        )
    ]

    assert events == [{"type": "ok", "value": 42}]
    assert tool.calls == [
        ("request", "context", {"value": 42, "intent": "target_intent"})
    ]


@pytest.mark.asyncio
async def test_tool_registry_falls_back_to_small_talk_with_original_intent():
    registry = ToolRegistry()
    registry.register(FallbackTool())

    events = [
        event
        async for event in registry.execute(
            "unsupported_intent",
            "request",
            "context",
        )
    ]

    assert events == [{"type": "fallback", "intent": "unsupported_intent"}]


def test_shopguide_agent_registers_small_talk_tool():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products)

    assert agent.tool_registry.get("small_talk") is not None


@pytest.mark.asyncio
async def test_cart_tool_handles_explicit_cart_action_without_message_text():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products)
    cart = CartService(products)
    product_id = products[0].product_id
    request = ChatRequest(
        type="cart_action",
        session_id="tool_cart_explicit",
        action="add_to_cart",
        product_id=product_id,
        quantity=2,
    )

    events = [
        event
        async for event in agent.tool_registry.execute(
            "cart_operation",
            request,
            agent.sessions.get(request.session_id),
            cart_service=cart,
        )
    ]

    assert [event["type"] for event in events] == ["cart_update", "done"]
    assert events[0]["product_id"] == product_id
    assert events[0]["cart"]["items"][0]["product_id"] == product_id
    assert events[0]["cart"]["items"][0]["quantity"] == 2
