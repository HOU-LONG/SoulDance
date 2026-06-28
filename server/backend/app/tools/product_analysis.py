"""单品分析工具——命中库内商品用 LLM 流式生成分析，未命中给出引导文本。

Task 11: 将命中商品的分析从硬编码模板改为 LLM 流式生成。
模板 _focus_product_explanation 保留为 LLM 流失败时的 fallback。
"""
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
        from ..agent import _text_delta_events, _assistant_state, _focus_product_explanation, _stream_with_first_chunk_timeout
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

        # Task 11: 命中商品——用 LLM 流式生成分析，替代硬编码 _focus_product_explanation 模板
        yield _assistant_state(message_id, "explaining", "正在分析商品", intent="product_analysis", retrieval_mode="no_retrieval")

        # 临时注入焦点商品信息供 LLM 使用
        context.focus_product_id = product.product_id
        context.last_recommendations.append({
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "price": product.price,
            "sub_category": product.sub_category,
        })

        got_any_chunk = False
        try:
            stream = self._agent.llm_client.stream_chitchat_response(
                request.message, "product_analysis", context
            )
            async for chunk in _stream_with_first_chunk_timeout(
                stream,
                first_chunk_timeout=12.0,
                chunk_timeout=12.0,
            ):
                if chunk:
                    got_any_chunk = True
                    yield {"type": "text_delta", "message_id": message_id, "text": chunk}
        except Exception:
            pass

        if not got_any_chunk:
            # 流无输出 → fallback 到旧模板分析
            fallback = _focus_product_explanation(product, context)
            for event in _text_delta_events(message_id, fallback):
                yield event
        yield {"type": "done", "message_id": message_id}


def _message_id() -> str:
    import uuid
    return "assistant_" + uuid.uuid4().hex[:10]
