"""
ShopGuide 导购 Agent — 后端核心编排器。

===== 在项目中的角色 =====

agent.py 是 SoulDance 后端的"大脑"——它不直接做 LLM 推理、不做向量检索、
不管理购物车数据，但它**编排**所有这些组件协同工作。如果把后端比作一个乐团，
agent.py 就是指挥家，LLM/RAG/Cart/Order 是各个乐器组。

===== 核心流程：stream_message =====

用户消息到达后的完整处理链路（每步都是 async generator，通过 yield 输出事件）：

1. 【Session】从 SessionStore 加载或创建 SessionContext（对话记忆）
2. 【Semantic Parse】SemanticParser.parse() → SemanticFrame（意图 + 约束编辑）
   - LLM 路径优先（DoubaoLLMClient.parse_semantic_frame）
   - LLM 不可用 → 规则引擎保底（semantic_layer.rule_semantic_frame）
3. 【Intent Compile】IntentCompiler.compile() → ShoppingIntentIR（购物意图的中间表示）
4. 【Plan】PlannerAgent.plan() → RetrievalPlan（硬约束 + 软偏好 + 检索关键词）
5. 【State Reduce】StateReducer.apply() → 将约束编辑写入 SessionContext
6. 【Retrieve】AdaptiveRetriever.search_async() → 渐进放松 + Hybrid 融合检索
   - 优先走 HybridRetriever（BM25 + 向量 + RRF 融合 + Reranker 重排）
   - 失败回退基础 retriever + 约束放松循环
7. 【Rank】rank_products() → 排序（硬约束过滤 + feedback 加权 + 价格/新品/销量等）
8. 【Format】compose_markdown_sections() → LLM prompt 组装（含商品卡片 + 证据引用）
9. 【LLM Generate】llm_client.chat_completion_streaming() → 逐 token 输出 text_delta
10.【TTS】TTSAdapter.stream_tts() → 文字转语音流式输出 audio_delta
11.【Cart】购物车操作通过 tool_registry 路由，不经过 LLM 生成链路
12.【Order】订单操作通过 /api/order/* REST 端点，由 OrderService 状态机保护

===== 评测开关（C4/A1/A2）=====

这些是长会话评测的实验条件代码名，在 config.py 和 semantic_layer.py 中已详细解释。
简要概括：
- C4（窗口截断 + 结构化快照 + 推荐记忆缓存）：生产默认全开
- A1（禁用窗口截断）：评测模式，LLM 看到全量历史
- A2（禁用结构化快照）：评测模式，LLM 只用原始对话文本

开关通过 settings.eval_disable_window_truncation / eval_disable_structured_snapshot 控制，
在 semantic_context_payload() 中实际生效，不影响 agent.py 的核心流程代码。

===== 与其它模块协作 =====

- main.py：create_app 装配所有组件后注入 ShopGuideAgent
- semantic_layer.py：SemanticParser（LLM+规则混合语义解析）
- intent_compiler.py：IntentCompiler（SemanticFrame → ShoppingIntentIR）
- planner_agent.py：PlannerAgent（LLM 产出 RetrievalPlan）
- state_reducer.py：StateReducer（约束编辑应用到对话状态）
- adaptive_retriever.py：AdaptiveRetriever（渐进放松检索 + Hybrid 融合）
- rag/：HybridRetriever + Reranker（混合检索与重排序）
- ranker.py：rank_products（硬约束过滤 + 多因素排序）
- cart.py：CartService（购物车增删改查 + 幂等 + 检查点）
- order_service.py：OrderService（订单状态机）
- session_store.py：SessionStore（对话记忆持久化）
- feedback_*：FeedbackStore / FeedbackAggregator / FeedbackAwareRanker（反馈闭环）
- memory_cache.py：RecommendationMemoryCache / StructuredMemoryCache
- llm_client.py：LLM 客户端（Doubao/DeepSeek/Fake + 熔断）
- tts_adapter.py / stt_adapter.py：语音交互适配器
"""

from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import AsyncIterator
import json
import re
import uuid

