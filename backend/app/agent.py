from __future__ import annotations

from collections.abc import AsyncIterator
import re
import uuid

from .cart import CartService
from .embedding_retriever import BM25OnlyRetriever
from .llm_client import FakeLLMClient
from .models import ChatRequest, HardConstraints, Product, ProductCard, RankedProduct, RetrievalPlan, SessionContext
from .planner_agent import PlannerAgent
from .ranker import rank_products
from .session_store import SessionStore
from .tts_adapter import TTSAdapter


class ShopGuideAgent:
    def __init__(
        self,
        products: list[Product],
        llm_client=None,
        retriever=None,
        session_store: SessionStore | None = None,
        tts_adapter: TTSAdapter | None = None,
    ):
        self.products = products
        self.product_map = {product.product_id: product for product in products}
        self.llm_client = llm_client or FakeLLMClient()
        self.retriever = retriever or BM25OnlyRetriever(products)
        self.sessions = session_store or SessionStore()
        self.planner = PlannerAgent(self.llm_client)
        self.tts = tts_adapter or TTSAdapter()

    async def plan(self, request: ChatRequest) -> RetrievalPlan:
        context = self.sessions.get(request.session_id)
        return await self.planner.create_plan(request, context)

    def retrieve_and_rank(self, plan: RetrievalPlan) -> list[RankedProduct]:
        retrieved = self.retriever.search(plan.retrieval_query, top_k=30)
        if retrieved:
            candidates = [product for product, _ in retrieved]
            scores = {product.product_id: score for product, score in retrieved}
        else:
            candidates = self.products
            scores = {}
        ranked = rank_products(candidates, plan, scores, limit=3)
        if not ranked and candidates != self.products:
            ranked = rank_products(self.products, plan, {}, limit=3)
        return ranked

    async def handle_message(self, request: ChatRequest) -> list[dict]:
        return [event async for event in self.stream_message(request)]

    async def stream_message(self, request: ChatRequest) -> AsyncIterator[dict]:
        if request.type == "product_followup":
            async for event in self._stream_followup(request):
                yield event
            return
        plan = await self.plan(request)
        if plan.need_clarification or plan.intent == "clarification":
            for event in self._build_clarification_events(plan):
                yield event
            return
        if plan.intent == "compare_products":
            for event in self._build_comparison_events(request):
                yield event
            return
        if plan.intent == "scenario_bundle":
            for event in self._build_bundle_events(request, plan):
                yield event
            return
        ranked = self.retrieve_and_rank(plan)
        context = self.sessions.get(request.session_id)
        self._remember_recommendations(context, plan, ranked)
        async for event in self._stream_recommendation_events(request, plan, ranked):
            yield event

    async def _handle_followup(self, request: ChatRequest) -> list[dict]:
        return [event async for event in self._stream_followup(request)]

    async def _stream_followup(self, request: ChatRequest) -> AsyncIterator[dict]:
        context = self.sessions.get(request.session_id)
        if request.focus_product_id:
            context.focus_product_id = request.focus_product_id
        context.focus_history.append(request.message)
        plan = await self.plan(request)
        focus_product = self.product_map.get(request.focus_product_id or context.focus_product_id or "")
        if focus_product and _wants_different_brand(request.message):
            plan.hard_constraints.exclude_brands = _dedupe(plan.hard_constraints.exclude_brands + [focus_product.brand])
            context.negative_feedback.append(f"不要品牌:{focus_product.brand}")
        ranked = self.retrieve_and_rank(plan)
        self._remember_recommendations(context, plan, ranked)
        message_id = _message_id()
        intro = _followup_intro(plan)
        yield _assistant_state(message_id, "retrieving", "正在按当前商品上下文重新筛选")
        for event in _text_delta_events(message_id, intro):
            yield event
        if ranked:
            replacement = _product_card(ranked[0])
            yield {
                "type": "replacement_product",
                "message_id": message_id,
                "focus_product_id": request.focus_product_id,
                "reason": ranked[0].reason,
                "product": replacement.model_dump(mode="json"),
            }
            text = await self._safe_generate_text(request, plan, ranked, focus_product)
            for event in _text_delta_events(message_id, text):
                yield event
            yield _quick_actions_event(message_id, plan, ranked)
        else:
            text = _no_match_text(plan)
            for event in _text_delta_events(message_id, text):
                yield event
            yield _filter_recovery_event(message_id, plan)
        yield {"type": "focus_done", "message_id": message_id}
        for event in await self.tts.synthesize_events(intro + text, request.tts_enabled):
            yield event

    async def _build_recommendation_events(
        self, request: ChatRequest, plan: RetrievalPlan, ranked: list[RankedProduct]
    ) -> list[dict]:
        return [event async for event in self._stream_recommendation_events(request, plan, ranked)]

    async def _stream_recommendation_events(
        self, request: ChatRequest, plan: RetrievalPlan, ranked: list[RankedProduct]
    ) -> AsyncIterator[dict]:
        message_id = _message_id()
        intro = _understanding_text(plan)
        yield _assistant_state(message_id, "retrieving", "正在理解需求并筛选商品")
        for event in _text_delta_events(message_id, intro):
            yield event
        if not ranked:
            text = _no_match_text(plan)
            for event in _text_delta_events(message_id, text):
                yield event
            yield _filter_recovery_event(message_id, plan)
            yield _quick_actions_event(message_id, plan, ranked)
            yield {"type": "done", "message_id": message_id}
            for event in await self.tts.synthesize_events(intro + text, request.tts_enabled):
                yield event
            return
        yield {"type": "products_start", "message_id": message_id}
        for index, item in enumerate(ranked):
            yield {
                "type": "product_item",
                "message_id": message_id,
                "index": index,
                "role": "primary" if index == 0 else "alternative",
                "product": _product_card(item).model_dump(mode="json"),
            }
        yield {"type": "products_done", "message_id": message_id}
        text = await self._safe_generate_text(request, plan, ranked, None)
        for event in _text_delta_events(message_id, text):
            yield event
        yield _quick_actions_event(message_id, plan, ranked)
        yield {"type": "done", "message_id": message_id}
        for event in await self.tts.synthesize_events(intro + text, request.tts_enabled):
            yield event

    async def _safe_generate_text(
        self,
        request: ChatRequest,
        plan: RetrievalPlan,
        ranked: list[RankedProduct],
        focus_product: Product | None,
    ) -> str:
        if not ranked:
            return _no_match_text(plan)
        try:
            text = await self.llm_client.generate_response(request.message, plan, ranked, focus_product)
            if text:
                return text
        except Exception:
            pass
        return await FakeLLMClient().generate_response(request.message, plan, ranked, focus_product)

    def _build_clarification_events(self, plan: RetrievalPlan) -> list[dict]:
        message_id = _message_id()
        question = plan.clarification_question or "我需要再确认一个关键偏好，才能更稳地推荐。"
        events = [_assistant_state(message_id, "clarifying", "需要确认一个关键偏好")]
        events.extend(_text_delta_events(message_id, question))
        events.append(
            {
                "type": "clarification_request",
                "message_id": message_id,
                "question": question,
                "options": [
                    {"label": "拍照优先", "message": "拍照优先"},
                    {"label": "续航优先", "message": "续航优先"},
                    {"label": "性价比", "message": "性价比优先"},
                ],
            }
        )
        events.append({"type": "done", "message_id": message_id})
        return events

    def _build_comparison_events(self, request: ChatRequest) -> list[dict]:
        context = self.sessions.get(request.session_id)
        product_ids = _resolve_mentioned_product_ids(request.message, context.last_product_ids)
        products = [self.product_map[product_id] for product_id in product_ids if product_id in self.product_map]
        message_id = _message_id()
        if len(products) < 2:
            text = "我还没有足够的最近推荐商品可以对比。你可以先让我推荐几款，再说第一款和第二款怎么选。"
            return [
                _assistant_state(message_id, "clarifying", "缺少可对比商品"),
                *_text_delta_events(message_id, text),
                {"type": "done", "message_id": message_id},
            ]
        recommendation = _pick_comparison_winner(products, request.message)
        comparison = {
            "type": "comparison_result",
            "message_id": message_id,
            "items": [_comparison_item(product, request.message) for product in products],
            "recommendation": {
                "product_id": recommendation.product_id,
                "reason": _comparison_reason(recommendation, request.message),
            },
        }
        text = (
            f"我把你刚才看的 {len(products)} 款放在一起比。"
            f"如果只选一款，我更建议「{recommendation.title}」，因为{comparison['recommendation']['reason']}。"
        )
        return [
            _assistant_state(message_id, "comparing", "正在对比最近推荐商品"),
            *_text_delta_events(message_id, text),
            comparison,
            _quick_actions_event(message_id, context.last_plan or _default_plan(request.message), []),
            {"type": "done", "message_id": message_id},
        ]

    def _build_bundle_events(self, request: ChatRequest, plan: RetrievalPlan) -> list[dict]:
        context = self.sessions.get(request.session_id)
        message_id = _message_id()
        bundle_id = "bundle_" + uuid.uuid4().hex[:8]
        slots = [
            ("防晒护理", "防晒霜", "防晒 海边 三亚 防水 清爽"),
            ("穿搭", "速干T恤", "三亚 海边 轻便 速干 衣服"),
            ("出行配件", "帽子", "海边 遮阳 防晒 轻便 帽子"),
        ]
        events: list[dict] = [_assistant_state(message_id, "retrieving", "正在拆解场景组合需求")]
        events.extend(_text_delta_events(message_id, "我会按三亚海边的强紫外线、轻便出行和降温舒适来拆成几组搭配。"))
        events.append(
            {
                "type": "bundle_start",
                "message_id": message_id,
                "bundle_id": bundle_id,
                "title": "三亚度假组合方案",
            }
        )
        used_product_ids: list[str] = []
        for index, (group, slot, query) in enumerate(slots):
            slot_plan = RetrievalPlan(
                intent="scenario_bundle",
                retrieval_mode="decompose_parallel",
                category=None,
                hard_constraints=_slot_constraints(slot),
                soft_preferences={"scene": "海边度假"},
                retrieval_query=query,
            )
            ranked = self.retrieve_and_rank(slot_plan)
            if not ranked:
                continue
            item = ranked[0]
            used_product_ids.append(item.product.product_id)
            events.append(
                {
                    "type": "bundle_item",
                    "message_id": message_id,
                    "bundle_id": bundle_id,
                    "group": group,
                    "slot": slot,
                    "index": index,
                    "product": _product_card(item).model_dump(mode="json"),
                }
            )
        events.append({"type": "bundle_done", "message_id": message_id, "bundle_id": bundle_id})
        events.append(
            _quick_actions_event(
                message_id,
                plan,
                [],
                extra=[{"label": "一键加入购物车", "message": "把这套组合加入购物车"}],
            )
        )
        events.append({"type": "done", "message_id": message_id})
        context.last_plan = plan
        context.last_product_ids = used_product_ids
        context.last_recommendations = [
            {"product_id": product_id, "role": "bundle_item", "index": index}
            for index, product_id in enumerate(used_product_ids)
        ]
        if used_product_ids:
            context.focus_product_id = used_product_ids[0]
        return events

    def handle_cart_message(self, request: ChatRequest, cart: CartService) -> dict:
        context = self.sessions.get(request.session_id)
        action = request.action or _detect_cart_action(request.message)
        product_id = request.product_id or _resolve_cart_product_id(request.message, context, cart.get(request.session_id))
        quantity = request.quantity
        detected_quantity = _detect_quantity(request.message)
        if detected_quantity is not None:
            quantity = detected_quantity
        if action == "checkout":
            snapshot = cart.checkout(request.session_id)
            return {"action": action, "product_id": product_id, "cart": snapshot, "message": "已为你模拟下单。"}
        if not product_id:
            snapshot = cart.get(request.session_id)
            return {"action": "get_cart", "product_id": None, "cart": snapshot, "message": "我还没找到要操作的商品。"}
        if action == "update_quantity":
            snapshot = cart.update_quantity(request.session_id, product_id, quantity)
        elif action == "remove":
            snapshot = cart.remove(request.session_id, product_id)
        else:
            action = "add_to_cart"
            snapshot = cart.add(request.session_id, product_id, quantity)
        context.recent_cart_product_id = product_id
        return {"action": action, "product_id": product_id, "cart": snapshot, "message": _cart_message(action, product_id)}

    def is_natural_language_cart_request(self, request: ChatRequest) -> bool:
        if request.type == "cart_action":
            return True
        plan_intent = _detect_cart_action(request.message)
        return plan_intent != "get_cart" or any(word in request.message for word in ["购物车", "下单", "结算"])

    def _remember_recommendations(
        self, context: SessionContext, plan: RetrievalPlan, ranked: list[RankedProduct]
    ) -> None:
        context.last_plan = plan
        context.last_product_ids = [item.product.product_id for item in ranked]
        context.last_recommendations = [
            {"product_id": item.product.product_id, "role": "primary" if index == 0 else "alternative", "index": index}
            for index, item in enumerate(ranked)
        ]
        if ranked:
            context.focus_product_id = ranked[0].product.product_id
            context.active_focus = {
                "focus_type": "product",
                "product_id": ranked[0].product.product_id,
                "origin_constraints": plan.hard_constraints.model_dump(mode="json"),
            }
        _update_profile(context, plan)


