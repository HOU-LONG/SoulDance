from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class ProductAnalysisTool:
    name = "product_analysis"
    description = "对单一命名商品做性价比/特点分析"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        user_id = kwargs.get("user_id", "anonymous")
        from ..reference_resolver import resolve_named_product
        from ..agent import _text_delta_events, _assistant_state, _focus_product_explanation
        product = resolve_named_product(request.message, self._agent.product_map, context)
        message_id = _message_id()
        if product is None:
            text = (
                "当前商品库没有找到你提到的这款商品，所以我没有办法给出基于真实库存的分析。"
                "如果你告诉我预算、用途和偏好，我可以从现有商品里帮你挑一款性价比合适的。"
            )
            yield _assistant_state(message_id, "chatting", "商品库未命中", intent="product_analysis", retrieval_mode="no_retrieval")
            for event in _text_delta_events(message_id, text):
                yield event
            yield {"type": "done", "message_id": message_id}
            return

        yield _assistant_state(message_id, "explaining", "正在分析商品", intent="product_analysis", retrieval_mode="no_retrieval")
        text = _focus_product_explanation(product, context)
        for event in _text_delta_events(message_id, text):
            yield event
        yield {"type": "done", "message_id": message_id}


def _message_id() -> str:
    import uuid
    return "assistant_" + uuid.uuid4().hex[:10]