from .adaptive_retriever import AdaptiveRetriever
from .cart import CartService
from .cart_intent import (
    _detect_cart_action,
    _normalize_cart_action,
    _detect_quantity,
    _cart_product_display_name,
    _cart_message,
)
from .comparison_presenter import comparison_item, comparison_reason
from .constraint_filter import canonical_brand, dedupe, extract_excluded_brands, hard_filter
from .utils import extract_json
from .embedding_retriever import BM25OnlyRetriever
from .image_assets import product_image_url_auto as product_image_url
from .knowledge_base import evidence_review_summary, product_evidence
from .intent_compiler import IntentCompiler
from .keywords import (
    CHEAPER_ALTERNATIVE_MARKERS,
    DIFFERENT_BRAND_MARKERS,
    EXPLAIN_FOCUS_MARKERS,
    MORE_EXPENSIVE_ALTERNATIVE_MARKERS,
    PRODUCT_REQUEST_MARKERS,
)
from .messages import insufficient_comparison_products_text, unknown_category_text
from .response_contract import action_message, compose_markdown_sections, no_result_contract_text
from .llm_client import FakeLLMClient
from .memory_cache import RecommendationMemoryCache, RecommendationMemoryHit, StructuredMemoryCache
from .models import (
    ChatRequest,
    ContextEvent,
    DisplayMessage,
    DisplayMessageProduct,
    HardConstraints,
    PendingClarification,
    PendingRecovery,
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
from .timeout_policy import TimeoutBudget, run_with_timeout
from .degradation import fallback_text_for_failure
from .tts_adapter import TTSAdapter


DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS = 12.0


class ShopGuideAgent:
    def __init__(
        self,
        products: list[Product],
        llm_client=None,
        retriever=None,
        session_store: SessionStore | None = None,
        tts_adapter: TTSAdapter | None = None,
        memory_cache: StructuredMemoryCache | None = None,
        recommendation_memory: RecommendationMemoryCache | None = None,
        feedback_ranker=None,
        feedback_store=None,
        user_profile_store=None,
        *,
        hybrid_retriever=None,
        reranker=None,
        settings: object | None = None,
    ):
        self.products = products
        self.product_map = {product.product_id: product for product in products}
        self.llm_client = llm_client or FakeLLMClient()
        self.retriever = retriever or BM25OnlyRetriever(products)
        self.adaptive_retriever = AdaptiveRetriever(self.retriever, hybrid_retriever=hybrid_retriever, reranker=reranker)
        self.sessions = session_store or SessionStore()
        self.planner = PlannerAgent()
        # settings 仅长会话评测专用，production 默认 None → 全部走 C4 全开行为
        self.settings = settings
        self.semantic_parser = SemanticParser(self.llm_client, settings=self.settings)
        self.intent_compiler = IntentCompiler(self.llm_client, self.semantic_parser)
        self.state_reducer = StateReducer()
        self.reference_resolver = ReferenceResolver(self.product_map)
        self.tts = tts_adapter or TTSAdapter()
        self.memory_cache = memory_cache
        self.recommendation_memory = recommendation_memory
        self.taxonomy = TaxonomyResolver.from_products(products)
        self.query_builder = QueryBuilder(self.taxonomy)
        self.feedback_ranker = feedback_ranker
        self.feedback_store = feedback_store
        self.user_profile_store = user_profile_store
        # 长会话评测专用：记录上一轮 cache probe 结果
        self._last_cache_probe: dict = {}
        # 长会话评测专用：记录上一轮 degradation（如 context_overflow_forced_trim）
        self._last_degradation: str | None = None
        self._init_tool_registry()

    def _init_tool_registry(self) -> None:
        from .tools.registry import ToolRegistry
        from .tools.retrieval import RetrieveProductsTool
        from .tools.cart import CartTool
        from .tools.clarify import ClarifyTool
        from .tools.comparison import CompareProductsTool
        from .tools.bundle import ScenarioBundleTool
        from .tools.followup import ProductFollowupTool
        from .tools.small_talk import SmallTalkTool
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(RetrieveProductsTool(self))
        self.tool_registry.register(CartTool(self))
        self.tool_registry.register(ClarifyTool(self))
        self.tool_registry.register(CompareProductsTool(self))
        self.tool_registry.register(ScenarioBundleTool(self))
        self.tool_registry.register(ProductFollowupTool(self))
        self.tool_registry.register(SmallTalkTool(self))

    def _record_feedback(self, session_id: str, signal_type: str, product_id: str = None,
                         action_label: str = None, context: dict = None) -> None:
        """自动记录隐式反馈信号到 FeedbackStore。"""
        if not self.feedback_store:
            return
        from .models import FeedbackEvent
        event = FeedbackEvent(
            session_id=session_id,
            signal_type=signal_type,
            product_id=product_id,
            action_label=action_label,
            context=context or {},
        )
        self.feedback_store.record(event)

    async def plan(self, user_id: str, request: ChatRequest) -> RetrievalPlan:
        context = self.sessions.get(user_id, request.session_id)
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

    async def retrieve_and_rank(self, plan: RetrievalPlan, user_id: str, limit: int = 8, session_id: str = "") -> list[RankedProduct]:
        # memory_cache 存的是"未个性化"的基础排序（cross-session 共享是安全的，因为 key
        # 完全由 plan 内容决定）。命中后必须再走 feedback_ranker 才能注入当前 session 的反馈，
        # 否则会出现"session A 的偏好被 cache 走，session B 拿到 A 的个性化结果"的数据泄漏。
        cached_base: list[RankedProduct] | None = None
        would_hit_b2 = False
        if self.memory_cache and plan.intent in {"recommend_product", "product_followup"}:
            would_hit_b2 = self.memory_cache.probe(plan, self.product_map)
            cached_base = self.memory_cache.get(
                plan,
                self.product_map,
                disable_get=getattr(self.settings, "eval_disable_rank_cache", False),
            )
        self._last_cache_probe["would_hit_b2"] = would_hit_b2
        self._last_cache_probe["effective_hit_b2"] = cached_base is not None
        if self.memory_cache:
            self._last_cache_probe["cache_stats_b2"] = dict(self.memory_cache.stats())

        if cached_base is not None:
            ranked = list(cached_base)
        else:
            retrieved = await self.adaptive_retriever.search_async(plan, top_k=30)
            if retrieved:
                candidates = [product for product, _ in retrieved]
                scores = {product.product_id: score for product, score in retrieved}
            else:
                candidates = self.products
                scores = {}
            ranked = rank_products(
                candidates,
                plan,
                scores,
                limit=limit,
                retrieval_evidence_by_product=getattr(self.adaptive_retriever, "last_evidence_by_product", {}),
            )
            if not ranked and candidates != self.products:
                ranked = rank_products(self.products, plan, {}, limit=limit)
            # cache ? feedback_ranker ?????????????"????"?????
            if self.memory_cache and plan.intent in {"recommend_product", "product_followup"}:
                self.memory_cache.put(plan, ranked)
        # ?????????????? cache????? session ?? apply

        if self.feedback_ranker and session_id:
            ranked = self.feedback_ranker.apply(ranked, session_id)
        return ranked

    async def handle_message(self, user_id: str, request: ChatRequest) -> list[dict]:
        events = [event async for event in self.stream_message(user_id, request)]
        context = self.sessions.get(user_id, request.session_id)
        self._collect_assistant_reply(context, events)
        await self._maybe_update_summary(context)
        return events

    def _collect_assistant_reply(self, context: SessionContext, events: list[dict]) -> None:
        """Collect text_delta events into dialog_turns after stream completes."""
        text_parts = [e.get("text", "") for e in events if e.get("type") == "text_delta"]
        full = "".join(text_parts) if text_parts else "[回复]"
        context.dialog_turns.append({"role": "assistant", "content": full[:2000]})
        # Capacity: keep last 100 messages (50 full turns)
        if len(context.dialog_turns) > 100:
            context.dialog_turns = context.dialog_turns[-100:]

    async def _maybe_update_summary(self, context: SessionContext) -> None:
        """Generate a living summary when dialog grows beyond threshold."""
        turns = context.dialog_turns
        if len(turns) < 16:  # 8 full turns = 16 messages
            return
        last_at = context.compression_state.living_summary.updated_turn
        if len(turns) - last_at < 6:  # at least 3 new turns since last summary
            return
        # Build history text from uncovered turns
        history_lines = []
        for t in turns[last_at:]:
            role = "用户" if t["role"] == "user" else "助手"
            history_lines.append(f"{role}: {t.get('content', '')[:500]}")
        history_text = "\n".join(history_lines)

        summary = await self.llm_client.generate_summary(history_text)
        if not summary:
            return

        ls = context.compression_state.living_summary
        if ls.text:
            ls.text = ls.text + " " + summary
        else:
            ls.text = summary
        ls.covered_part_ids.append(f"{last_at}-{len(turns)}")
        ls.updated_turn = len(turns)
        ls.source_token_count = len(history_text)

    async def compile_intent(self, user_id: str, request: ChatRequest):
        context = self.sessions.get(user_id, request.session_id)
        seed_constraint_state_from_plan(context, context.last_plan)
        return await self.intent_compiler.compile(request, context)

    async def stream_message(self, user_id: str, request: ChatRequest, compiled_ir=None) -> AsyncIterator[dict]:
        context = self.sessions.get(user_id, request.session_id)
        # Append user message to dialog history before processing
        context.dialog_turns.append({"role": "user", "content": request.message or ""})

        # Record user display message
        user_display = DisplayMessage(
            id=_message_id(),
            role="user",
            text=request.message or "",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        context.display_messages.append(user_display)

        collected: list[dict] = []
        async for event in self._do_stream_message(user_id, request, compiled_ir, context):
            collected.append(event)
            yield event

        self._record_display_messages(context, collected)

    async def _do_stream_message(self, user_id: str, request: ChatRequest, compiled_ir, context: SessionContext) -> AsyncIterator[dict]:
        recovery_events = self._build_pending_recovery_events(context, request)
        if recovery_events is not None:
            for event in recovery_events:
                yield event
            return
        seed_constraint_state_from_plan(context, context.last_plan)
        ir = compiled_ir or await self.intent_compiler.compile(request, context)
        if _is_pending_clarification_answer(context, request, ir):
            ir.intent = "recommend_product"
            _apply_pending_answer_preferences(ir, request.message)
        if request.type == "product_followup" or (
            request.type == "user_message"
            and ir.intent == "product_followup"
            and not _is_pending_clarification_answer(context, request, ir)
        ):
            async for event in self.tool_registry.execute(
                "product_followup",
                request,
                context,
                compiled_ir=ir,
                user_id=user_id,
            ):
                yield event
            return
        if ir.intent in {"small_talk", "unclear_input"}:
            async for event in self.tool_registry.execute(
                ir.intent,
                request,
                context,
                user_id=user_id,
            ):
                yield event
            return
        context_action = self._prepare_context_for_turn(context, request, ir)
        self.state_reducer.apply(context, ir, request.message)
        plan = self.query_builder.build(ir, context, request.message)
        self.taxonomy.apply_to_constraints(plan.hard_constraints, request.message)
        plan.category = plan.hard_constraints.sub_category or plan.hard_constraints.category or plan.category
        self._apply_product_admission_gate(plan, request.message)
        # Anchor resolution: "回到第一轮" → bind to first-turn brand
        if plan.soft_preferences.pop("anchor_reference", None) == "first_turn":
            first_brand = context.reference_anchors.get("first_turn_brand")
            if first_brand:
                plan.hard_constraints.include_brands = dedupe(
                    list(plan.hard_constraints.include_brands) + [first_brand]
                )
        context.last_plan = plan
        context.state.trace.last_execution_plan = {"retrieval_plan": plan.model_dump(mode="json")}
        if plan.intent in {"small_talk", "unclear_input"}:
            async for event in self.tool_registry.execute(
                plan.intent,
                request,
                context,
                user_id=user_id,
            ):
                yield event
            return
        if plan.need_clarification or plan.intent == "clarification":
            async for event in self.tool_registry.execute(
                "clarification",
                request,
                context,
                plan=plan,
                context_action=context_action,
                user_id=user_id,
            ):
                yield event
            return
        if plan.intent == "compare_products":
            async for event in self.tool_registry.execute(
                "compare_products",
                request,
                context,
                plan=plan,
                user_id=user_id,
            ):
                yield event
            return
        if plan.intent == "scenario_bundle":
            async for event in self.tool_registry.execute(
                "scenario_bundle",
                request,
                context,
                plan=plan,
                user_id=user_id,
            ):
                yield event
            return
        if _looks_like_product_request(request.message) and not self.taxonomy.is_known_request(request.message):
            message_id = _message_id()
            text = _unknown_category_text(request.message)
            yield self._assistant_state(message_id, "clarifying", "当前商品库没有匹配类目", plan)
            for event in _text_delta_events(message_id, text):
                yield event
            recovery = _filter_recovery_event(message_id, plan)
            _remember_pending_recovery(context, request.message, plan, recovery, "unknown_taxonomy")
            yield recovery
            yield {"type": "done", "message_id": message_id}
            return
        memory_hit = self._get_recommendation_memory_hit(plan, request.message)
        async for event in self.tool_registry.execute(
            "recommend_product",
            request,
            context,
            plan=plan,
            compiled_ir=ir,
            context_action=context_action,
            memory_hit=memory_hit,
            user_id=user_id,
        ):
            yield event

    def _record_display_messages(self, context: SessionContext, events: list[dict]) -> None:
        """Build one assistant DisplayMessage from collected stream events."""
        assistant = DisplayMessage(
            id=_message_id(),
            role="assistant",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        has_content = False
        for event in events:
            etype = event.get("type")
            if etype in {"text_delta", "focus_text_delta"}:
                assistant.text += event.get("text", "")
                has_content = True
            elif etype in {"product_item", "replacement_product"}:
                raw = event.get("product", {})
                if raw:
                    assistant.products.append(DisplayMessageProduct(**raw))
                    has_content = True
            elif etype == "quick_actions":
                assistant.quick_actions = event.get("actions", [])
            elif etype == "cart_update" and event.get("message"):
                assistant.text += ("\n" if assistant.text else "") + event.get("message")
                has_content = True
        if has_content:
            context.display_messages.append(assistant)

    def _build_pending_recovery_events(self, context: SessionContext, request: ChatRequest) -> list[dict] | None:
        pending = context.state.pending_recovery
        if request.type != "user_message" or pending is None:
            return None
        option = _match_pending_recovery_option(pending, request.message)
        if option is None:
            return None
        message_id = _message_id()
        payload = option.get("payload", {}) if isinstance(option.get("payload"), dict) else {}
        action = payload.get("action")
        category = payload.get("category")
        if action == "recover_to_category" and category:
            text = f"可以，我们先不再围绕「{pending.failed_object or pending.failed_query}」硬猜，改看现有的「{category}」方向。"
            plan = RetrievalPlan(
                intent="recommend_product",
                retrieval_mode="single",
                category=str(category),
                hard_constraints=HardConstraints(category=str(category)),
                soft_preferences={},
                retrieval_query=f"{category} 相近商品",
                need_clarification=True,
                clarification_question=f"你想看「{category}」里的哪个具体方向？",
            )
            context.state.pending_recovery = None
            return [
                self._assistant_state(
                    message_id,
                    "clarifying",
                    "根据上次无匹配需求恢复",
                    plan,
                    context_action="recovery",
                ),
                *_text_delta_events(message_id, text + plan.clarification_question),
                {
                    "type": "clarification_request",
                    "message_id": message_id,
                    "question": plan.clarification_question,
                    "options": _clarification_options(plan.clarification_question or ""),
                },
                {"type": "done", "message_id": message_id},
            ]
        text = (
            f"上次「{pending.failed_query}」没有匹配到商品库里的真实类目。"
            "你可以从现有类目里选一个方向，我再继续筛。"
        )
        return [
            self._assistant_state(
                message_id,
                "clarifying",
                "根据上次无匹配需求恢复",
                intent="clarification",
                retrieval_mode="no_retrieval",
                context_action="recovery",
            ),
            *_text_delta_events(message_id, text),
            {"type": "filter_recovery_options", "message_id": message_id, "recovery_id": pending.recovery_id, "options": pending.options},
            {"type": "done", "message_id": message_id},
        ]

    async def _handle_followup(self, user_id: str, request: ChatRequest) -> list[dict]:
        return [event async for event in self._stream_followup(user_id, request)]

    async def _stream_followup(self, user_id: str, request: ChatRequest, ir=None) -> AsyncIterator[dict]:
        context = self.sessions.get(user_id, request.session_id)
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
        resolved_product_id = _resolve_context_product_id(context, request.message)
        # Entity-params fallback: when the user references product attributes
        # ("那个重的", "50ml的") and context cache has matching params
        if not resolved_product_id and context.entity_params:
            resolved_product_id = _resolve_from_entity_params(
                request.message, context.entity_params)
        if resolved_product_id:
            context.focus_product_id = resolved_product_id
            context.state.active_focus.type = "product"
            context.state.active_focus.product_id = resolved_product_id
            context.state.active_focus.source = "context_event"
        focus_product = self.product_map.get(resolved_product_id or request.focus_product_id or context.focus_product_id or "")
        cheaper_than_price = None
        more_expensive_than_price = None
        if focus_product and _wants_cheaper_alternative(request.message, ir):
            cheaper_than_price = focus_product.price
            plan.soft_preferences["price_preference"] = "更便宜"
            context.state.constraint_state.soft["price_preference"] = "更便宜"
        if focus_product and _wants_more_expensive_alternative(request.message, ir):
            more_expensive_than_price = focus_product.price
            plan.soft_preferences["price_preference"] = "更贵"
            context.state.constraint_state.soft["price_preference"] = "更贵"
        explicit_excluded_brands = dedupe(
            extract_excluded_brands(request.message)
            + _catalog_brands_mentioned_for_exclusion(request.message, self.products)
        )
        if focus_product and _wants_different_brand(request.message, ir):
            explicit_excluded_brands.append(canonical_brand(focus_product.brand))
        if explicit_excluded_brands:
            explicit_excluded_brands = dedupe(explicit_excluded_brands)
            excluded_canonical = {canonical_brand(brand) for brand in explicit_excluded_brands}
            plan.hard_constraints.include_brands = [
                brand for brand in plan.hard_constraints.include_brands
                if canonical_brand(brand) not in excluded_canonical
            ]
            plan.hard_constraints.exclude_brands = dedupe(plan.hard_constraints.exclude_brands + explicit_excluded_brands)
            context.state.constraint_state.hard.include_brands = list(plan.hard_constraints.include_brands)
            context.state.constraint_state.hard.exclude_brands = list(plan.hard_constraints.exclude_brands)
            for brand in explicit_excluded_brands:
                context.negative_feedback.append(f"不要品牌:{brand}")
                context.state.user_profile.negative_preferences.append(f"不要品牌:{brand}")
        context.last_plan = plan
        context.state.trace.last_execution_plan = {"retrieval_plan": plan.model_dump(mode="json")}
        message_id = _message_id()
        is_explain_request = bool(focus_product and _is_explain_focus_request(request.message, ir))
        intro = "我来说明刚刚那款商品。" if is_explain_request else _followup_intro(plan)
        label = "正在解释当前商品" if is_explain_request else "正在按当前商品上下文重新筛选"
        phase = "explaining" if is_explain_request else "retrieving"
        yield self._assistant_state(message_id, phase, label, plan, memory_mode="disabled_for_followup")
        for event in _text_delta_events(message_id, intro):
            yield event
        if is_explain_request:
            text = _focus_product_explanation(focus_product, context)
            for event in _text_delta_events(message_id, text):
                yield event
            yield {"type": "focus_done", "message_id": message_id}
            for event in await self.tts.synthesize_events(
                intro + text,
                enabled=request.tts_enabled,
                voice=request.voice,
                message_id=message_id,
            ):
                yield event
            return
        ranked_raw = await self.retrieve_and_rank(plan, user_id=user_id, session_id=request.session_id)
        ranked = [item for item in ranked_raw if hard_filter(item.product, plan.hard_constraints)]
        if cheaper_than_price is not None:
            ranked = [item for item in ranked if item.product.price < cheaper_than_price]
        if more_expensive_than_price is not None:
            ranked = [item for item in ranked if item.product.price > more_expensive_than_price]
        final_selected = ranked[:4]
        if final_selected:
            self._remember_recommendations(context, plan, final_selected)
            context.focus_product_id = final_selected[0].product.product_id
            context.state.active_focus.type = "product"
            context.state.active_focus.product_id = final_selected[0].product.product_id
            context.state.active_focus.source = "followup_primary"
        if final_selected:
            replacement = _product_card(final_selected[0], is_primary=True)
            replacement_event = {
                "type": "replacement_product",
                "message_id": message_id,
                "focus_product_id": request.focus_product_id,
                "reason": final_selected[0].reason,
                "product": replacement.model_dump(mode="json"),
            }
            yield replacement_event
            text_parts: list[str] = []
            async for event in self._stream_generate_text_events(message_id, request, plan, final_selected, focus_product):
                if event.get("type") == "text_delta":
                    text_parts.append(event["text"])
                yield event
            text = "".join(text_parts)
            if request.type == "user_message":
                yield {"type": "products_start", "message_id": message_id, "expected_count": len(final_selected)}
                for index, item in enumerate(final_selected):
                    yield {
                        "type": "product_item",
                        "message_id": message_id,
                        "index": index,
                        "role": "primary" if index == 0 else "alternative",
                        "product": _product_card(item, is_primary=(index == 0)).model_dump(mode="json"),
                    }
                yield {"type": "products_done", "message_id": message_id}
            yield _quick_actions_event(message_id, plan, final_selected)
        else:
            text = _no_match_text(plan)
            for event in _text_delta_events(message_id, text):
                yield event
            yield _filter_recovery_event(message_id, plan)
        yield {"type": "focus_done", "message_id": message_id}
        for event in await self.tts.synthesize_events(
            intro + text,
            enabled=request.tts_enabled,
            voice=request.voice,
            message_id=message_id,
        ):
            yield event

    async def _build_recommendation_events(
        self, user_id: str, request: ChatRequest, plan: RetrievalPlan, ranked: list[RankedProduct]
    ) -> list[dict]:
        return [event async for event in self._stream_recommendation_events(user_id, request, plan, ranked)]

    def _get_recommendation_memory_hit(self, plan: RetrievalPlan, message: str) -> RecommendationMemoryHit | None:
        if not self.recommendation_memory or plan.intent != "recommend_product":
            self._last_cache_probe["would_hit_b1"] = False
            self._last_cache_probe["effective_hit_b1"] = False
            return None
        would_hit_b1 = self.recommendation_memory.probe(plan, message, self.product_map)
        memory_hit = self.recommendation_memory.get(
            plan,
            message,
            self.product_map,
            disable_get=getattr(self.settings, "eval_disable_recommendation_memory", False),
        )
        self._last_cache_probe["would_hit_b1"] = would_hit_b1
        self._last_cache_probe["effective_hit_b1"] = memory_hit is not None
        if self.recommendation_memory:
            self._last_cache_probe["cache_stats_b1"] = dict(self.recommendation_memory.stats())
        return memory_hit

    async def _stream_recommendation_events(
        self,
        user_id: str,
        request: ChatRequest,
        plan: RetrievalPlan,
        ranked: list[RankedProduct],
        context_action: str = "same_task",
        memory_mode: str = "miss",
        selected_override: list[RankedProduct] | None = None,
        cached_summary: str | None = None,
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
            memory_mode=memory_mode,
        )
        for event in _text_delta_events(message_id, intro):
            yield event
        selected = selected_override or await self._select_products(request, plan, ranked)
        yield self._assistant_state(
            message_id,
            "selecting",
            "已完成候选商品决策",
            plan,
            selection_mode="memory_hit" if selected_override is not None else "llm_selection",
            candidate_count=len(ranked),
            selected_count=len(selected),
            context_action=context_action,
            memory_mode=memory_mode,
        )
        if not selected:
            context = self.sessions.get(user_id, request.session_id)
            context.state.pending_clarification = None
            text = _no_match_text(plan)
            for event in _text_delta_events(message_id, text):
                yield event
            recovery = _filter_recovery_event(message_id, plan)
            _remember_pending_recovery(context, request.message, plan, recovery, "no_match")
            yield recovery
            yield {"type": "done", "message_id": message_id}
            for event in await self.tts.synthesize_events(
                intro + text,
                enabled=request.tts_enabled,
                voice=request.voice,
                message_id=message_id,
            ):
                yield event
            return
        context = self.sessions.get(user_id, request.session_id)
        self._remember_recommendations(context, plan, selected)
        if self.recommendation_memory and selected_override is None:
            self.recommendation_memory.put(plan, request.message, selected)
        text_parts: list[str] = []
        if cached_summary:
            for event in _text_delta_events(message_id, cached_summary):
                text_parts.append(event["text"])
                yield event
        else:
            async for event in self._stream_generate_text_events(message_id, request, plan, selected, None):
                if event.get("type") == "text_delta":
                    text_parts.append(event["text"])
                yield event
        text = "".join(text_parts)
        yield {"type": "products_start", "message_id": message_id, "expected_count": len(selected)}
        for index, item in enumerate(selected):
            yield {
                "type": "product_item",
                "message_id": message_id,
                "index": index,
                "role": "primary" if index == 0 else "alternative",
                "product": _product_card(item, is_primary=(index == 0)).model_dump(mode="json"),
            }
        yield {"type": "products_done", "message_id": message_id}
        yield _quick_actions_event(message_id, plan, selected)
        yield {"type": "done", "message_id": message_id}
        for event in await self.tts.synthesize_events(
            intro + text,
            enabled=request.tts_enabled,
            voice=request.voice,
            message_id=message_id,
        ):
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
        max_cards = 4
        try:
            raw = await self.llm_client.select_products(request.message, plan, candidates)
            data = extract_json(raw)
            if data.get("need_clarification") is True or data.get("should_recommend") is False:
                return []
            selected_ids = data.get("selected_product_ids", [])
            reasons = data.get("reasons", {})
            max_cards = data.get("recommended_count", 4)
            max_cards = min(max(1, max_cards), 4)
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
            if len(selected) >= max_cards:
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
        ctx = self.sessions.get("anonymous", request.session_id)
        try:
            text = await self.llm_client.generate_response(request.message, plan, ranked, focus_product, context=ctx)
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
        ctx = self.sessions.get("anonymous", request.session_id)
        try:
            chunks: list[str] = []
            first_chunk = await run_with_timeout(
                self._first_chunk_from_stream(
                    self.llm_client.stream_response(request.message, plan, ranked, focus_product, context=ctx)
                ),
                timeout_seconds=DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS,
                fallback=None,
            )
            if first_chunk is None:
                # timeout before first chunk
                fallback = fallback_text_for_failure("llm_timeout", plan)
                for event in _text_delta_events(message_id, fallback):
                    yield event
                return
            chunks.append(first_chunk)
            async for chunk in self.llm_client.stream_response(request.message, plan, ranked, focus_product, context=ctx):
                if chunk:
                    chunks.append(chunk)
            streamed_text = "".join(chunks)
            if streamed_text and _primary_text_matches_selected(streamed_text, ranked):
                # 幻觉检测
                from .hallucination_checker import HallucinationChecker
                report = HallucinationChecker().verify(streamed_text, ranked)
                if not report.is_clean:
                    text = await FakeLLMClient().generate_response(request.message, plan, ranked, focus_product)
                    yield {"type": "hallucination_corrected", "message_id": message_id, "original_issues": report.fabricated_product_ids + report.fabricated_attributes}
                    for event in _text_delta_events(message_id, text):
                        yield event
                    return
                for chunk in chunks:
                    yield {"type": "text_delta", "message_id": message_id, "text": chunk}
                return
        except Exception:
            pass
        text = await self._safe_generate_text(request, plan, ranked, focus_product)
        if not _primary_text_matches_selected(text, ranked):
            text = await FakeLLMClient().generate_response(request.message, plan, ranked, focus_product)
        for event in _text_delta_events(message_id, text):
            yield event

    async def _first_chunk_from_stream(self, stream):
        async for chunk in stream:
            if chunk:
                return chunk
        return ""

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
        text = compose_markdown_sections(
            [
                ("理解", "我还需要确认一个关键偏好，才能更稳地推荐。"),
                ("下一步", question),
            ]
        )
        events.extend(_text_delta_events(message_id, text))
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

    async def _stream_no_retrieval_events(self, user_id: str, request: ChatRequest, intent: str = "small_talk") -> AsyncIterator[dict]:
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
        # 首块超时 + 后续 chunk 间超时双重保护：避免 LLM 卡死把整条 ws 拖住。
        # 同一个 stream 实例从首块开始一路迭代到底，不重新建 stream，避免 LLM 重复计费/输出重复。
        stream = self.llm_client.stream_chitchat_response(
            request.message, intent, self.sessions.get(user_id, request.session_id)
        )
        got_any_chunk = False
        try:
            async for chunk in _stream_with_first_chunk_timeout(
                stream,
                first_chunk_timeout=DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS,
                chunk_timeout=DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS,
            ):
                if chunk:
                    got_any_chunk = True
                    yield {"type": "text_delta", "message_id": message_id, "text": chunk}
        except Exception:
            pass
        if not got_any_chunk:
            # 流根本没出 chunk（首块超时 / 异常 / 空流）：补静态 fallback
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
        memory_mode: str | None = None,
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
            memory_mode=memory_mode,
        )

    async def _build_comparison_events(
        self, user_id: str, request: ChatRequest, plan: RetrievalPlan | None = None
    ) -> list[dict]:
        context = self.sessions.get(user_id, request.session_id)
        # Resolve named products and fuzzy references from user text first.
        # Fall back to context-event-derived product_ids only when neither is present.
        resolved_ids = _resolve_comparison_named_targets(request.message, self.product_map, context)
        if resolved_ids and len(resolved_ids) >= 2:
            product_ids = resolved_ids
        else:
            product_ids = _resolve_comparison_product_ids(request.message, context)
        products = [self.product_map[product_id] for product_id in product_ids if product_id in self.product_map]
        # Apply price constraints from the current comparison plan even for explicitly named targets,
        # so that requests like "小米手机和华为手机，6000元价位段" compare phones in that band.
        comparison_plan = plan or context.last_plan
        if comparison_plan and comparison_plan.hard_constraints:
            hc = comparison_plan.hard_constraints
            if hc.price_min is not None or hc.price_max is not None:
                products = [
                    p for p in products
                    if (hc.price_min is None or p.price >= hc.price_min)
                    and (hc.price_max is None or p.price <= hc.price_max)
                ]
        # Only apply hard_filter when product IDs came from context events.
        # Explicitly resolved named+fuzzy targets (≥2) should not be gated
        # by a previous turn's price/category constraints — the user named them.
        used_resolved = resolved_ids and len(resolved_ids) >= 2
        if context.last_plan and not used_resolved:
            products = [
                product for product in products
                if product.product_id in context.entity_params
                or hard_filter(product, context.last_plan.hard_constraints)
            ]
        message_id = _message_id()
        if len(products) < 2:
            text = insufficient_comparison_products_text()
            return [
                _assistant_state(message_id, "clarifying", "缺少可对比商品"),
                *_text_delta_events(message_id, text),
                {"type": "done", "message_id": message_id},
            ]
        from .comparison_engine import ComparisonEngine
        engine = ComparisonEngine(self.llm_client)
        try:
            result = await engine.compare(products, request.message)
        except Exception:
            result = engine._fallback_compare(products, request.message)
        winner = self.product_map.get(result.overall_winner) if result.overall_winner else products[0]
        dimension_names = [dim.dimension for dim in result.dimensions]
        comparison = {
            "type": "comparison_result",
            "message_id": message_id,
            "product_ids": result.product_ids,
            "dimensions": dimension_names,
            "structured_dimensions": [dim.model_dump(mode="json") for dim in result.dimensions],
            "overall_winner": result.overall_winner,
            "overall_reason": result.overall_reason,
            "scenario_recommendations": result.scenario_recommendations,
            "items": [comparison_item(product, request.message, dimension_names, comparison_plan) for product in products],
            "recommendation": {
                "product_id": winner.product_id if winner else None,
                "reason": (result.overall_reason or comparison_reason(winner, request.message)) if winner else "",
            },
        }
        understanding = (
            f"我按你这次说的条件筛出 {len(products)} 款来比。"
            if used_resolved
            else f"我把你刚才看的 {len(products)} 款放在一起比。"
        )
        text = compose_markdown_sections(
            [
                ("理解", understanding),
                (
                    "结论",
                    f"如果只选一款，我更建议「{winner.title if winner else products[0].title}」，因为{result.overall_reason or '综合对比'}。",
                ),
                ("下一步", "你可以继续说更便宜、换品牌，或直接围绕胜出款追问。"),
            ]
        )
        _append_context_event(
            context,
            request.message,
            "compare_products",
            "comparison_result",
            {"product_ids": [product.product_id for product in products], "comparison": comparison},
        )
        return [
            _assistant_state(message_id, "comparing", "正在多维度对比商品"),
            *_text_delta_events(message_id, text),
            comparison,
            _quick_actions_event(message_id, comparison_plan or _default_plan(request.message), []),
            {"type": "done", "message_id": message_id},
        ]

    async def _build_bundle_events(self, user_id: str, request: ChatRequest, plan: RetrievalPlan) -> list[dict]:
        context = self.sessions.get(user_id, request.session_id)
        message_id = _message_id()
        bundle_id = "bundle_" + uuid.uuid4().hex[:8]
        slots = [
            ("防晒护理", "防晒霜", "防晒 海边 三亚 防水 清爽"),
            ("穿搭", "速干T恤", "三亚 海边 轻便 速干 衣服"),
            ("出行配件", "帽子", "海边 遮阳 防晒 轻便 帽子"),
        ]
        events: list[dict] = [_assistant_state(message_id, "retrieving", "正在拆解场景组合需求")]
        bundle_intro = compose_markdown_sections(
            [
                ("理解", "我会按三亚海边的强紫外线、轻便出行和降温舒适来拆成几组搭配。"),
                ("结论", "先拆成防晒护理、穿搭和出行配件三组。"),
                ("下一步", "你可以查看每组商品，也可以把整套组合加入购物车。"),
            ]
        )
        events.extend(_text_delta_events(message_id, bundle_intro))
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
            ranked = await self.retrieve_and_rank(slot_plan, user_id=user_id, session_id=request.session_id)
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

    def handle_cart_message(self, user_id: str, request: ChatRequest, cart: CartService) -> dict:
        context = self.sessions.get(user_id, request.session_id)
        action = _normalize_cart_action(request.action or _detect_cart_action(request.message))
        product_id = request.product_id or _resolve_cart_product_id(request.message, context, cart.get(user_id, request.session_id))
        quantity = request.quantity
        detected_quantity = _detect_quantity(request.message)
        if detected_quantity is not None:
            quantity = detected_quantity
        if action == "clear_cart":
            snapshot = cart.clear(user_id, request.session_id)
            context.recent_cart_product_id = None
            context.state.cart_memory.recent_product_id = None
            return {"action": action, "product_id": None, "cart": snapshot, "success": True, "message": _cart_message(action, "")}
        if action == "get_cart":
            snapshot = cart.get(user_id, request.session_id)
            return {"action": action, "product_id": None, "cart": snapshot, "success": True, "message": "这是当前购物车。"}
        if action == "checkout":
            snapshot = cart.checkout(user_id, request.session_id)
            return {"action": action, "product_id": product_id, "cart": snapshot, "message": "已为你模拟下单。"}
        if not product_id:
            snapshot = cart.get(user_id, request.session_id)
            return {"action": "get_cart", "product_id": None, "cart": snapshot, "message": "我还没找到要操作的商品。"}
        if action == "update_quantity":
            snapshot = cart.update_quantity(user_id, request.session_id, product_id, quantity)
        elif action == "remove":
            snapshot = cart.remove(user_id, request.session_id, product_id)
        else:
            action = "add_to_cart"
            snapshot = cart.add(user_id, request.session_id, product_id, quantity)
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
        context.state.pending_recovery = None
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

        # If this is a cheaper alternative follow-up, save the anchor
        if (
            plan.intent == "product_followup"
            and plan.soft_preferences.get("price_preference") == "更便宜"
            and ranked
        ):
            context.reference_anchors["last_cheaper_alternative"] = ranked[0].product.product_id
        # Store first-turn anchor for long-session references
        if "first_turn_brand" not in context.reference_anchors and ranked:
            primary = ranked[0].product
            context.reference_anchors["first_turn_brand"] = primary.brand
            context.reference_anchors["first_turn_category"] = primary.category
            context.reference_anchors["first_turn_sub_category"] = primary.sub_category
            context.reference_anchors["first_turn_product_ids"] = json.dumps(
                [item.product.product_id for item in ranked],
                ensure_ascii=False,
            )
        # Cache product parameters for future reference
        for item in ranked:
            pid = item.product.product_id
            if pid not in context.entity_params:
                context.entity_params[pid] = {
                    "price": item.product.price,
                    "brand": item.product.brand,
                    "category": item.product.category,
                    "sub_category": item.product.sub_category,
                }
                context.entity_params_order.append(pid)
        # LRU eviction: keep last 50
        while len(context.entity_params_order) > 50:
            oldest = context.entity_params_order.pop(0)
            context.entity_params.pop(oldest, None)

        # Track shopping domain
        if plan.hard_constraints.category:
            context.state.constraint_state.current_domain = plan.hard_constraints.category

        _append_context_event(
            context,
            plan.retrieval_query,
            plan.intent,
            "recommendation_set",
            {
                "set_id": context.state.recommendation_memory.last_set_id,
                "plan": plan.model_dump(mode="json"),
                "product_ids": [item.product.product_id for item in ranked],
                "products": list(context.last_recommendations),
            },
        )
        _update_profile(context, plan)

    async def try_handle_cart_message(self, user_id: str, request: ChatRequest, cart: CartService, compiled_ir=None) -> dict | None:
        context = self.sessions.get(user_id, request.session_id)
        frame = compiled_ir or await self.intent_compiler.compile(request, context)
        if compiled_ir is None and (frame.intent != "cart_operation" or frame.cart_operation is None):
            frame = rule_semantic_frame(request)
        if frame.intent != "cart_operation" or frame.cart_operation is None:
            return None
        action = _normalize_cart_action(frame.cart_operation.action)
        quantity = max(frame.cart_operation.quantity, 0)
        product_id = None
        if action in {"get_cart", "clear_cart", "checkout"}:
            return self._execute_cart_action(user_id, request.session_id, action, None, quantity, cart)
        if action == "update_sku":
            if not product_id:
                resolution = self.reference_resolver.resolve(
                    frame.cart_operation.target,
                    context,
                    cart.get(user_id, request.session_id),
                )
                product_id = resolution.product_id
            return self._handle_update_sku(user_id, request.session_id, product_id, request.message, cart)
        has_named_product_hint = False
        if action in {"add_to_cart", "update_quantity"}:
            has_named_product_hint = _has_explicit_product_hint(request.message, self.products)
            product_id = self._resolve_product_mention_for_cart(request.message)
            if not product_id and has_named_product_hint:
                return self._named_product_not_resolved_event(user_id, request.session_id, action, request.message, cart)
        if not product_id:
            resolution = self.reference_resolver.resolve(
                frame.cart_operation.target,
                context,
                cart.get(user_id, request.session_id),
            )
            product_id = resolution.product_id
        return self._execute_cart_action(user_id, request.session_id, action, product_id, quantity, cart)

    def _resolve_product_mention_for_cart(self, message: str) -> str | None:
        scored = self._cart_product_candidates(message)
        if not scored:
            return None

        scored.sort(reverse=True)
        best_score, _, best_product_id = scored[0]
        if best_score < 80:
            return None
        if len(scored) > 1 and best_score == scored[1][0]:
            return None
        return best_product_id

    def _cart_product_candidates(self, message: str) -> list[tuple[int, float, str]]:
        message_text = _normalize_product_match_text(message)
        if not message_text:
            return []

        unique_brand_product_ids = _unique_brand_product_ids_for_message(message_text, self.products)
        scored: list[tuple[int, float, str]] = []
        for product in self.products:
            score = _product_mention_score(message_text, product)
            if product.product_id in unique_brand_product_ids:
                score += 100
            if score <= 0:
                continue
            scored.append((score, -product.price, product.product_id))
        scored.sort(reverse=True)
        return scored

    def _named_product_not_resolved_event(
        self,
        user_id: str,
        session_id: str,
        action: str,
        message: str,
        cart: CartService,
    ) -> dict:
        candidates = [
            self.product_map[product_id]
            for _, _, product_id in self._cart_product_candidates(message)[:3]
            if product_id in self.product_map
        ]
        candidate_payload = [
            {
                "product_id": product.product_id,
                "name": product.title,
                "brand": product.brand,
                "price": product.price,
            }
            for product in candidates
        ]
        if len(candidates) > 1:
            names = "、".join(product.title for product in candidates[:3])
            text = action_message(f"我找到了多个可能的商品：{names}。请说完整型号，或点商品卡片上的加购按钮。")
        elif candidates:
            text = action_message(f"我找到了一个可能的商品：{candidates[0].title}。请说完整型号，或点商品卡片上的加购按钮。")
        else:
            text = action_message("我还没找到明确要加入购物车的商品。请说完整品牌和型号，或点商品卡片上的加购按钮。")
        return {
            "action": action,
            "product_id": None,
            "cart": cart.get(user_id, session_id),
            "success": False,
            "reason": "named_product_not_resolved",
            "candidates": candidate_payload,
            "message": text,
        }

    def _handle_update_sku(
        self,
        user_id: str,
        session_id: str,
        product_id: str | None,
        message: str,
        cart: CartService,
    ) -> dict:
        """Resolve SKU selection from a natural-language expression and apply it."""
        if not product_id:
            snapshot = cart.get(user_id, session_id)
            return {
                "action": "update_sku",
                "product_id": None,
                "cart": snapshot,
                "success": False,
                "message": "我没找到要切换规格的商品。请先把它加入购物车，或告诉我商品名称。",
            }
        # Extract SKU property value: e.g. "50ml" from "换成 50ml 的"
        sku_match = re.search(r"(\d+ml)", message or "")
        if not sku_match:
            product = cart.products.get(product_id)
            options = [
                ", ".join(f"{k}: {v}" for k, v in sku.properties.items())
                for sku in (product.skus if product else [])
            ]
            snapshot = cart.get(user_id, session_id)
            return {
                "action": "update_sku",
                "product_id": product_id,
                "cart": snapshot,
                "success": False,
                "message": f"我没找到规格参数。可选规格有：{'；'.join(options)}" if options else "该商品暂无可选规格。",
                "candidates": options,
            }
        property_value = sku_match.group(1).strip()
        try:
            snapshot = cart.update_sku(user_id, session_id, product_id, property_value)
            return {
                "action": "update_sku",
                "product_id": product_id,
                "cart": snapshot,
                "success": True,
                "message": f"已切换到 {property_value} 规格。",
            }
        except ValueError as exc:
            snapshot = cart.get(user_id, session_id)
            product = cart.products.get(product_id)
            options = [
                ", ".join(f"{k}: {v}" for k, v in sku.properties.items())
                for sku in (product.skus if product else [])
            ]
            return {
                "action": "update_sku",
                "product_id": product_id,
                "cart": snapshot,
                "success": False,
                "message": str(exc),
                "candidates": options,
            }

    def execute_cart_action(
        self,
        user_id: str,
        session_id: str,
        action: str,
        product_id: str | None,
        quantity: int,
        cart: CartService,
    ) -> dict:
        return self._execute_cart_action(user_id, session_id, action, product_id, quantity, cart)

    def _execute_cart_action(
        self,
        user_id: str,
        session_id: str,
        action: str,
        product_id: str | None,
        quantity: int,
        cart: CartService,
    ) -> dict:
        action = _normalize_cart_action(action)
        context = self.sessions.get(user_id, session_id)
        if action == "get_cart":
            snapshot = cart.get(user_id, session_id)
            return {
                "action": action,
                "product_id": None,
                "cart": snapshot,
                "success": True,
                "message": "这是当前购物车。",
            }
        if action == "clear_cart":
            snapshot = cart.clear(user_id, session_id)
            context.recent_cart_product_id = None
            context.state.cart_memory.recent_product_id = None
            return {
                "action": action,
                "product_id": None,
                "cart": snapshot,
                "success": True,
                "message": _cart_message(action, ""),
            }
        if action == "checkout":
            current = cart.get(user_id, session_id)
            if not current.get("items"):
                return {
                    "action": action,
                    "product_id": product_id,
                    "cart": current,
                    "success": False,
                    "message": "购物车为空，无法结算。",
                }
            snapshot = cart.checkout(user_id, session_id)
            return {
                "action": action,
                "product_id": product_id,
                "cart": snapshot,
                "success": True,
                "message": "已为你模拟下单。",
            }
        if not product_id:
            snapshot = cart.get(user_id, session_id)
            return {"action": "get_cart", "product_id": None, "cart": snapshot, "message": action_message("我还没找到要操作的商品。")}
        if action == "update_quantity":
            snapshot = cart.update_quantity(user_id, session_id, product_id, quantity)
        elif action == "remove":
            snapshot = cart.remove(user_id, session_id, product_id)
        else:
            action = "add_to_cart"
            snapshot = cart.add(user_id, session_id, product_id, quantity)
        context.recent_cart_product_id = product_id
        context.state.cart_memory.recent_product_id = product_id
        return {
            "action": action,
            "product_id": product_id,
            "cart": snapshot,
            "success": True,
            "message": _cart_message(action, _cart_product_display_name(cart, product_id)),
        }

    @staticmethod
    def _estimate_tokens(payload: dict) -> int:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(json.dumps(payload, ensure_ascii=False)))
        except Exception:
            # 兜底：粗估 1 token ≈ 1.6 char（中文场景）
            return int(len(json.dumps(payload, ensure_ascii=False)) / 1.6)

    def _maybe_force_trim_context(
        self,
        payload: dict,
        *,
        budget: int,
    ) -> tuple[dict, str | None]:
        """若 payload tokens 超 budget，逐步截断 recent_context.recent_user_turns / last_events 的尾部直到 ≤budget。
        返回 (trimmed_payload, degradation_label 或 None)。
        仅在 eval_disable_window_truncation=True 时有意义；A1 默认行为下窗口已经截好，几乎不会触发。
        """
        if not payload:
            return payload, None
        current = self._estimate_tokens(payload)
        if current <= budget:
            return payload, None
        trimmed = json.loads(json.dumps(payload))  # deep copy
        rc = trimmed.get("recent_context", {})
        # 逐步从最早的 turn 开始砍
        for key in ("recent_user_turns", "last_events", "recent_recommendation_sets"):
            while rc.get(key) and self._estimate_tokens(trimmed) > budget:
                rc[key].pop(0)  # 砍最早的
        return trimmed, "context_overflow_forced_trim"


def _normalize_product_match_text(text: str | None) -> str:
    return re.sub(r"[\s,，。！？!?:：；;、（）()【】\[\]\"'“”‘’]+", "", (text or "").lower())


def _extract_target_sub_category(text: str) -> str | None:
    mapping = {
        "手机": "智能手机",
        "平板": "平板电脑",
        "笔记本": "笔记本电脑",
        "电脑": "笔记本电脑",
        "精华": "精华",
        "防晒": "防晒霜",
        "咖啡": "咖啡",
        "耳机": "耳机",
        "跑鞋": "跑鞋",
    }
    for key, value in mapping.items():
        if key in text:
            return value
    return None


def _extract_price_band(text: str) -> tuple[float | None, float | None]:
    import re
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)?\s*价位段", text)
    if match:
        center = float(match.group(1))
        # "6000元价位段" → compare products around 6000, ±1000
        return max(0.0, center - 1000), center + 1000
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)?\s*左右", text)
    if match:
        center = float(match.group(1))
        return max(0.0, center - 1000), center + 1000
    return None, None