def _product_card(item: RankedProduct) -> ProductCard:
    product = item.product
    tags = [product.category, product.sub_category, product.brand_region]
    tags.extend(product.extracted_terms[:3])
    return ProductCard(
        product_id=product.product_id,
        name=product.title,
        brand=product.brand,
        category=product.category,
        sub_category=product.sub_category,
        price=product.price,
        main_image_url=product.image_path,
        tags=[tag for tag in tags if tag],
        reason=item.reason,
        evidence=item.evidence,
    )


def _assistant_state(message_id: str, phase: str, label: str) -> dict:
    return {"type": "assistant_state", "message_id": message_id, "phase": phase, "label": label}


def _understanding_text(plan: RetrievalPlan) -> str:
    constraints = plan.hard_constraints
    handled: list[str] = []
    if constraints.sub_category or constraints.category:
        handled.append(constraints.sub_category or constraints.category or "")
    if constraints.price_max is not None:
        handled.append(f"{constraints.price_max:.0f} 元以内")
    if constraints.exclude_terms:
        handled.append("排除" + "、".join(constraints.exclude_terms))
    if constraints.exclude_brand_regions:
        handled.append("排除" + "、".join(constraints.exclude_brand_regions) + "品牌")
    if plan.soft_preferences:
        handled.extend(str(value) for value in plan.soft_preferences.values() if value)
    if handled:
        return "我先按「" + "、".join(_dedupe(handled)) + "」来筛，先给你一个明确主推。"
    return "我先按你的描述筛一轮，优先给你一个省心的主推选择。"


