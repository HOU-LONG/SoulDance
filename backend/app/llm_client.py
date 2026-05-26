from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from .config import Settings
from .models import Product, RankedProduct, RetrievalPlan, SessionContext


PLANNER_SYSTEM_PROMPT = """你是电商导购后端的检索规划器。只输出 JSON，不要 Markdown。
intent 只能是 recommend_product, product_followup, compare_products, cart_action, scenario_bundle, clarification。
字段必须包含 intent, retrieval_mode, category, hard_constraints, soft_preferences, retrieval_query, need_clarification。
hard_constraints 可包含 category, sub_category, price_max, exclude_terms, exclude_brands, exclude_brand_regions, in_stock_only。
否定约束例如不要、不含、排除必须放进 hard_constraints，不能变成软偏好。
商品最终选择由后端完成，你只负责理解用户需求。"""

RESPONSE_SYSTEM_PROMPT = """你是低压力电商导购助手。只能基于后端给你的真实商品和证据回答。
回复结构：一句话理解用户意图；说明已经处理的硬约束；主推一个商品；给 2-3 个证据；给低成本修正入口。
不要编造商品属性，不要承诺疗效，不要油腻。"""


class DoubaoLLMClient:
    def __init__(self, settings: Settings):
        if not settings.ark_api_key:
            raise ValueError("ARK_API_KEY is required for DoubaoLLMClient")
        self.model = settings.ark_model
        self.client = AsyncOpenAI(
            api_key=settings.ark_api_key,
            base_url=settings.ark_base_url,
            timeout=settings.request_timeout_seconds,
        )

    async def plan(self, message: str, context: SessionContext | None = None) -> str:
        context_payload: dict[str, Any] = {}
        if context and context.last_plan:
            context_payload = {
                "last_plan": context.last_plan.model_dump(mode="json"),
                "focus_product_id": context.focus_product_id,
            }
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"message": message, "session_context": context_payload},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or "{}"

    async def generate_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
    ) -> str:
        products = [
            {
                "product_id": item.product.product_id,
                "title": item.product.title,
                "brand": item.product.brand,
                "category": item.product.category,
                "sub_category": item.product.sub_category,
                "price": item.product.price,
                "reason": item.reason,
                "evidence": item.evidence,
            }
            for item in ranked_products[:3]
        ]
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": user_message,
                            "retrieval_plan": plan.model_dump(mode="json"),
                            "focus_product": focus_product.model_dump(mode="json") if focus_product else None,
                            "candidate_products": products,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content or ""


class FakeLLMClient:
    async def plan(self, message: str, context: SessionContext | None = None) -> str:
        return "{}"

    async def generate_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
    ) -> str:
        if not ranked_products:
            return "我按你的条件筛了一遍，暂时没有找到完全合适的商品。可以放宽预算或减少一个排除条件再试。"
        primary = ranked_products[0]
        constraints = plan.hard_constraints
        handled: list[str] = []
        if constraints.price_max is not None:
            handled.append(f"预算 {constraints.price_max:.0f} 元以内")
        if constraints.exclude_terms:
            handled.append("排除" + "、".join(constraints.exclude_terms))
        if constraints.exclude_brand_regions:
            handled.append("排除" + "、".join(constraints.exclude_brand_regions) + "品牌")
        handled_text = "，".join(handled) if handled else "你的核心需求"
        return (
            f"我理解你想要的是更省心的商品选择，所以先按「{handled_text}」筛选。"
            f"主推「{primary.product.title}」，价格 {primary.product.price:.0f} 元。"
            f"{primary.reason} 如果你想更便宜、更清爽或换个品牌，我可以继续帮你换。"
        )