def _has_explicit_product_hint(message: str, products: list[Product]) -> bool:
    message_text = _normalize_product_match_text(message)
    if not message_text:
        return False
    for product in products:
        brand = _normalize_product_match_text(product.brand)
        if brand and brand in message_text:
            return True
        if any(alias in message_text for alias in _product_model_aliases(product)):
            return True
    return False


def _unique_brand_product_ids_for_message(message_text: str, products: list[Product]) -> set[str]:
    products_by_brand: dict[str, list[Product]] = {}
    for product in products:
        brand = _normalize_product_match_text(product.brand)
        if not brand:
            continue
        products_by_brand.setdefault(brand, []).append(product)
    return {
        items[0].product_id
        for brand, items in products_by_brand.items()
        if len(items) == 1 and brand in message_text
    }


def _catalog_brands_mentioned_for_exclusion(message: str, products: list[Product]) -> list[str]:
    if not re.search(r"不要|不考虑|排除|避开|除了|别|非", message or ""):
        return []
    message_text = _normalize_product_match_text(message)
    brands: list[str] = []
    seen_raw: set[str] = set()
    for product in products:
        brand = (product.brand or "").strip()
        if not brand or brand in seen_raw:
            continue
        seen_raw.add(brand)
        normalized = _normalize_product_match_text(brand)
        if normalized and normalized in message_text:
            brands.append(canonical_brand(brand))
    return dedupe(brands)