def _followup_intro(plan: RetrievalPlan) -> str:
    constraints = plan.hard_constraints
    parts: list[str] = []
    if constraints.price_max is not None:
        parts.append(f"预算压到 {constraints.price_max:.0f} 元以内")
    if constraints.exclude_brands:
        parts.append("避开" + "、".join(constraints.exclude_brands))
    if constraints.exclude_terms:
        parts.append("继续排除" + "、".join(constraints.exclude_terms))
    text = "，".join(parts) if parts else "保留刚才的核心条件"
    return f"我会{ text }，再围绕当前商品重新筛。"


def _quick_actions_event(
    message_id: str,
    plan: RetrievalPlan,
    ranked: list[RankedProduct],
    extra: list[dict] | None = None,
) -> dict:
    focus_product_id = ranked[0].product.product_id if ranked else None
    actions = [
        {"label": "更便宜", "message": "换个更便宜的", "payload": {"focus_product_id": focus_product_id}},
        {"label": "不要这个品牌", "message": "不要这个品牌，换一款", "payload": {"focus_product_id": focus_product_id}},
        {"label": "更适合户外", "message": "换个更适合户外的", "payload": {"focus_product_id": focus_product_id}},
    ]
    if plan.hard_constraints.price_max is not None:
        actions.insert(
            1,
            {
                "label": "放宽预算",
                "message": f"预算可以放宽到 {max(plan.hard_constraints.price_max * 1.5, plan.hard_constraints.price_max + 50):.0f} 元",
                "payload": {"focus_product_id": focus_product_id},
            },
        )
    if extra:
        actions.extend(extra)
    return {"type": "quick_actions", "message_id": message_id, "actions": actions[:5]}


