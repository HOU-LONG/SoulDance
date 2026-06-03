from __future__ import annotations

from collections.abc import AsyncIterator
import json
import re
import uuid

from .cart import CartService
from .constraint_filter import hard_filter
from .embedding_retriever import BM25OnlyRetriever
from .intent_compiler import IntentCompiler
from .llm_client import FakeLLMClient
from .memory_cache import StructuredMemoryCache
from .models import (
    ChatRequest,
    HardConstraints,
    PendingClarification,
    Product,
    ProductCard,
    RankedProduct,
    RecommendationMemoryItem,
    RetrievalPlan,
    SessionContext,
)
from .planner_agent import PlannerAgent
from .query_builder import QueryBuilder
from .ranker import rank_products
from .reference_resolver import ReferenceResolver
from .semantic_layer import SemanticParser, rule_semantic_frame
from .session_store import SessionStore
from .state_reducer import StateReducer, seed_constraint_state_from_plan
from .taxonomy import TaxonomyResolver
from .tts_adapter import TTSAdapter


class ShopGuideAgent:
    def __init__(
        self,
        products: list[Product],
        llm_client=None,
        retriever=None,
        session_store: SessionStore | None = None,
        tts_adapter: TTSAdapter | None = None,
        memory_cache: StructuredMemoryCache | None = None,
    ):
        self.products = products
        self.product_map = {product.product_id: product for product in products}
        self.llm_client = llm_client or FakeLLMClient()
        self.retriever = retriever or BM25OnlyRetriever(products)
        self.sessions = session_store or SessionStore()
        self.planner = PlannerAgent(self.llm_client)
        self.semantic_parser = SemanticParser(self.llm_client)
        self.intent_compiler = IntentCompiler(self.llm_client, self.semantic_parser)
        self.state_reducer = StateReducer()
        self.reference_resolver = ReferenceResolver(self.product_map)
        self.tts = tts_adapter or TTSAdapter()
        self.memory_cache = memory_cache
        self.taxonomy = TaxonomyResolver.from_products(products)
        self.query_builder = QueryBuilder(self.taxonomy)

    async def plan(self, request: ChatRequest) -> RetrievalPlan:
        context = self.sessions.get(request.session_id)
        seed_constraint_state_from_plan(context, context.last_plan)
        ir = await self.intent_compiler.compile(request, context)
        if _is_pending_clarification_answer(context, request, ir):
            ir.intent = "recommend_product"
            _apply_pending_answer_preferences(ir, request.message)
        self._prepare_context_for_turn(context, request, ir)
        self.state_reducer.apply(context, ir, request.message)
        plan = self.query_builder.build(ir, context, request.message)
        self.taxonomy.apply_to_constraints(plan.hard_constraints, request.message)
        plan.category = plan.hard_constraints.sub_category or plan.hard_constraints.category or plan.category
        self._apply_product_admission_gate(plan, request.message)
        context.last_plan = plan
        context.state.trace.last_execution_plan = {"retrieval_plan": plan.model_dump(mode="json")}
        return plan

    def retrieve_and_rank(self, plan: RetrievalPlan, limit: int = 8) -> list[RankedProduct]:
        if self.memory_cache and plan.intent in {"recommend_product", "product_followup"}:
            cached = self.memory_cache.get(plan, self.product_map)
            if cached is not None:
                return cached
        retrieved = self.retriever.search(plan.retrieval_query, top_k=30)
        if retrieved:
            candidates = [product for product, _ in retrieved]
            scores = {product.product_id: score for product, score in retrieved}
        else:
            candidates = self.products
            scores = {}
        ranked = rank_products(candidates, plan, scores, limit=limit)
        if not ranked and candidates != self.products:
            ranked = rank_products(self.products, plan, {}, limit=limit)
        if self.memory_cache and plan.intent in {"recommend_product", "product_followup"}:
            self.memory_cache.put(plan, ranked)
        return ranked

    async def handle_message(self, request: ChatRequest) -> list[dict]:
        return [event async for event in self.stream_message(request)]

    async def compile_intent(self, request: ChatRequest):
        context = self.sessions.get(request.session_id)
        seed_constraint_state_from_plan(context, context.last_plan)
        return await self.intent_compiler.compile(request, context)

    async def stream_message(self, request: ChatRequest, compiled_ir=None) -> AsyncIterator[dict]:
        context = self.sessions.get(request.session_id)
        seed_constraint_state_from_plan(context, context.last_plan)
        ir = compiled_ir or await self.intent_compiler.compile(request, context)
        if _is_pending_clarification_answer(context, request, ir):
            ir.intent = "recommend_product"
            _apply_pending_answer_preferences(ir, request.message)
        if request.type == "product_followup" or (request.type == "user_message" and ir.intent == "product_followup"):
            async for event in self._stream_followup(request, ir):
                yield event
            return
        if ir.intent in {"small_talk", "unclear_input"}:
            async for event in self._stream_no_retrieval_events(request, ir.intent):
                yield event
            return
        context_action = self._prepare_context_for_turn(context, request, ir)
        self.state_reducer.apply(context, ir, request.message)
        plan = self.query_builder.build(ir, context, request.message)
        self.taxonomy.apply_to_constraints(plan.hard_constraints, request.message)
        plan.category = plan.hard_constraints.sub_category or plan.hard_constraints.category or plan.category
        self._apply_product_admission_gate(plan, request.message)
        context.last_plan = plan
        context.state.trace.last_execution_plan = {"retrieval_plan": plan.model_dump(mode="json")}
        if plan.intent in {"small_talk", "unclear_input"}:
            async for event in self._stream_no_retrieval_events(request, plan.intent):
                yield event
            return
        if plan.need_clarification or plan.intent == "clarification":
            for event in self._build_clarification_events(context, plan, context_action):
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
        if _looks_like_product_request(request.message) and not self.taxonomy.is_known_request(request.message):
            message_id = _message_id()
            text = _unknown_category_text(request.message)
            yield self._assistant_state(message_id, "clarifying", "当前商品库没有匹配类目", plan)
            for event in _text_delta_events(message_id, text):
                yield event
            yield _filter_recovery_event(message_id, plan)
            yield {"type": "done", "message_id": message_id}
            return
        ranked = self.retrieve_and_rank(plan)
        async for event in self._stream_recommendation_events(request, plan, ranked, context_action):
            yield event

    async def _handle_followup(self, request: ChatRequest) -> list[dict]:
        return [event async for event in self._stream_followup(request)]

    async def _stream_followup(self, request: ChatRequest, ir=None) -> AsyncIterator[dict]:
        context = self.sessions.get(request.session_id)
        if request.focus_product_id:
            context.focus_product_id = request.focus_product_id
            context.state.active_focus.type = "product"
            context.state.active_focus.product_id = request.focus_product_id
            context.state.active_focus.source = "product_card"
        context.focus_history.append(request.message)
        if request.type == "user_message" and not (context.focus_product_id or context.last_product_ids):
            message_id = _message_id()
            text = "我还没有可以替换或解释的上一款商品。你可以先告诉我想买什么，或者让我先推荐一款。"
            yield self._assistant_state(
                message_id,
                "chatting",
                "缺少可追问商品",
                intent="unclear_input",
                retrieval_mode="no_retrieval",
            )
            for event in _text_delta_events(message_id, text):
                yield event
            yield {"type": "done", "message_id": message_id}
            return
        if ir is None:
            seed_constraint_state_from_plan(context, context.last_plan)
            ir = await self.intent_compiler.compile(request, context)
        self._prepare_context_for_turn(context, request, ir)
        self.state_reducer.apply(context, ir, request.message)
        plan = self.query_builder.build(ir, context, request.message)
        self.taxonomy.apply_to_constraints(plan.hard_constraints, request.message)
        plan.category = plan.hard_constraints.sub_category or plan.hard_constraints.category or plan.category
        plan.intent = "product_followup"
        plan.retrieval_mode = "product_focus_retrieval"
        focus_product = self.product_map.get(request.focus_product_id or context.focus_product_id or "")
        if focus_product and _wants_cheaper_alternative(request.message, ir):
            new_max = max(focus_product.price - 0.01, 0)
            current_max = plan.hard_constraints.price_max
            plan.hard_constraints.price_max = min(current_max, new_max) if current_max is not None else new_max
            context.state.constraint_state.hard.price_max = plan.hard_constraints.price_max
            plan.soft_preferences["price_preference"] = "更便宜"
            context.state.constraint_state.soft["price_preference"] = "更便宜"
        if focus_product and _wants_different_brand(request.message, ir):
            plan.hard_constraints.exclude_brands = _dedupe(plan.hard_constraints.exclude_brands + [focus_product.brand])
            context.state.constraint_state.hard.exclude_brands = list(plan.hard_constraints.exclude_brands)
            context.negative_feedback.append(f"不要品牌:{focus_product.brand}")
            context.state.user_profile.negative_preferences.append(f"不要品牌:{focus_product.brand}")
        context.last_plan = plan
        context.state.trace.last_execution_plan = {"retrieval_plan": plan.model_dump(mode="json")}
        message_id = _message_id()
        is_explain_request = bool(focus_product and _is_explain_focus_request(request.message, ir))
        intro = "我来说明刚刚那款商品。" if is_explain_request else _followup_intro(plan)
        label = "正在解释当前商品" if is_explain_request else "正在按当前商品上下文重新筛选"
        phase = "explaining" if is_explain_request else "retrieving"
        yield self._assistant_state(message_id, phase, label, plan)
        for event in _text_delta_events(message_id, intro):
            yield event
        if is_explain_request:
            text = _focus_product_explanation(focus_product, context)
            for event in _text_delta_events(message_id, text):
                yield event
            yield {"type": "focus_done", "message_id": message_id}
            for event in await self.tts.synthesize_events(intro + text, request.tts_enabled):
                yield event
            return
        ranked = self.retrieve_and_rank(plan)
        if ranked:
            self._remember_recommendations(context, plan, ranked)
        if ranked:
            replacement = _product_card(ranked[0])
            replacement_event = {
                "type": "replacement_product",
                "message_id": message_id,
                "focus_product_id": request.focus_product_id,
                "reason": ranked[0].reason,
                "product": replacement.model_dump(mode="json"),
            }
            yield replacement_event
            text_parts: list[str] = []
            async for event in self._stream_generate_text_events(message_id, request, plan, ranked, focus_product):
                text_parts.append(event["text"])
                yield event
            text = "".join(text_parts)
            if request.type == "user_message":
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
        self,
        request: ChatRequest,
        plan: RetrievalPlan,
        ranked: list[RankedProduct],
        context_action: str = "same_task",
    ) -> AsyncIterator[dict]:
        message_id = _message_id()
        intro = _understanding_text(plan)
        yield self._assistant_state(
            message_id,
            "retrieving",
            "正在理解需求并筛选商品",
            plan,
            selection_mode="llm_selection",
            candidate_count=len(ranked),
            context_action=context_action,
        )
        for event in _text_delta_events(message_id, intro):
            yield event
        selected = await self._select_products(request, plan, ranked)
        yield self._assistant_state(
            message_id,
            "selecting",
            "已完成候选商品决策",
            plan,
            selection_mode="llm_selection",
            candidate_count=len(ranked),
            selected_count=len(selected),
            context_action=context_action,
        )
        if not selected:
            context = self.sessions.get(request.session_id)
            context.state.pending_clarification = None
            text = _no_match_text(plan)
            for event in _text_delta_events(message_id, text):
                yield event
            yield _filter_recovery_event(message_id, plan)
            yield {"type": "done", "message_id": message_id}
            for event in await self.tts.synthesize_events(intro + text, request.tts_enabled):
                yield event
            return
        context = self.sessions.get(request.session_id)
        self._remember_recommendations(context, plan, selected)
        text_parts: list[str] = []
        async for event in self._stream_generate_text_events(message_id, request, plan, selected, None):
            text_parts.append(event["text"])
            yield event
        text = "".join(text_parts)
        yield {"type": "products_start", "message_id": message_id}
        for index, item in enumerate(selected):
            yield {
                "type": "product_item",
                "message_id": message_id,
                "index": index,
                "role": "primary" if index == 0 else "alternative",
                "product": _product_card(item).model_dump(mode="json"),
            }
        yield {"type": "products_done", "message_id": message_id}
        yield _quick_actions_event(message_id, plan, selected)
        yield {"type": "done", "message_id": message_id}
        for event in await self.tts.synthesize_events(intro + text, request.tts_enabled):
            yield event

    async def _select_products(
        self,
        request: ChatRequest,
        plan: RetrievalPlan,
        candidates: list[RankedProduct],
    ) -> list[RankedProduct]:
        if not candidates:
            return []
        by_id = {item.product.product_id: item for item in candidates}
        try:
            raw = await self.llm_client.select_products(request.message, plan, candidates)
            data = _extract_json_object(raw)
            if data.get("need_clarification") is True or data.get("should_recommend") is False:
                return []
            selected_ids = data.get("selected_product_ids", [])
            reasons = data.get("reasons", {})
        except Exception:
            selected = _fallback_selected_products(candidates)
            return selected
        if not isinstance(selected_ids, list):
            return _fallback_selected_products(candidates)
        if not isinstance(reasons, dict):
            reasons = {}
        selected: list[RankedProduct] = []
        seen: set[str] = set()
        for product_id in selected_ids:
            product_id = str(product_id)
            if product_id in seen or product_id not in by_id:
                continue
            item = by_id[product_id]
            if not hard_filter(item.product, plan.hard_constraints):
                continue
            reason = str(reasons.get(product_id, "")).strip()
            if reason:
                item = item.model_copy(update={"reason": reason})
            selected.append(item)
            seen.add(product_id)
            if len(selected) >= 4:
                break
        if selected:
            return selected
        return []

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

    async def _stream_generate_text_events(
        self,
        message_id: str,
        request: ChatRequest,
        plan: RetrievalPlan,
        ranked: list[RankedProduct],
        focus_product: Product | None,
    ) -> AsyncIterator[dict]:
        if not ranked:
            for event in _text_delta_events(message_id, _no_match_text(plan)):
                yield event
            return
        try:
            got_chunk = False
            async for chunk in self.llm_client.stream_response(request.message, plan, ranked, focus_product):
                if chunk:
                    got_chunk = True
                    yield {"type": "text_delta", "message_id": message_id, "text": chunk}
            if got_chunk:
                return
        except Exception:
            pass
        text = await self._safe_generate_text(request, plan, ranked, focus_product)
        for event in _text_delta_events(message_id, text):
            yield event

    def _build_clarification_events(
        self, context: SessionContext, plan: RetrievalPlan, context_action: str = "same_task"
    ) -> list[dict]:
        message_id = _message_id()
        question = plan.clarification_question or "我需要再确认一个关键偏好，才能更稳地推荐。"
        _remember_pending_clarification(context, plan, question)
        events = [
            self._assistant_state(
                message_id,
                "clarifying",
                "需要确认一个关键偏好",
                plan,
                context_action=context_action,
            )
        ]
        events.extend(_text_delta_events(message_id, question))
        events.append(
            {
                "type": "clarification_request",
                "message_id": message_id,
                "question": question,
                "options": _clarification_options(question),
            }
        )
        events.append({"type": "done", "message_id": message_id})
        return events

    async def _stream_no_retrieval_events(self, request: ChatRequest, intent: str = "small_talk") -> AsyncIterator[dict]:
        message_id = _message_id()
        if intent == "unclear_input":
            label = "未识别到明确购物需求"
            fallback = "我还没太抓到你的购物需求。你可以随便说个想买的东西、预算，或者不想要什么，我再帮你筛。"
        else:
            label = "回应寒暄"
            fallback = "我在，可以陪你慢慢挑。你告诉我想买什么、预算多少，或者有什么偏好就行。"
        yield self._assistant_state(
            message_id,
            "chatting",
            label,
            intent=intent,
            retrieval_mode="no_retrieval",
        )
        try:
            got_chunk = False
            async for chunk in self.llm_client.stream_chitchat_response(request.message, intent, self.sessions.get(request.session_id)):
                if chunk:
                    got_chunk = True
                    yield {"type": "text_delta", "message_id": message_id, "text": chunk}
            if got_chunk:
                yield {"type": "done", "message_id": message_id}
                return
        except Exception:
            pass
        for event in _text_delta_events(message_id, fallback):
            yield event
        yield {"type": "done", "message_id": message_id}

    def _apply_product_admission_gate(self, plan: RetrievalPlan, message: str) -> None:
        if plan.intent not in {"recommend_product", "product_followup", "clarification"}:
            return
        if _has_product_admission_signal(message, plan, self.taxonomy):
            return
        plan.intent = "unclear_input"
        plan.retrieval_mode = "no_retrieval"
        plan.need_clarification = False
        plan.clarification_question = None
        plan.category = None

    def _prepare_context_for_turn(self, context: SessionContext, request: ChatRequest, ir) -> str:
        if request.type == "product_followup":
            return "followup"
        if ir.intent not in {"recommend_product", "clarification"}:
            return ir.intent
        explicit_match = self.taxonomy.resolve_task_object(request.message)
        pending = context.state.pending_clarification
        if explicit_match:
            current = context.state.constraint_state.hard
            current_sub = current.sub_category
            current_category = current.category
            target_sub = explicit_match.sub_category
            target_category = explicit_match.category
            pending_sub = pending.sub_category if pending else None
            pending_category = pending.category if pending else None
            is_conflict = (
                (target_sub and current_sub and target_sub != current_sub)
                or (target_sub and pending_sub and target_sub != pending_sub)
                or (not target_sub and target_category and current_category and target_category != current_category)
                or (not target_sub and target_category and pending_category and target_category != pending_category)
            )
            if is_conflict:
                _reset_shopping_task(context)
                return "new_task"
            if pending and (
                (target_sub and target_sub == pending.sub_category)
                or (not target_sub and target_category == pending.category)
            ):
                _seed_pending_constraints(context)
                return "clarification_answer"
            return "same_task"
        if pending and _looks_like_clarification_answer(request.message, ir):
            _seed_pending_constraints(context)
            return "clarification_answer"
        return "same_task"

    def _assistant_state(
        self,
        message_id: str,
        phase: str,
        label: str,
        plan: RetrievalPlan | None = None,
        intent: str | None = None,
        retrieval_mode: str | None = None,
        selection_mode: str | None = None,
        candidate_count: int | None = None,
        selected_count: int | None = None,
        context_action: str | None = None,
    ) -> dict:
        return _assistant_state(
            message_id,
            phase,
            label,
            intent=intent or (plan.intent if plan else None),
            retrieval_mode=retrieval_mode or (plan.retrieval_mode if plan else None),
            llm_mode=_llm_mode(self.llm_client),
            selection_mode=selection_mode,
            candidate_count=candidate_count,
            selected_count=selected_count,
            context_action=context_action,
        )

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
            {
                "product_id": item.product.product_id,
                "title": item.product.title,
                "brand": item.product.brand,
                "category": item.product.category,
                "sub_category": item.product.sub_category,
                "price": item.product.price,
                "reason": item.reason,
                "role": "primary" if index == 0 else "alternative",
                "index": index,
            }
            for index, item in enumerate(ranked)
        ]
        context.state.recommendation_memory.last_set_id = "recset_" + uuid.uuid4().hex[:8]
        context.state.recommendation_memory.items = [
            RecommendationMemoryItem(
                index=index,
                product_id=item.product.product_id,
                role="primary" if index == 0 else "alternative",
                score=item.score,
            )
            for index, item in enumerate(ranked)
        ]
        context.state.constraint_state.hard = plan.hard_constraints.model_copy(deep=True)
        context.state.constraint_state.soft = dict(plan.soft_preferences)
        context.state.pending_clarification = None
        context.state.current_task.category = plan.hard_constraints.category
        context.state.current_task.sub_category = plan.hard_constraints.sub_category
        if not context.state.current_task.task_id:
            context.state.current_task.task_id = "task_" + uuid.uuid4().hex[:8]
        if ranked:
            context.focus_product_id = ranked[0].product.product_id
            context.active_focus = {
                "focus_type": "product",
                "product_id": ranked[0].product.product_id,
                "origin_constraints": plan.hard_constraints.model_dump(mode="json"),
            }
            context.state.active_focus.type = "product"
            context.state.active_focus.product_id = ranked[0].product.product_id
            context.state.active_focus.source = "recommendation"
        _update_profile(context, plan)

    async def try_handle_cart_message(self, request: ChatRequest, cart: CartService, compiled_ir=None) -> dict | None:
        context = self.sessions.get(request.session_id)
        frame = compiled_ir or await self.intent_compiler.compile(request, context)
        if compiled_ir is None and (frame.intent != "cart_operation" or frame.cart_operation is None):
            frame = rule_semantic_frame(request)
        if frame.intent != "cart_operation" or frame.cart_operation is None:
            return None
        action = _normalize_cart_action(frame.cart_operation.action)
        quantity = max(frame.cart_operation.quantity, 0)
        resolution = self.reference_resolver.resolve(
            frame.cart_operation.target,
            context,
            cart.get(request.session_id),
        )
        product_id = resolution.product_id
        return self._execute_cart_action(request.session_id, action, product_id, quantity, cart)

    def execute_cart_action(
        self,
        session_id: str,
        action: str,
        product_id: str | None,
        quantity: int,
        cart: CartService,
    ) -> dict:
        return self._execute_cart_action(session_id, action, product_id, quantity, cart)

    def _execute_cart_action(
        self,
        session_id: str,
        action: str,
        product_id: str | None,
        quantity: int,
        cart: CartService,
    ) -> dict:
        context = self.sessions.get(session_id)
        if action == "checkout":
            snapshot = cart.checkout(session_id)
            return {"action": action, "product_id": product_id, "cart": snapshot, "message": "已为你模拟下单。"}
        if not product_id:
            snapshot = cart.get(session_id)
            return {"action": "get_cart", "product_id": None, "cart": snapshot, "message": "我还没找到要操作的商品。"}
        if action == "update_quantity":
            snapshot = cart.update_quantity(session_id, product_id, quantity)
        elif action == "remove":
            snapshot = cart.remove(session_id, product_id)
        else:
            action = "add_to_cart"
            snapshot = cart.add(session_id, product_id, quantity)
        context.recent_cart_product_id = product_id
        context.state.cart_memory.recent_product_id = product_id
        return {"action": action, "product_id": product_id, "cart": snapshot, "message": _cart_message(action, product_id)}


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