def _product_mention_score(message_text: str, product: Product) -> int:
    title = _normalize_product_match_text(product.title)
    brand = _normalize_product_match_text(product.brand)
    category = _normalize_product_match_text(product.category)
    sub_category = _normalize_product_match_text(product.sub_category)
    search_text = _normalize_product_match_text(product.search_text)
    aliases = _product_model_aliases(product)
    short_aliases = _product_short_name_aliases(product)

    score = 0
    if brand and brand in message_text:
        score += 45
    if sub_category and sub_category in message_text:
        score += 35
    if category and category in message_text:
        score += 10
    brand_subcategory = f"{brand}{sub_category}"
    if brand_subcategory and brand_subcategory in message_text and brand_subcategory in title:
        score += 65
    alias_hits = [alias for alias in aliases if alias in message_text]
    if alias_hits:
        score += 120 + min(max(len(alias) for alias in alias_hits), 40)
    short_alias_hits = [alias for alias in short_aliases if alias in message_text]
    if short_alias_hits:
        score += 140 + min(max(len(alias) for alias in short_alias_hits), 40)
    if title and title in message_text:
        score += 160
    if title and message_text in title:
        score += 60
    for token in [brand_subcategory, brand, sub_category]:
        if token and token in message_text and token in search_text:
            score += 10

    # Do not resolve on a generic category/sub-category alone.
    if short_alias_hits:
        return score
    if alias_hits:
        return score
    if title and title in message_text:
        return score
    if brand and brand in message_text:
        return score
    if brand_subcategory and brand_subcategory in message_text:
        return score
    return 0