def _filter_recovery_event(message_id: str, plan: RetrievalPlan) -> dict:
    constraints = plan.hard_constraints
    options: list[dict] = []
    if constraints.price_max is not None:
        relaxed = max(constraints.price_max * 2, 100)
        options.append({"label": f"放宽预算到 {relaxed:.0f} 元", "message": f"预算放宽到{relaxed:.0f}元以内"})
    if constraints.exclude_terms:
        options.append(
            {
                "label": "保留排除项，换相近类目",
                "message": "保留这些排除要求，换一个相近类目看看",
            }
        )
    if constraints.exclude_brand_regions:
        options.append(
            {
                "label": "只保留非日系要求",
                "message": "先保留非日系要求，其他条件可以放宽",
            }
        )
    if not options:
        options.append({"label": "换个相近需求", "message": "换一个相近需求重新筛"})
    return {"type": "filter_recovery_options", "message_id": message_id, "options": options}


def _resolve_mentioned_product_ids(text: str, last_product_ids: list[str]) -> list[str]:
    index_map = {
        "第一": 0,
        "第1": 0,
        "1": 0,
        "第二": 1,
        "第2": 1,
        "2": 1,
        "第三": 2,
        "第3": 2,
        "3": 2,
    }
    indexes: list[int] = []
    for marker, index in index_map.items():
        if marker in text and index not in indexes:
            indexes.append(index)
    if not indexes:
        indexes = [0, 1]
    return [last_product_ids[index] for index in indexes if index < len(last_product_ids)]


