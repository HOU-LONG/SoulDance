"""单品分析工具——命中库内商品走 LLM 流式分析；未命中也走 LLM 通用知识回答，不再拒答。"""
from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class ProductAnalysisTool:
    name = "product_analysis"
    description = "对单一命名商品做参数/性价比/特点分析"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        user_id = kwargs.get("user_id", "anonymous")
        from ..reference_resolver import resolve_named_product
        from ..agent import _text_delta_events, _assistant_state, _focus_product_explanation, _stream_with_first_chunk_timeout
        product = resolve_named_product(request.message, self._agent.product_map, context)
        message_id = _message_id()

        if product is None:
            # 未命中库存——不再拒答，改用 LLM 通用知识回答 + 诚实标注本店不在售
            yield _assistant_state(
                message_id, "chatting", "正在用通用知识回答",
                intent="product_analysis", retrieval_mode="no_retrieval",
            )
            got_any_chunk = False
            try:
                stream = self._agent.llm_client.stream_chitchat_response(
                    request.message, "product_analysis_unknown", context
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
                fallback = (
                    "这款商品我手里没有完整的本店参数。"
                    "基于公开信息我可以大致说说它的定位和卖点，但具体价格和是否在售请以实际为准。"
                    "你想了解哪方面？参数、价格区间，还是和其它型号怎么选？"
                )
                for event in _text_delta_events(message_id, fallback):
                    yield event
            yield {"type": "done", "message_id": message_id}
            return

        # 命中商品——用 LLM 流式生成分析
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
            fallback = _focus_product_explanation(product, context)
            for event in _text_delta_events(message_id, fallback):
                yield event
        yield {"type": "done", "message_id": message_id}


def _message_id() -> str:
    import uuid
    return "assistant_" + uuid.uuid4().hex[:10]
