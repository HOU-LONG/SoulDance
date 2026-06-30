"""Tests for rule_semantic_frame() — the rule-based tool routing fallback."""
from __future__ import annotations

import pytest

from backend.app.models import ChatRequest
from backend.app.semantic_layer import rule_semantic_frame


@pytest.mark.asyncio
async def test_rule_based_recommends_for_shopping_request():
    request = ChatRequest(type="user_message", session_id="s1", message="推荐防晒霜")
    frame = rule_semantic_frame(request)
    assert frame.tool == "recommend_product"


@pytest.mark.asyncio
async def test_rule_based_detects_shopping_request():
    request = ChatRequest(type="user_message", session_id="s1", message="我要一瓶东鹏特饮")
    frame = rule_semantic_frame(request)
    assert frame.tool == "recommend_product"


@pytest.mark.asyncio
async def test_rule_based_cart_operation():
    request = ChatRequest(type="user_message", session_id="s1", message="加入购物车")
    frame = rule_semantic_frame(request)
    assert frame.tool == "cart_operation"


@pytest.mark.asyncio
async def test_rule_based_product_followup():
    request = ChatRequest(type="product_followup", session_id="s1", message="换一个")
    frame = rule_semantic_frame(request)
    assert frame.tool == "product_followup"


@pytest.mark.asyncio
async def test_rule_based_small_talk():
    request = ChatRequest(type="user_message", session_id="s1", message="你好")
    frame = rule_semantic_frame(request)
    assert frame.tool == "small_talk"


@pytest.mark.asyncio
async def test_rule_based_unclear_input():
    request = ChatRequest(type="user_message", session_id="s1", message="asdf")
    frame = rule_semantic_frame(request)
    assert frame.tool == "unclear_input"