def _comparison_item(product: Product, text: str) -> dict:
    points = []
    if "油皮" in text and "油皮" in product.search_text:
        points.append("明确提到适合油皮")
    if "清爽" in product.search_text:
        points.append("质地或反馈偏清爽")
    if product.review_rating:
        points.append(f"评价均分 {product.review_rating:.1f}")
    if not points:
        points.append("与当前需求语义相关")
    return {
        "product_id": product.product_id,
        "name": product.title,
        "brand": product.brand,
        "price": product.price,
        "key_points": points[:3],
    }


def _pick_comparison_winner(products: list[Product], text: str) -> Product:
    def score(product: Product) -> tuple[int, float, float]:
        oil_score = 1 if "油皮" in text and "油皮" in product.search_text else 0
        clear_score = 1 if "清爽" in product.search_text else 0
        return oil_score + clear_score, product.review_rating, -product.price

    return sorted(products, key=score, reverse=True)[0]


def _comparison_reason(product: Product, text: str) -> str:
    if "油皮" in text and "油皮" in product.search_text:
        return "它的商品信息里更明确覆盖油皮需求"
    if "清爽" in product.search_text:
        return "它更贴近日常清爽使用场景"
    if product.review_rating:
        return "它的评价表现更稳"
    return "它和当前需求的商品信息更贴近"


def _slot_constraints(slot: str) -> HardConstraints:
    aliases = {"防晒霜": "防晒", "速干T恤": "速干T恤", "帽子": "帽子", "背包": "背包"}
    sub_category = aliases.get(slot, slot)
    category = "美妆护肤" if sub_category == "防晒" else "服饰运动"
    return HardConstraints(category=category, sub_category=sub_category)