def _product_short_name_aliases(product: Product) -> set[str]:
    title = (product.title or "").strip()
    if not title:
        return set()
    brand = _normalize_product_match_text(product.brand)
    aliases: set[str] = set()
    first_segment = _normalize_product_match_text(re.split(r"\s+", title, maxsplit=1)[0])
    if len(first_segment) >= 4:
        aliases.add(first_segment)

    tokens = [
        _normalize_product_match_text(token)
        for token in re.findall(r"[A-Za-z]+|\d+|[\u4e00-\u9fff]+", title)
    ]
    tokens = [token for token in tokens if token]
    if brand and tokens and tokens[0] == brand and len(tokens) > 1:
        brand_phrase = f"{brand}{tokens[1]}"
        if len(brand_phrase) >= 4:
            aliases.add(brand_phrase)
    return aliases


def _product_model_aliases(product: Product) -> set[str]:
    tokens = [
        _normalize_product_match_text(token)
        for token in re.findall(r"[A-Za-z]+|\d+|[\u4e00-\u9fff]+", product.title or "")
    ]
    tokens = [token for token in tokens if token]
    aliases: set[str] = set()
    for start in (0, 1):
        max_end = min(len(tokens), start + 6)
        for end in range(start + 2, max_end + 1):
            alias = "".join(tokens[start:end])
            if len(alias) >= 4 and re.search(r"[a-z0-9]", alias):
                aliases.add(alias)
    brand = _normalize_product_match_text(product.brand)
    if brand:
        for alias in list(aliases):
            if alias.startswith(brand) or len(alias) < 4:
                continue
            aliases.add(f"{brand}{alias}")
    return aliases