def _assistant_state(
    message_id: str,
    phase: str,
    label: str,
    intent: str | None = None,
    retrieval_mode: str | None = None,
    llm_mode: str | None = None,
    selection_mode: str | None = None,
    candidate_count: int | None = None,
    selected_count: int | None = None,
    context_action: str | None = None,
) -> dict:
    event = {"type": "assistant_state", "message_id": message_id, "phase": phase, "label": label}
    if intent:
        event["intent"] = intent
    if retrieval_mode:
        event["retrieval_mode"] = retrieval_mode
    if llm_mode:
        event["llm_mode"] = llm_mode
    if selection_mode:
        event["selection_mode"] = selection_mode
    if candidate_count is not None:
        event["candidate_count"] = candidate_count
    if selected_count is not None:
        event["selected_count"] = selected_count
    if context_action:
        event["context_action"] = context_action
    return event


def _reset_shopping_task(context: SessionContext) -> None:
    context.state.constraint_state.hard = HardConstraints()
    context.state.constraint_state.soft = {}
    context.state.pending_clarification = None
    context.state.current_task.task_id = "task_" + uuid.uuid4().hex[:8]
    context.state.current_task.category = None
    context.state.current_task.sub_category = None
    context.last_product_ids = []
    context.last_recommendations = []
    context.focus_product_id = None
    context.active_focus = {}
    context.state.active_focus.type = None
    context.state.active_focus.product_id = None
    context.state.active_focus.source = None
    context.state.recommendation_memory.items = []
    context.state.recommendation_memory.last_set_id = None


