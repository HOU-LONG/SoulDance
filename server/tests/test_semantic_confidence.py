from __future__ import annotations

import pytest

from backend.app.models import ChatRequest, SemanticFrame, SessionContext
from backend.app.semantic_layer import SemanticParser


class _MockLLMClient:
    def __init__(self, confidence: float = 1.0):
        self.confidence = confidence

    async def parse_semantic_frame(self, message, context, request_type="user_message"):
        return f'{{"intent": "recommend_product", "confidence": {self.confidence}}}'


@pytest.mark.asyncio
async def test_low_confidence_triggers_clarification():
    parser = SemanticParser(llm_client=_MockLLMClient(confidence=0.3))
    request = ChatRequest(type="user_message", session_id="s1", message="我想买点东西")
    context = SessionContext(session_id="s1")
    frame = await parser.parse(request, context)
    assert frame.intent == "clarification"
    assert frame.clarification_question is not None


@pytest.mark.asyncio
async def test_high_confidence_keeps_intent():
    parser = SemanticParser(llm_client=_MockLLMClient(confidence=0.9))
    request = ChatRequest(type="user_message", session_id="s1", message="推荐防晒霜")
    context = SessionContext(session_id="s1")
    frame = await parser.parse(request, context)
    assert frame.intent == "recommend_product"


@pytest.mark.asyncio
async def test_boundary_confidence_exactly_0_6():
    parser = SemanticParser(llm_client=_MockLLMClient(confidence=0.6))
    request = ChatRequest(type="user_message", session_id="s1", message="推荐手机")
    context = SessionContext(session_id="s1")
    frame = await parser.parse(request, context)
    # 0.6 is not < 0.6, so should NOT trigger clarification
    assert frame.intent == "recommend_product"


@pytest.mark.asyncio
async def test_just_below_threshold_confidence():
    parser = SemanticParser(llm_client=_MockLLMClient(confidence=0.59))
    request = ChatRequest(type="user_message", session_id="s1", message="随便看看")
    context = SessionContext(session_id="s1")
    frame = await parser.parse(request, context)
    assert frame.intent == "clarification"


@pytest.mark.asyncio
async def test_no_llm_client_falls_back_to_rule_based():
    parser = SemanticParser(llm_client=None)
    request = ChatRequest(type="user_message", session_id="s1", message="推荐防晒霜")
    context = SessionContext(session_id="s1")
    frame = await parser.parse(request, context)
    assert frame.intent == "recommend_product"


@pytest.mark.asyncio
async def test_specific_i_want_product_name_is_shopping_request():
    parser = SemanticParser(llm_client=None)
    request = ChatRequest(type="user_message", session_id="s1", message="\u6211\u8981\u4e00\u74f6\u4e1c\u9e4f\u7279\u996e")
    context = SessionContext(session_id="s1")
    frame = await parser.parse(request, context)
    assert frame.intent == "recommend_product"
