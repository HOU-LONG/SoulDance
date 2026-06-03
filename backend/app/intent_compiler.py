from __future__ import annotations

from typing import Any

from .models import ChatRequest, SessionContext, ShoppingIntentIR
from .planner_agent import _detect_category, _detect_intent
from .semantic_layer import SemanticParser, rule_semantic_frame


class IntentCompiler:
    """Single semantic parse boundary for shopping intent IR."""

    def __init__(self, llm_client: Any | None = None, parser: SemanticParser | None = None):
        self.parser = parser or SemanticParser(llm_client)

    async def compile(self, request: ChatRequest, context: SessionContext) -> ShoppingIntentIR:
        frame = await self.parser.parse(request, context)
        guarded = _normalize_intent(frame, request)
        context.state.trace.last_ir = guarded.model_dump(mode="json")
        return guarded


def _normalize_intent(frame: ShoppingIntentIR, request: ChatRequest) -> ShoppingIntentIR:
    intent = _canonical_intent(frame.intent)
    rule_intent = _canonical_intent(_detect_intent(request.message or "", request))
    if request.type == "product_followup":
        intent = "product_followup"
    elif intent == "product_followup" and rule_intent == "recommend_product" and _detect_category(request.message or ""):
        intent = "recommend_product"
    elif intent == "compare_products" and rule_intent == "recommend_product":
        intent = "recommend_product"
    elif intent == "recommend_product" and rule_intent in {
        "compare_products",
        "scenario_bundle",
        "cart_operation",
        "clarification",
        "small_talk",
        "unclear_input",
    }:
        intent = rule_intent
    elif intent == "cart_operation" and frame.cart_operation is None:
        guarded = rule_semantic_frame(request)
        frame.cart_operation = guarded.cart_operation
    elif intent == "cart_operation" and frame.cart_operation is not None:
        frame.intent = intent
        return frame
    frame.intent = intent
    return frame


def _canonical_intent(intent: str) -> str:
    aliases = {
        "recommend": "recommend_product",
        "followup": "product_followup",
        "cart": "cart_operation",
        "cart_action": "cart_operation",
        "compare": "compare_products",
        "bundle": "scenario_bundle",
        "clarify": "clarification",
        "smalltalk": "small_talk",
        "small_talk": "small_talk",
        "unclear": "unclear_input",
        "unclear_input": "unclear_input",
        "invalid_input": "unclear_input",
        "non_shopping": "unclear_input",
        "chitchat": "small_talk",
    }
    return aliases.get(intent, intent)