def _primary_text_matches_selected(text: str, ranked: list[RankedProduct]) -> bool:
    if not text or not ranked:
        return True
    primary_title = ranked[0].product.title
    alternative_titles = [item.product.title for item in ranked[1:4]]
    primary_markers = ["主推", "优先推荐", "优先看"]
    for title in alternative_titles:
        for marker in primary_markers:
            if f"{marker}{title}" in text or f"{marker}「{title}」" in text or f"{marker}商品为{title}" in text:
                return False
    if any(marker in text for marker in primary_markers) and not any(
        f"{marker}{primary_title}" in text or f"{marker}「{primary_title}」" in text or f"{marker}商品为{primary_title}" in text
        for marker in primary_markers
    ):
        return not any(title in text for title in alternative_titles)
    return True


def _product_card(item: RankedProduct, is_primary: bool = False) -> ProductCard:
    product = item.product
    tags = _product_dynamic_tags(product)
    review_summary = evidence_review_summary(product, tags)
    img = product_image_url(product.image_path)
    return ProductCard(
        product_id=product.product_id,
        name=product.title,
        brand=product.brand,
        category=product.category,
        sub_category=product.sub_category,
        price=product.price,
        main_image_url=img,
        image_url=img,                      # Android 兼容
        tags=tags,
        reason=item.reason,
        is_primary=is_primary,
        derived_attributes={
            "generated_tags": [
                {
                    "value": tag,
                    "evidence": "title/sub_category/brand/review",
                    "confidence": 1.0,
                }
                for tag in tags
            ],
        },
        positive_feedback_summary=[
            review_summary["positive_summary"],
        ] if review_summary.get("positive_summary") else [],
        negative_feedback_summary=[
            review_summary["negative_summary"],
        ] if review_summary.get("negative_summary") else [],
        risk_tags=_product_risk_tags(product),
    )


def _product_dynamic_tags(product: Product) -> list[str]:
    title = product.title or ""
    text = f"{title} {product.marketing_description} {product.search_text}"
    keyword_candidates = [
        "三合一",
        "速溶",
        "冻干",
        "黑咖啡",
        "无糖",
        "低糖",
        "拍照",
        "快充",
        "轻薄",
        "高刷",
        "防晒",
        "保湿",
        "修护",
        "清爽",
        "通勤",
        "跑步",
        "速干",
        "防水",
    ]
    candidates = [
        *product.extracted_terms,
        product.brand,
        product.sub_category,
        *[keyword for keyword in keyword_candidates if keyword in text],
    ]
    return dedupe([tag for tag in candidates if tag and tag != "未知"])[:4]


def _product_risk_tags(product: Product) -> list[str]:
    risks: list[str] = []
    for review in product.reviews[:8]:
        content = str(review.get("content", ""))
        rating = float(review.get("rating", 0) or 0)
        if rating <= 2 and content:
            risks.append(content[:24])
    return risks[:2]


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
    memory_mode: str | None = None,
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
    if memory_mode:
        event["memory_mode"] = memory_mode
    return event


def _append_context_event(
    context: SessionContext,
    user_message: str,
    assistant_intent: str,
    result_type: str,
    payload: dict,
) -> None:
    event = ContextEvent(
        event_id="ctx_" + uuid.uuid4().hex[:8],
        turn_index=context.state.dialog_state.turn_index,
        user_message=user_message,
        assistant_intent=assistant_intent,
        result_type=result_type,
        payload=payload,
    )
    context.state.context_events.append(event)
    context.state.context_events = context.state.context_events[-12:]


def _remember_pending_recovery(
    context: SessionContext,
    failed_query: str,
    plan: RetrievalPlan,
    recovery_event: dict,
    reason: str,
) -> None:
    options = list(recovery_event.get("options", []))
    recovery_id = str(recovery_event.get("recovery_id") or ("recovery_" + uuid.uuid4().hex[:8]))
    failed_object = _guess_failed_object(failed_query)
    context.state.pending_recovery = PendingRecovery(
        recovery_id=recovery_id,
        failed_query=failed_query,
        failed_object=failed_object,
        reason=reason,
        options=options,
    )
    _append_context_event(
        context,
        failed_query,
        plan.intent,
        "pending_recovery",
        {
            "recovery_id": recovery_id,
            "failed_query": failed_query,
            "failed_object": failed_object,
            "reason": reason,
            "options": options,
            "plan": plan.model_dump(mode="json"),
        },
    )


def _match_pending_recovery_option(pending: PendingRecovery, message: str) -> dict | None:
    normalized = _normalize_message(message)
    for option in pending.options:
        if normalized in {_normalize_message(str(option.get("message", ""))), _normalize_message(str(option.get("label", "")))}:
            return option
        payload = option.get("payload", {}) if isinstance(option.get("payload"), dict) else {}
        category = str(payload.get("category", ""))
        if category and category in message:
            return option
    if any(token in message for token in ["相近需求", "重新筛", "换一个相近", "换个相近"]):
        for option in pending.options:
            payload = option.get("payload", {}) if isinstance(option.get("payload"), dict) else {}
            if payload.get("action") == "choose_existing_category":
                return option
        return pending.options[0] if pending.options else {}
    return None


def _resolve_context_product_id(context: SessionContext, message: str) -> str | None:
    recommendation_events = [
        event for event in context.state.context_events if event.result_type == "recommendation_set"
    ]
    if not recommendation_events:
        return None
    if any(marker in message for marker in ["上上轮", "上上个", "倒数第二"]):
        target = recommendation_events[-2] if len(recommendation_events) >= 2 else None
    elif any(marker in message for marker in ["上一轮", "上一个", "上一组"]):
        target = recommendation_events[-1]
    elif any(marker in message for marker in ["刚刚", "刚才", "这个", "那款"]):
        target = recommendation_events[-1]
    else:
        return None
    if target is None:
        return None
    product_ids = list(target.payload.get("product_ids", []))
    if not product_ids:
        return None
    index = _reference_index_from_text(message)
    if index is not None and 0 <= index < len(product_ids):
        return str(product_ids[index])
    return str(product_ids[0])


def _resolve_from_entity_params(text: str, entity_params: dict[str, dict[str, Any]]) -> str | None:
    """Match user attribute references against cached entity params.

    When a follow-up message mentions a product attribute (e.g."那个重的",
    "50ml的"), scans entity_params for matching values and returns the
    first product_id whose cached attributes appear in the text.
    """
    for pid, attrs in entity_params.items():
        for value in attrs.values():
            if isinstance(value, (str, int, float)) and str(value) in text:
                return pid
    return None


