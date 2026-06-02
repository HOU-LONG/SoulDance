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

SEMANTIC_SYSTEM_PROMPT = """你是电商导购后端的 IntentCompiler。只输出 JSON，不要 Markdown。
你的任务是把用户自然语言解析成 ShoppingIntentIR，不直接执行商品选择、检索排序或购物车操作。
intent 只能是 recommend_product, product_followup, compare_products, cart_operation, scenario_bundle, clarification, small_talk, unclear_input。
纯寒暄、感谢、询问助手身份等非购物消息输出 small_talk；如果同一句里包含明确购物需求，购物意图优先。
乱码、自我陈述、情绪表达、没有购物动作也没有明确商品类目的输入输出 unclear_input，不要联想商品。
示例：`halo`、`hallo`、`hello`、`hi`、`你好`、`在吗`、`谢谢` -> small_talk。
示例：`sdfghjhgfdg`、`我是猪`、`哈哈哈`、`我今天很难过` -> unclear_input。
示例：`halo，推荐防晒霜`、`你好，预算100以内推荐精华` -> recommend_product。
示例：`我想买猪肉松`、`推荐毛巾` -> recommend_product。
followup 偏好变化放在 constraint_edits：add 表示新增或覆盖约束，remove 表示用户明确取消旧约束，relax 表示放宽某类约束。
自然语言购物车放在 cart_operation，target.reference 可用 focus_product, last_recommendation, last_recommendations, recent_cart_item。
target.selection_strategy 可用 primary, cheapest, most_expensive, index。
query_intent 只能表达类目、子类目、软偏好和 query_terms，不能生成最终 retrieval_query。
不要编造 product_id；只有用户明确提供 product_id 时才填写。"""

RESPONSE_SYSTEM_PROMPT = """你是低压力电商导购助手。只能基于后端给你的 evidence payload 回答。
回复结构：一句话理解用户意图；说明已经处理的硬约束；主推一个商品；给 2-3 个证据；给低成本修正入口。
不要编造商品属性，不要承诺疗效，不要改变商品顺序、价格、购物车状态或事件类型。"""

SELECTION_SYSTEM_PROMPT = """你是电商导购后端的商品选择器。只输出 JSON，不要 Markdown。
你只能从 candidates 中选择 product_id，不能编造商品，不能选择不满足用户硬约束的商品。
根据用户需求、后端排序分数、tier、reason 和 evidence 决定是否推荐以及推荐几个。
高相关最多选 4 个；中相关选 2-3 个；低相关选 1 个或不推荐。
输出字段：should_recommend, need_clarification, selected_product_ids, reasons。
reasons 是 product_id 到一句简短中文理由的对象。"""

CHITCHAT_SYSTEM_PROMPT = """你是一个温和、自然的电商导购助手。
用户当前没有形成可检索的购物需求。请简短回应，不要推荐具体商品，不要联想商品。
回复要有人味，最多两句话，引导用户可以补充想买什么、预算、偏好或排除条件。
不要评价用户，不要调侃用户，不要使用“别闹”这类可能冒犯的表达。"""


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

    async def parse_semantic_frame(
        self,
        message: str,
        context: SessionContext | None = None,
        request_type: str = "user_message",
    ) -> str:
        context_payload: dict[str, Any] = {}
        if context:
            context_payload = {
                "last_plan": context.last_plan.model_dump(mode="json") if context.last_plan else None,
                "focus_product_id": context.focus_product_id,
                "last_product_ids": context.last_product_ids,
                "last_recommendations": context.last_recommendations,
                "recent_cart_product_id": context.recent_cart_product_id,
                "global_profile": context.global_profile,
            }
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SEMANTIC_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": message,
                            "request_type": request_type,
                            "session_context": context_payload,
                        },
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
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": user_message,
                            "evidence_payload": _response_evidence_payload(plan, ranked_products, focus_product),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content or ""

    async def select_products(
        self,
        user_message: str,
        plan: RetrievalPlan,
        candidates: list[RankedProduct],
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SELECTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": user_message,
                            "plan": plan.model_dump(mode="json"),
                            "candidates": _selection_candidates_payload(candidates),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or "{}"

    async def stream_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
    ):
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": user_message,
                            "evidence_payload": _response_evidence_payload(plan, ranked_products, focus_product),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.3,
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
            if text:
                yield text

    async def stream_chitchat_response(
        self,
        user_message: str,
        intent: str,
        context: SessionContext | None = None,
    ):
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": CHITCHAT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"message": user_message, "intent": intent},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.4,
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
            if text:
                yield text


class FakeLLMClient:
    async def plan(self, message: str, context: SessionContext | None = None) -> str:
        return "{}"

    async def parse_semantic_frame(
        self,
        message: str,
        context: SessionContext | None = None,
        request_type: str = "user_message",
    ) -> str:
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

    async def select_products(
        self,
        user_message: str,
        plan: RetrievalPlan,
        candidates: list[RankedProduct],
    ) -> str:
        selected = _fallback_selected_products(candidates)
        return json.dumps(
            {
                "should_recommend": bool(selected),
                "need_clarification": False,
                "selected_product_ids": [item.product.product_id for item in selected],
                "reasons": {item.product.product_id: item.reason for item in selected},
            },
            ensure_ascii=False,
        )

    async def stream_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
    ):
        text = await self.generate_response(user_message, plan, ranked_products, focus_product)
        for index in range(0, len(text), 12):
            yield text[index : index + 12]

    async def stream_chitchat_response(
        self,
        user_message: str,
        intent: str,
        context: SessionContext | None = None,
    ):
        if intent == "unclear_input":
            text = "我还没太抓到你的购物需求。你可以随便说个想买的东西、预算，或者不想要什么，我再帮你筛。"
        else:
            text = "我在，可以陪你慢慢挑。你告诉我购物需求、预算多少，或者有什么偏好就行。"
        for index in range(0, len(text), 12):
            yield text[index : index + 12]


def _response_evidence_payload(
    plan: RetrievalPlan,
    ranked_products: list[RankedProduct],
    focus_product: Product | None = None,
) -> dict[str, Any]:
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
    constraints = plan.hard_constraints
    return {
        "allowed_products": products,
        "selected_primary": products[0]["product_id"] if products else None,
        "hard_constraints_applied": {
            "category": constraints.category,
            "sub_category": constraints.sub_category,
            "price_max": constraints.price_max,
            "exclude_terms": constraints.exclude_terms,
            "exclude_brands": constraints.exclude_brands,
            "exclude_brand_regions": constraints.exclude_brand_regions,
        },
        "focus_product": focus_product.model_dump(mode="json") if focus_product else None,
        "forbidden_claims": ["疗效承诺", "未给出的商品属性", "后端没有返回的 product_id"],
    }


def _selection_candidates_payload(candidates: list[RankedProduct]) -> list[dict[str, Any]]:
    return [
        {
            "product_id": item.product.product_id,
            "title": item.product.title,
            "brand": item.product.brand,
            "category": item.product.category,
            "sub_category": item.product.sub_category,
            "price": item.product.price,
            "score": item.score,
            "tier": item.tier,
            "reason": item.reason,
            "evidence": item.evidence[:3],
        }
        for item in candidates
    ]


def _fallback_selected_products(candidates: list[RankedProduct]) -> list[RankedProduct]:
    if not candidates:
        return []
    best_tier = min(item.tier for item in candidates)
    same_tier = [item for item in candidates if item.tier == best_tier]
    if best_tier == 1:
        limit = 4
    elif best_tier == 2:
        limit = 3
    else:
        limit = 1
    return same_tier[:limit]