def _default_plan(text: str) -> RetrievalPlan:
    return RetrievalPlan(hard_constraints=HardConstraints(), retrieval_query=text or "商品推荐")


def _wants_different_brand(text: str) -> bool:
    return any(word in text for word in ["不要这个品牌", "换个品牌", "别的品牌", "不要这个牌子"])


def _detect_cart_action(text: str) -> str:
    if any(word in text for word in ["下单", "结算"]):
        return "checkout"
    if any(word in text for word in ["删掉", "删除", "移除"]):
        return "remove"
    if any(word in text for word in ["数量", "改成", "改为"]):
        return "update_quantity"
    if any(word in text for word in ["购物车", "加购", "加入", "加到"]):
        return "add_to_cart"
    return "get_cart"


def _resolve_cart_product_id(text: str, context: SessionContext, cart_snapshot: dict) -> str | None:
    mentioned = _resolve_mentioned_product_ids(text, context.last_product_ids)
    if mentioned:
        return mentioned[0]
    if any(word in text for word in ["刚才", "这款", "这个", "主推"]):
        return context.focus_product_id or (context.last_product_ids[0] if context.last_product_ids else None)
    if context.recent_cart_product_id:
        return context.recent_cart_product_id
    items = cart_snapshot.get("items", [])
    if items:
        return items[0].get("product_id")
    return context.focus_product_id or (context.last_product_ids[0] if context.last_product_ids else None)


def _detect_quantity(text: str) -> int | None:
    match = re.search(r"(?:数量)?(?:改成|改为|设为)?\s*(\d+)", text)
    if match:
        return max(int(match.group(1)), 0)
    chinese_digits = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}
    for word, value in chinese_digits.items():
        if f"{word}件" in text or f"{word}个" in text:
            return value
    return None


def _cart_message(action: str, product_id: str) -> str:
    if action == "update_quantity":
        return f"已更新 {product_id} 的数量。"
    if action == "remove":
        return f"已从购物车移除 {product_id}。"
    return f"已把 {product_id} 加入购物车。"


def _update_profile(context: SessionContext, plan: RetrievalPlan) -> None:
    for key, value in plan.soft_preferences.items():
        if value:
            context.global_profile[key] = value
    constraints = plan.hard_constraints
    if constraints.price_max is not None:
        context.global_profile["budget_max"] = constraints.price_max
    if constraints.exclude_terms:
        context.global_profile["exclude_terms"] = constraints.exclude_terms
    if constraints.exclude_brand_regions:
        context.global_profile["exclude_brand_regions"] = constraints.exclude_brand_regions


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _text_delta_events(message_id: str, text: str) -> list[dict]:
    if not text:
        return []
    chunks = [text[i : i + 12] for i in range(0, len(text), 12)]
    return [{"type": "text_delta", "message_id": message_id, "text": chunk} for chunk in chunks]


def _message_id() -> str:
    return "assistant_" + uuid.uuid4().hex[:10]


def _no_match_text(plan: RetrievalPlan) -> str:
    constraints = plan.hard_constraints
    parts: list[str] = []
    if constraints.sub_category or constraints.category:
        parts.append(constraints.sub_category or constraints.category or "")
    if constraints.price_max is not None:
        parts.append(f"{constraints.price_max:.0f} 元以内")
    if constraints.exclude_terms:
        parts.append("不含" + "、".join(constraints.exclude_terms))
    if constraints.exclude_brand_regions:
        parts.append("排除" + "、".join(constraints.exclude_brand_regions) + "品牌")
    condition_text = "、".join(part for part in parts if part) or "这些条件"
    return (
        f"我按「{condition_text}」做了硬过滤，当前商品库里没有完全满足的商品。"
        "为了不违反你的明确要求，我先不推荐不合规替代品。"
        "你可以放宽预算、取消一个排除条件，或者换成相近类目，我再继续帮你筛。"
    )
