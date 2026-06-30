"""单品分析工具：模糊匹配商品后用 LLM 流式分析；未命中则给出通用知识 + 候选提示。

匹配策略：
- 优先用 ProductMatcher（共享 retriever 的 BM25/dense 索引）模糊匹配用户原话
- 上下文焦点（"这个""刚才那个"）仍由 ReferenceResolver 兜底
- 未命中 → product_analysis_unknown LLM prompt，附带库内相近候选，让 LLM 自然回答 + 引导
"""
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
        from ..agent import _text_delta_events, _assistant_state, _focus_product_explanation, _stream_with_first_chunk_timeout

        product = self._resolve_target_product(request, context)
        message_id = _message_id()

        if product is None:
            # 未命中库内任何商品：仍走 LLM 用通用知识回答，并把库内相近候选透传作为提示
            yield _assistant_state(
                message_id, "chatting", "正在用通用知识回答",
                intent="product_analysis", retrieval_mode="no_retrieval",
            )
            candidates = self._find_candidates(request.message)
            got_any_chunk = False
            try:
                stream = self._agent.llm_client.stream_chitchat_response(
                    request.message, "product_analysis_unknown", context,
                )
                async for chunk in _stream_with_first_chunk_timeout(
                    stream, first_chunk_timeout=12.0, chunk_timeout=12.0,
                ):
                    if chunk:
                        got_any_chunk = True
                        yield {"type": "text_delta", "message_id": message_id, "text": chunk}
            except Exception:
                pass
            if not got_any_chunk:
                # 拼一段"本店暂无 + 候选"的兜底文本，保留模糊匹配带来的"接近商品"作为线索
                fallback_parts = [
                    "这款商品我手里没有完整的本店参数。基于公开信息我可以大致说说它的定位和卖点，"
                    "具体价格和是否在售请以实际为准。",
                ]
                if candidates:
                    nearby_names = "、".join(c.title.split()[0] if " " in c.title else c.title[:18] for c in candidates[:3])
                    fallback_parts.append(f"本店有几款相近的可以参考：{nearby_names}。")
                for event in _text_delta_events(message_id, "\n\n".join(fallback_parts)):
                    yield event
            yield {"type": "done", "message_id": message_id}
            return

        # 命中库内商品：LLM 流式分析
        yield _assistant_state(message_id, "explaining", "正在分析商品", intent="product_analysis", retrieval_mode="no_retrieval")

        # 注入焦点商品供 LLM 引用真实数据
        context.focus_product_id = product.product_id
        context.last_recommendations.append({
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "price": product.price,
            "sub_category": product.sub_category,
        })

        # ★ 关键：把商品事实注入到 LLM prompt 中
        enriched_message = (
            f"[本店匹配到的商品]\n"
            f"商品ID: {product.product_id}\n"
            f"名称: {product.title}\n"
            f"品牌: {product.brand}\n"
            f"价格: ¥{product.price:.0f}\n"
            f"类目: {product.category} / {product.sub_category}\n"
            f"卖点: {product.marketing_description or '暂无'}\n\n"
            f"用户问题: {request.message}\n\n"
            f"请基于以上真实商品数据进行分析，从性价比、适用场景、优缺点角度给出简短分析（2-4句话）。"
            f"必须引用商品的实际名称、价格和规格。绝对禁止说该商品不存在。"
        )

        got_any_chunk = False
        try:
            stream = self._agent.llm_client.stream_chitchat_response(
                enriched_message, "product_analysis", context
            )
            async for chunk in _stream_with_first_chunk_timeout(
                stream, first_chunk_timeout=12.0, chunk_timeout=12.0,
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

    # ----- 内部解析逻辑 -----

    def _resolve_target_product(self, request: ChatRequest, context: SessionContext):
        """决定单品分析的目标商品：
        1. 用户原话先走 ProductMatcher 模糊匹配（命中 → 用 best）
        2. 模糊但 top-1 候选 raw score > 0 → 降级使用 top-1
        3. 有焦点商品上下文 → 用 focus_product
        4. 都没有 → None（走 unknown 流）
        """
        import logging
        logger = logging.getLogger(__name__)
        match = self._agent.product_matcher.match(request.message)
        logger.warning(
            f"[product_analysis] query='{request.message[:60]}' "
            f"best={match.best.title if match.best else 'None'} "
            f"confidence={match.confidence:.3f} "
            f"candidates={len(match.candidates)}"
        )
        if match.best is not None:
            return match.best

        # 降级：confidence 低但 top-1 候选存在 → 直接使用 top-1
        if match.candidates:
            top = match.candidates[0]
            logger.warning(f"[product_analysis] fallback to top candidate: {top.title[:50]}")
            return top

        # 模糊不确定时回退到 context focus（"这个/刚才那个"语义）
        focus_id = context.state.active_focus.product_id or context.focus_product_id
        if focus_id and focus_id in self._agent.product_map:
            import re
            if re.search(r"(这个|这款|那个|刚才|刚刚|它|前面|继续|还是)", request.message or ""):
                return self._agent.product_map[focus_id]
        return None

    def _find_candidates(self, message: str):
        """模糊匹配虽未命中明确目标，但 candidates 通常有相近商品，作为"本店相近款"提示。"""
        match = self._agent.product_matcher.match(message or "", top_k=3)
        return match.candidates


def _message_id() -> str:
    import uuid
    return "assistant_" + uuid.uuid4().hex[:10]