def _seed_pending_constraints(context: SessionContext) -> None:
    pending = context.state.pending_clarification
    if not pending:
        return
    hard = context.state.constraint_state.hard
    hard.category = pending.category or hard.category
    hard.sub_category = pending.sub_category or hard.sub_category


def _remember_pending_clarification(context: SessionContext, plan: RetrievalPlan, question: str) -> None:
    constraints = plan.hard_constraints
    context.state.pending_clarification = PendingClarification(
        category=constraints.category,
        sub_category=constraints.sub_category,
        question=question,
        created_turn=context.state.dialog_state.turn_index,
    )
    context.state.current_task.category = constraints.category
    context.state.current_task.sub_category = constraints.sub_category


def _looks_like_clarification_answer(message: str, ir) -> bool:
    edits = ir.constraint_edits
    if edits.add.price_max is not None or edits.add.soft_preferences:
        return True
    if ir.query_intent.soft_preferences:
        return True
    return bool(re.search(r"预算|以内|以下|拍照|续航|性价比|性能|轻薄|便携|清爽|温和|保湿|修护", message or ""))


def _is_pending_clarification_answer(context: SessionContext, request: ChatRequest, ir) -> bool:
    return (
        request.type == "user_message"
        and ir.intent == "unclear_input"
        and context.state.pending_clarification is not None
        and _looks_like_clarification_answer(request.message, ir)
    )