def _reference_index_from_text(text: str) -> int | None:
    markers = {
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
    for marker, index in markers.items():
        if marker in text:
            return index
    return None


def _guess_failed_object(text: str) -> str | None:
    cleaned = re.sub(r"^(我想要|我想买|想要|想买|推荐|找|买|有没有|给我)", "", text or "").strip()
    cleaned = re.sub(r"[，。！？、,.!?].*$", "", cleaned).strip()
    return cleaned or None


def _normalize_message(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def _reset_shopping_task(context: SessionContext) -> None:
    context.state.constraint_state.hard = HardConstraints()
    context.state.constraint_state.soft = {}
    context.state.pending_clarification = None
    context.state.pending_recovery = None
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
    context.state.recommendation_memory.items.clear()
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
    return bool(re.search(r"预算|以内|以下|拍照|续航|性价比|性能|轻薄|便携|清爽|温和|保湿|修护|惊喜|稳妥|不踩雷|实用", message or ""))


def _is_pending_clarification_answer(context: SessionContext, request: ChatRequest, ir) -> bool:
    if request.type != "user_message" or context.state.pending_clarification is None:
        return False
    if ir.intent not in {"unclear_input", "recommend_product", "clarification", "product_followup"}:
        return False
    return _looks_like_clarification_answer(request.message, ir)


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
    if "惊喜" in message:
        soft["gift_style"] = "惊喜感"
    if "稳妥" in message or "不踩雷" in message:
        soft["gift_style"] = "稳妥不踩雷"
    if "实用" in message:
        soft["gift_style"] = "实用"


def _llm_mode(llm_client) -> str:
    if isinstance(llm_client, FakeLLMClient):
        return "fake"
    return "doubao"


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
        or constraints.price_min is not None
        or constraints.price_max is not None
        or constraints.exclude_terms
        or constraints.include_brands
        or constraints.exclude_brands
        or constraints.exclude_brand_regions
        or plan.soft_preferences
    ):
        return True
    if taxonomy.resolve(message):
        return True
    if constraints.category or constraints.sub_category:
        return True
    if constraints.price_min is not None or constraints.price_max is not None or constraints.exclude_terms or constraints.include_brands or constraints.exclude_brands or constraints.exclude_brand_regions:
        return True
    if plan.soft_preferences:
        return True
    return bool(
        re.search(
            r"推荐|找|买|想要|想买|我要|要一|要个|来一|来瓶|来个|拿一|看看|有没有|预算|以内|以下|不要|不含|排除|对比|比较|哪个更|购物车|加购|加入|下单|结算|"
            r"防晒|精华|护肤|美妆|化妆|化妆品|彩妆|手机|笔记本|电脑|耳机|跑鞋|鞋|衣服|背包|咖啡|饮料|食品|零食|特饮|功能饮料|能量饮料|礼物|送人|送给",
            message or "",
            flags=re.I,
        )
    )


def _understanding_text(plan: RetrievalPlan) -> str:
    return ""


def _followup_intro(plan: RetrievalPlan) -> str:
    constraints = plan.hard_constraints
    parts: list[str] = []
    if plan.soft_preferences.get("price_preference") == "更便宜":
        parts.append("找比当前主推更便宜的")
    if plan.soft_preferences.get("price_preference") == "更贵":
        parts.append("找比当前主推更贵一点的")
    if constraints.price_min is not None:
        parts.append(f"保留 {constraints.price_min:.0f} 元以上")
    if constraints.price_max is not None:
        parts.append(f"保留预算 {constraints.price_max:.0f} 元以内")
    if constraints.include_brands:
        parts.append("保留品牌" + "、".join(constraints.include_brands))
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
    recovery_id = "recovery_" + uuid.uuid4().hex[:8]
    if constraints.price_max is not None:
        relaxed = max(constraints.price_max * 2, 100)
        options.append(
            {
                "label": f"放宽预算到 {relaxed:.0f} 元",
                "message": f"预算放宽到{relaxed:.0f}元以内",
                "payload": {"recovery_id": recovery_id, "action": "relax_budget", "price_max": relaxed},
            }
        )
    if constraints.exclude_terms:
        options.append(
            {
                "label": "保留排除项，换相近类目",
                "message": "保留这些排除要求，换一个相近类目看看",
                "payload": {"recovery_id": recovery_id, "action": "choose_existing_category"},
            }
        )
    if constraints.exclude_brand_regions:
        options.append(
            {
                "label": "只保留非日系要求",
                "message": "先保留非日系要求，其他条件可以放宽",
                "payload": {"recovery_id": recovery_id, "action": "relax_to_region_only"},
            }
        )
    if not options:
        options.extend(
            [
                {
                    "label": "换个相近需求",
                    "message": "换个相近需求重新筛",
                    "payload": {"recovery_id": recovery_id, "action": "choose_existing_category"},
                },
                {
                    "label": "看看数码电子",
                    "message": "看看数码电子里的相近商品",
                    "payload": {"recovery_id": recovery_id, "action": "recover_to_category", "category": "数码电子"},
                },
                {
                    "label": "看看服饰运动",
                    "message": "看看服饰运动里的相近商品",
                    "payload": {"recovery_id": recovery_id, "action": "recover_to_category", "category": "服饰运动"},
                },
                {
                    "label": "看看美妆护肤",
                    "message": "看看美妆护肤里的相近商品",
                    "payload": {"recovery_id": recovery_id, "action": "recover_to_category", "category": "美妆护肤"},
                },
            ]
        )
    return {"type": "filter_recovery_options", "message_id": message_id, "recovery_id": recovery_id, "options": options}



def _resolve_comparison_named_targets(text: str, product_map: dict, context: SessionContext) -> list[str]:
    """Resolve named products and fuzzy deictic references in comparison text.

    Returns explicit product_ids when the user mentions a named product
    (brand + title keyword match) or a fuzzy reference (e.g. "刚才那个便宜的").
    Returns an empty list when neither is found — the caller should fall back
    to ``_resolve_comparison_product_ids``.
    """
    ids: list[str] = []

    # Infer target sub_category and price band from explicit cues in the request.
    target_sub_cat = _extract_target_sub_category(text)
    price_min, price_max = _extract_price_band(text)

    # ── fuzzy deictic references → anchor lookup ──
    _FUZZY_MARKERS: list[tuple[str, str]] = [
        ("刚才那个便宜的", "last_cheaper_alternative"),
        ("刚刚那个便宜的", "last_cheaper_alternative"),
        ("那个便宜的", "last_cheaper_alternative"),
        ("那个平替", "last_cheaper_alternative"),
    ]
    for marker, anchor_key in _FUZZY_MARKERS:
        if marker in text:
            anchor_id = context.reference_anchors.get(anchor_key)
            if anchor_id and anchor_id in product_map:
                ids.append(anchor_id)
            break

    # ── named product → scored by _product_mention_score ──
    # Replace brute-force n-gram matching with the existing hierarchical
    # scorer used by the cart path.
    normalized = _normalize_product_match_text(text)
    if normalized:
        # Fast path: brands with exactly one product — mentioning the brand
        # name alone is sufficient.
        unique_pids = _unique_brand_product_ids_for_message(normalized, list(product_map.values()))
        for pid in unique_pids:
            if pid not in ids and pid in product_map:
                ids.append(pid)

        # Infer the expected sub_category from any fuzzy-deictic anchor product
        # already resolved (e.g. "刚才那个便宜的" → p_beauty_018 → 精华).
        # This prevents a brand-only match from capturing unrelated products
        # of the same brand (e.g. 雅诗兰黛粉底液 when the user is in a 精华 flow).
        anchor_sub_cat: str | None = None
        for anchor_id in ids:
            anchor = product_map.get(anchor_id)
            if anchor is not None:
                anchor_sub_cat = _normalize_product_match_text(anchor.sub_category)
                break

        # Combine anchor-derived sub_category with explicit target sub_category.
        effective_sub_cat = anchor_sub_cat or target_sub_cat

        scored: list[tuple[int, str]] = []
        for pid, product in product_map.items():
            if pid in ids:
                continue
            if not product.brand or product.brand not in text:
                continue
            # Filter by explicit target sub_category before scoring.
            if target_sub_cat is not None and _normalize_product_match_text(product.sub_category) != target_sub_cat:
                continue
            # Filter by price band before scoring.
            if price_min is not None and product.price < price_min:
                continue
            if price_max is not None and product.price > price_max:
                continue
            score = _product_mention_score(normalized, product)
            # Require a score above the brand-only threshold (55).
            # When we have an anchor sub_category, also require that the
            # product shares it — this is the key guard that keeps brand-only
            # matches (which score the same regardless of sub_category) from
            # leaking unrelated products into the comparison.
            if score >= 55 and (
                effective_sub_cat is None
                or _normalize_product_match_text(product.sub_category) == effective_sub_cat
            ):
                scored.append((score, pid))
        scored.sort(reverse=True)
        for _, pid in scored:
            if pid not in ids:
                ids.append(pid)
        ids = ids[:3]  # cap to keep comparison manageable

    return ids


def _resolve_comparison_product_ids(text: str, context: SessionContext) -> list[str]:
    source_ids = _comparison_source_product_ids(text, context)
    if not source_ids:
        source_ids = list(context.last_product_ids)
    indexes = _comparison_reference_indexes(text)
    if indexes:
        return [source_ids[index] for index in indexes if index < len(source_ids)]
    if any(marker in text for marker in ["这两款", "两款", "前两款", "前2款"]):
        return source_ids[:2]
    return source_ids[: min(3, len(source_ids))]


def _is_explicit_current_comparison(plan: RetrievalPlan | None, text: str) -> bool:
    if not plan or plan.intent != "compare_products":
        return False
    if _comparison_looks_contextual(text):
        return False
    constraints = plan.hard_constraints
    return bool(
        constraints.include_brands
        or constraints.category
        or constraints.sub_category
        or constraints.price_min is not None
        or constraints.price_max is not None
    )


def _comparison_looks_contextual(text: str) -> bool:
    markers = [
        "这两款",
        "这三款",
        "这几款",
        "两款",
        "三款",
        "第一",
        "第二",
        "第三",
        "第1",
        "第2",
        "第3",
        "刚才",
        "刚刚",
        "之前",
        "上面",
        "以上",
        "前两款",
        "前三款",
        "前2款",
        "前3款",
    ]
    return any(marker in text for marker in markers)


def _comparison_plan_for_current_request(
    plan: RetrievalPlan, text: str, taxonomy, products: list[Product]
) -> RetrievalPlan:
    current_plan = plan.model_copy(deep=True)
    match = taxonomy.resolve(text) if taxonomy else None
    if match:
        current_plan.hard_constraints.category = match.category
        current_plan.hard_constraints.sub_category = match.sub_category
        current_plan.category = match.sub_category or match.category

    included_brands = _included_brands_from_product_catalog(text, products)
    if included_brands:
        current_plan.hard_constraints.include_brands = included_brands

    price_band = _price_band_from_text(text)
    if price_band:
        if current_plan.hard_constraints.price_min is None:
            current_plan.hard_constraints.price_min = price_band[0]
        if current_plan.hard_constraints.price_max is None:
            current_plan.hard_constraints.price_max = price_band[1]

    query_parts = [
        text,
        current_plan.hard_constraints.category,
        current_plan.hard_constraints.sub_category,
        *current_plan.hard_constraints.include_brands,
    ]
    current_plan.retrieval_query = " ".join(part for part in query_parts if part)
    return current_plan


def _price_band_from_text(text: str) -> tuple[float, float] | None:
    match = re.search(r"(\d{3,6})\s*(?:元|块)?\s*价位段", text)
    if not match:
        return None
    center = float(match.group(1))
    width = 1000.0 if center >= 3000 else max(100.0, center * 0.2)
    return max(0.0, center - width), center + width


def _included_brands_from_product_catalog(text: str, products: list[Product]) -> list[str]:
    brands: list[str] = []
    for product in products:
        brand = product.brand
        if brand and brand in text and brand not in brands:
            brands.append(brand)
    return brands


def _comparison_products_from_ranked(ranked: list[RankedProduct], plan: RetrievalPlan) -> list[Product]:
    constraints = plan.hard_constraints
    eligible = [item.product for item in ranked if hard_filter(item.product, constraints)]
    selected: list[Product] = []
    seen: set[str] = set()

    for brand in constraints.include_brands[:3]:
        product = next(
            (
                candidate
                for candidate in eligible
                if candidate.product_id not in seen and _product_matches_brand(candidate, brand)
            ),
            None,
        )
        if product:
            selected.append(product)
            seen.add(product.product_id)

    for product in eligible:
        if product.product_id in seen:
            continue
        selected.append(product)
        seen.add(product.product_id)
        if len(selected) >= 3:
            break

    return selected[:3]


def _product_matches_brand(product: Product, brand: str) -> bool:
    wanted = canonical_brand(brand)
    actual = canonical_brand(product.brand)
    if wanted and actual == wanted:
        return True
    text = f"{product.brand} {product.title} {product.search_text}"
    return bool(brand and brand in text)


def _comparison_reference_indexes(text: str) -> list[int]:
    marker_groups = [
        (("第一", "第1"), 0),
        (("第二", "第2"), 1),
        (("第三", "第3"), 2),
        (("第四", "第4"), 3),
    ]
    indexes: list[int] = []
    for markers, index in marker_groups:
        if any(marker in text for marker in markers) and index not in indexes:
            indexes.append(index)
    return indexes


def _comparison_source_product_ids(text: str, context: SessionContext) -> list[str]:
    recommendation_events = [
        event for event in context.state.context_events if event.result_type == "recommendation_set"
    ]
    if not recommendation_events:
        return list(context.last_product_ids)
    wanted_sub_category = _comparison_requested_sub_category(text)
    for event in reversed(recommendation_events):
        product_ids = [str(product_id) for product_id in event.payload.get("product_ids", [])]
        if len(product_ids) < 2:
            continue
        if wanted_sub_category:
            plan = event.payload.get("plan", {}) if isinstance(event.payload.get("plan"), dict) else {}
            hard = plan.get("hard_constraints", {}) if isinstance(plan.get("hard_constraints"), dict) else {}
            if hard.get("sub_category") != wanted_sub_category:
                continue
        return product_ids
    return list(context.last_product_ids)


def _comparison_requested_sub_category(text: str) -> str | None:
    if "手机" in text:
        return "智能手机"
    if "笔记本" in text or "电脑" in text:
        return "笔记本电脑"
    if "防晒" in text:
        return "防晒"
    if "精华" in text:
        return "精华"
    return None


def _resolve_mentioned_product_ids(text: str, last_product_ids: list[str]) -> list[str]:
    if any(marker in text for marker in ["这三款", "三款", "前三款", "前3款"]):
        return last_product_ids[:3]
    if any(marker in text for marker in ["以上几款", "上面几款", "这几款", "刚才几款", "最近几款"]):
        return last_product_ids[: min(3, len(last_product_ids))]
    if any(marker in text for marker in ["这两款", "两款", "前两款", "前2款"]):
        return last_product_ids[:2]
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


def _slot_constraints(slot: str) -> HardConstraints:
    aliases = {"防晒霜": "防晒", "速干T恤": "速干T恤", "帽子": "帽子", "背包": "背包"}
    sub_category = aliases.get(slot, slot)
    category = "美妆护肤" if sub_category == "防晒" else "服饰运动"
    return HardConstraints(category=category, sub_category=sub_category)


def _default_plan(text: str) -> RetrievalPlan:
    return RetrievalPlan(hard_constraints=HardConstraints(), retrieval_query=text or "商品推荐")


def _looks_like_product_request(text: str) -> bool:
    return any(word in text for word in PRODUCT_REQUEST_MARKERS)


def _unknown_category_text(text: str) -> str:
    return unknown_category_text()


def _is_explain_focus_request(text: str, ir) -> bool:
    return ir.response_goal == "explain_focus_product" or any(word in text for word in EXPLAIN_FOCUS_MARKERS)


def _wants_cheaper_alternative(text: str, ir) -> bool:
    if ir.response_goal == "recommend_cheaper_alternative":
        return True
    if ir.constraint_edits.add.soft_preferences.get("price_preference") == "更便宜":
        return True
    return any(word in text for word in CHEAPER_ALTERNATIVE_MARKERS)


def _wants_more_expensive_alternative(text: str, ir) -> bool:
    if ir.response_goal == "recommend_more_expensive_alternative":
        return True
    if ir.constraint_edits.add.soft_preferences.get("price_preference") == "更贵":
        return True
    return any(word in text for word in MORE_EXPENSIVE_ALTERNATIVE_MARKERS)


def _wants_different_brand(text: str, ir=None) -> bool:
    if ir is not None and ir.response_goal == "exclude_current_brand":
        return True
    return bool(extract_excluded_brands(text)) or any(word in text for word in DIFFERENT_BRAND_MARKERS)


def _focus_product_explanation(product: Product, context: SessionContext) -> str:
    reason = ""
    for item in context.last_recommendations:
        if item.get("product_id") == product.product_id:
            reason = str(item.get("reason") or "")
            break
    reason_text = f"推荐理由是：{reason}。" if reason else ""
    query_terms = [product.sub_category, product.brand, reason]
    evidence = product_evidence(product, query_terms, limit=2)
    summary = evidence_review_summary(product, query_terms)
    evidence_text = ""
    if evidence:
        evidence_text = "可参考的证据包括：" + "；".join(evidence[:2]) + "。"
    review_text = "评论摘要：" + summary.get("positive_summary", "暂无足够相关评论") + "。"
    return (
        f"刚刚那款是「{product.title}」，品牌是 {product.brand}，属于{product.sub_category}，"
        f"价格 {product.price:.0f} 元。{reason_text}{review_text}{evidence_text}"
        "如果你想换更便宜的、避开这个品牌，或者看同类备选，我可以继续筛。"
    )


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


def _update_profile(context: SessionContext, plan: RetrievalPlan) -> None:
    for key, value in plan.soft_preferences.items():
        if value:
            context.global_profile[key] = value
    constraints = plan.hard_constraints
    if constraints.price_min is not None:
        context.global_profile["budget_min"] = constraints.price_min
    if constraints.price_max is not None:
        context.global_profile["budget_max"] = constraints.price_max
    if constraints.include_brands:
        context.global_profile["include_brands"] = constraints.include_brands
    if constraints.exclude_terms:
        context.global_profile["exclude_terms"] = constraints.exclude_terms
    if constraints.exclude_brand_regions:
        context.global_profile["exclude_brand_regions"] = constraints.exclude_brand_regions


# 移动端适配：增大 chunk 到 36 字符，减少 WebSocket 帧数，降低移动网络开销
_TEXT_DELTA_CHUNK_SIZE = 36

def _text_delta_events(message_id: str, text: str) -> list[dict]:
    if not text:
        return []
    chunks = [text[i : i + _TEXT_DELTA_CHUNK_SIZE] for i in range(0, len(text), _TEXT_DELTA_CHUNK_SIZE)]
    return [{"type": "text_delta", "message_id": message_id, "text": chunk} for chunk in chunks]


def _message_id() -> str:
    return "assistant_" + uuid.uuid4().hex[:10]


async def _stream_with_first_chunk_timeout(
    stream,
    first_chunk_timeout: float,
    chunk_timeout: float,
):
    '''单一 stream 迭代器，对首块和后续每个 chunk 分别施加超时。

    设计目标：
    - 避免 LLM 卡死时整个 ws 长时间挂住。
    - 单 stream 实例从头到尾消费，不重复触发 LLM 调用（避免 stream_response 那种
      "先取首块再重建 stream"导致 LLM 跑两次、文本片段重复 yield 的问题）。

    任一阶段超时即终止迭代（StopAsyncIteration），不抛 TimeoutError，让调用方
    用 got_any_chunk 标志判断是否需要走静态 fallback 文本。
    '''
    import asyncio

    iterator = stream.__aiter__()
    timeout = first_chunk_timeout
    while True:
        try:
            chunk = await asyncio.wait_for(iterator.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            return
        except asyncio.TimeoutError:
            return
        yield chunk
        # 首块拿到后，后续 chunk 用更宽松的间隔超时
        timeout = chunk_timeout


def _no_match_text(plan: RetrievalPlan) -> str:
    constraints = plan.hard_constraints
    parts: list[str] = []
    if constraints.sub_category or constraints.category:
        parts.append(constraints.sub_category or constraints.category or "")
    if constraints.price_min is not None:
        parts.append(f"{constraints.price_min:.0f} 元以上")
    if constraints.price_max is not None:
        parts.append(f"{constraints.price_max:.0f} 元以内")
    if constraints.include_brands:
        parts.append("指定品牌" + "、".join(constraints.include_brands))
    if constraints.exclude_terms:
        parts.append("不含" + "、".join(constraints.exclude_terms))
    if constraints.exclude_brand_regions:
        parts.append("排除" + "、".join(constraints.exclude_brand_regions) + "品牌")
    condition_text = "、".join(part for part in parts if part) or "这些条件"
    return (
        no_result_contract_text(
            understanding=f"我按「{condition_text}」做了硬过滤。",
            conclusion="当前商品库里没有完全满足的商品。为了不违反你的明确要求，我先不推荐不合规替代品。",
            next_step="你可以放宽预算、取消一个排除条件，或者换成相近类目，我再继续帮你筛。",
        )
    )