def _apply_pending_answer_preferences(ir, message: str) -> None:
    soft = ir.constraint_edits.add.soft_preferences
    if "拍照" in message:
        soft["priority"] = "拍照"
    if "续航" in message:
        soft["priority"] = "续航"
    if "性价比" in message:
        soft["priority"] = "性价比"
    if "轻薄" in message or "便携" in message:
        soft["priority"] = "轻薄便携"
    if "性能" in message or "游戏" in message:
        soft["priority"] = "性能优先"
    if "清爽" in message:
        soft["texture"] = "清爽"
    if "温和" in message:
        soft["texture"] = "温和"
    if "保湿" in message or "修护" in message:
        soft["effect"] = "保湿修护"


def _llm_mode(llm_client) -> str:
    if isinstance(llm_client, FakeLLMClient):
        return "fake"
    return "doubao"


def _extract_json_object(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    return data if isinstance(data, dict) else {}


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


def _has_product_admission_signal(message: str, plan: RetrievalPlan, taxonomy: TaxonomyResolver) -> bool:
    constraints = plan.hard_constraints
    if plan.intent in {"product_followup", "clarification"} and (
        constraints.category
        or constraints.sub_category
        or constraints.price_max is not None
        or constraints.exclude_terms
        or constraints.exclude_brands
        or constraints.exclude_brand_regions
        or plan.soft_preferences
    ):
        return True
    if taxonomy.resolve(message):
        return True
    if constraints.category or constraints.sub_category:
        return True
    if constraints.price_max is not None or constraints.exclude_terms or constraints.exclude_brands or constraints.exclude_brand_regions:
        return True
    if plan.soft_preferences:
        return True
    return bool(
        re.search(
            r"推荐|找|买|想要|想买|看看|有没有|预算|以内|以下|不要|不含|排除|对比|比较|哪个更|购物车|加购|加入|下单|结算|"
            r"礼物|送人|送给",
            message or "",
            flags=re.I,
        )
    )


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
    focus_brand = ranked[0].product.brand if ranked else None
    actions = [
        {"label": "更便宜", "message": "换个更便宜的", "payload": {"focus_product_id": focus_product_id}},
        {"label": "更适合户外", "message": "换个更适合户外的", "payload": {"focus_product_id": focus_product_id}},
    ]
    if focus_brand:
        actions.insert(
            1,
            {
                "label": f"不要{focus_brand}",
                "message": f"不要{focus_brand}，换一款",
                "payload": {"focus_product_id": focus_product_id},
            },
        )
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


def _clarification_options(question: str) -> list[dict[str, str]]:
    if "笔记本" in question:
        return [
            {"label": "轻薄便携", "message": "轻薄便携"},
            {"label": "性能优先", "message": "性能优先"},
            {"label": "性价比", "message": "性价比优先"},
        ]
    if "送礼" in question:
        return [
            {"label": "实用礼物", "message": "实用礼物"},
            {"label": "惊喜感", "message": "更有惊喜感"},
            {"label": "稳妥不踩雷", "message": "稳妥不踩雷"},
        ]
    if "选鞋" in question:
        return [
            {"label": "跑步训练", "message": "跑步训练"},
            {"label": "篮球运动", "message": "篮球运动"},
            {"label": "户外通勤", "message": "户外通勤"},
        ]
    if "护肤品" in question:
        return [
            {"label": "油皮清爽", "message": "油皮清爽"},
            {"label": "敏感肌温和", "message": "敏感肌温和"},
            {"label": "保湿修护", "message": "保湿修护"},
        ]
    return [
        {"label": "拍照优先", "message": "拍照优先"},
        {"label": "续航优先", "message": "续航优先"},
        {"label": "性价比", "message": "性价比优先"},
    ]


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


def _looks_like_product_request(text: str) -> bool:
    return any(word in text for word in ["推荐", "找", "买", "想要", "有没有"])


def _unknown_category_text(text: str) -> str:
    return "当前商品库里还没有能稳定匹配这个需求的类目。为了不跨类目乱推荐，我先不返回商品卡。你可以换成现有商品类目再试。"


def _is_explain_focus_request(text: str, ir) -> bool:
    return ir.response_goal == "explain_focus_product" or any(
        word in text for word in ["刚刚那个是什么", "刚才那个是什么", "为什么推荐", "介绍一下", "这个是什么"]
    )


def _wants_cheaper_alternative(text: str, ir) -> bool:
    if ir.response_goal == "recommend_cheaper_alternative":
        return True
    if ir.constraint_edits.add.soft_preferences.get("price_preference") == "更便宜":
        return True
    return any(word in text for word in ["更便宜", "便宜点", "便宜的", "价格低"])


def _wants_different_brand(text: str, ir=None) -> bool:
    if ir is not None and ir.response_goal == "exclude_current_brand":
        return True
    return any(word in text for word in ["不要这个品牌", "换个品牌", "别的品牌", "不要这个牌子"])


def _focus_product_explanation(product: Product, context: SessionContext) -> str:
    reason = ""
    for item in context.last_recommendations:
        if item.get("product_id") == product.product_id:
            reason = str(item.get("reason") or "")
            break
    reason_text = f"推荐理由是：{reason}。" if reason else ""
    return (
        f"刚刚那款是「{product.title}」，品牌是 {product.brand}，属于{product.sub_category}，"
        f"价格 {product.price:.0f} 元。{reason_text}"
        "如果你想换更便宜的、避开这个品牌，或者看同类备选，我可以继续筛。"
    )


def _detect_cart_action(text: str) -> str:
    if any(word in text for word in ["不要这个品牌", "不要这个牌子"]):
        return "get_cart"
    if any(word in text for word in ["下单", "结算"]):
        return "checkout"
    if any(word in text for word in ["删掉", "删除", "移除"]):
        return "remove"
    if any(word in text for word in ["数量", "改成", "改为"]):
        return "update_quantity"
    if any(word in text for word in ["购物车", "加购", "加入", "加到"]):
        return "add_to_cart"
    return "get_cart"


def _normalize_cart_action(action: str) -> str:
    if action in {"add", "add_to_cart"}:
        return "add_to_cart"
    if action in {"update", "set_quantity", "update_quantity"}:
        return "update_quantity"
    if action in {"delete", "remove"}:
        return "remove"
    if action in {"checkout", "order"}:
        return "checkout"
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
