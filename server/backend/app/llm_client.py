from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from .config import Settings
from .knowledge_base import evidence_review_summary
from .llm_usage import LLMUsage, extract_usage
from .models import Product, RankedProduct, RetrievalPlan, SessionContext
from .prompt_registry import PromptRegistry
from .response_contract import recommendation_contract_text


_prompts = PromptRegistry(Path(__file__).parent / "prompts")

SEMANTIC_SYSTEM_PROMPT = _prompts.load("semantic_parser")
RESPONSE_SYSTEM_PROMPT = _prompts.load("response")
SELECTION_SYSTEM_PROMPT = _prompts.load("selection")
CHITCHAT_SYSTEM_PROMPT = _prompts.load("chitchat")
CONTEXTUAL_FOLLOWUP_SYSTEM_PROMPT = _prompts.load("contextual_followup")
# Task 11: 单品分析专用系统提示——与闲聊不同，LLM 需要扮演商品分析师角色
PRODUCT_ANALYSIS_SYSTEM_PROMPT = (
    "你是一个专业、客观的电商商品分析师。"
    "用户想了解一款具体商品的价值。请基于你掌握的商品知识，"
    "从性价比、适用场景、优缺点角度给出简短分析（2-4句话）。"
    "如果商品信息不足，诚实说明并引导用户补充需求。"
    "不要编造价格和规格。"
)


class DoubaoLLMClient:
    """OpenAI 兼容的 LLM 客户端。支持豆包 (doubao)、DeepSeek 或任意兼容 API。

    通过 Settings.llm_provider 切换后端：
      - doubao:  火山引擎豆包（默认），用 ARK_API_KEY / ARK_BASE_URL / ARK_MODEL
      - deepseek: DeepSeek API，用 LLM_API_KEY (或 DEEPSEEK_API_KEY)
      - custom:   任意 OpenAI 兼容服务，用 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
    """

    def __init__(self, settings: Settings):
        api_key = settings.effective_api_key
        if not api_key:
            provider = settings.llm_provider
            raise ValueError(
                f'LLM API key is required for provider="{provider}". '
                f'Set LLM_API_KEY or ARK_API_KEY environment variable.'
            )
        self.model = settings.effective_model           # 文本生成/闲聊
        self.fast_model = settings.effective_fast_model  # JSON 任务（意图解析、选品）
        self.reasoning_params = settings.reasoning_params

        import httpx
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.effective_base_url,
            http_client=http_client,
        )
        # Compression ledger input. Spec principle 4: store the most recent
        # provider-reported usage per call_kind so the agent lifecycle can
        # drive the watermark policy off real numbers. Preflight estimates
        # must NOT overwrite an existing authoritative entry — see
        # record_usage() below.
        self.last_usage_by_call_kind: dict[str, LLMUsage] = {}

    def record_usage(self, usage: LLMUsage) -> None:
        """Store the latest usage record for `usage.call_kind`.

        An authoritative provider-reported value always wins over a later
        non-authoritative one for the same call_kind; this prevents a
        preflight estimate from silently degrading a real measurement.
        """
        existing = self.last_usage_by_call_kind.get(usage.call_kind)
        if (
            existing is not None
            and existing.is_authoritative
            and not usage.is_authoritative
        ):
            return
        self.last_usage_by_call_kind[usage.call_kind] = usage

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(1, 8))
    async def _json_completion(self, messages: list[dict[str, str]], temperature: float = 0) -> str:
        kwargs: dict[str, Any] = {
            'model': getattr(self, 'fast_model', self.model),
            'messages': messages,
            'temperature': temperature,
            'response_format': {'type': 'json_object'},
        }
        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            if not _is_unsupported_json_mode_error(exc):
                raise
            kwargs.pop('response_format', None)
            response = await self.client.chat.completions.create(**kwargs)
        self.record_usage(extract_usage(response, call_kind='json'))
        return response.choices[0].message.content or '{}'

    async def parse_semantic_frame(
        self,
        message: str,
        context: SessionContext | dict[str, Any] | None = None,
        request_type: str = 'user_message',
    ) -> str:
        context_payload: dict[str, Any] = {}
        if isinstance(context, dict):
            context_payload = context
        elif context:
            context_payload = {
                'last_plan': context.last_plan.model_dump(mode='json') if context.last_plan else None,
                'focus_product_id': context.focus_product_id,
                'last_product_ids': context.last_product_ids,
                'last_recommendations': context.last_recommendations,
                'recent_cart_product_id': context.recent_cart_product_id,
                'global_profile': context.global_profile,
            }
        return await self._json_completion(
            [
                {'role': 'system', 'content': SEMANTIC_SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {
                            'message': message,
                            'request_type': request_type,
                            'session_context': context_payload,
                            'contextual_intent_task': _contextual_intent_task(message, context_payload),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,
        )

    async def classify_contextual_followup(self, message: str, context: dict[str, Any]) -> str:
        return await self._json_completion(
            [
                {'role': 'system', 'content': CONTEXTUAL_FOLLOWUP_SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {
                            'message': message,
                            'session_context': context,
                            'contextual_intent_task': _contextual_intent_task(message, context),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,
        )

    async def generate_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
        *,
        context=None,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {'role': 'system', 'content': RESPONSE_SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {
                            'message': user_message,
                            'evidence_payload': _response_evidence_payload(plan, ranked_products, focus_product, context=context),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.3,
            **self.reasoning_params,
        )
        self.record_usage(extract_usage(response, call_kind='response'))
        return response.choices[0].message.content or ''

    async def select_products(
        self,
        user_message: str,
        plan: RetrievalPlan,
        candidates: list[RankedProduct],
    ) -> str:
        return await self._json_completion(
            [
                {'role': 'system', 'content': SELECTION_SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {
                            'message': user_message,
                            'plan': plan.model_dump(mode='json'),
                            'candidates': _selection_candidates_payload(candidates),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,
        )

    async def stream_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
        *,
        context=None,
    ):
        stream_kwargs: dict[str, Any] = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': RESPONSE_SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {
                            'message': user_message,
                            'evidence_payload': _response_evidence_payload(plan, ranked_products, focus_product, context=context),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            'temperature': 0.3,
            'stream': True,
            'stream_options': {'include_usage': True},
            **self.reasoning_params,
        }
        try:
            stream = await self.client.chat.completions.create(**stream_kwargs)
        except Exception as exc:
            if not _is_unsupported_stream_options_error(exc):
                raise
            stream_kwargs.pop('stream_options', None)
            stream = await self.client.chat.completions.create(**stream_kwargs)
        observed_usage = False
        async for chunk in stream:
            text = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
            if text:
                yield text
            chunk_usage = extract_usage(chunk, call_kind='stream_response')
            if chunk_usage.is_authoritative:
                self.record_usage(chunk_usage)
                observed_usage = True
        if not observed_usage:
            # Streaming finished without provider-reported usage. Record a
            # non-authoritative marker so callers know the watermark policy
            # cannot rely on a real measurement from this call.
            self.record_usage(
                LLMUsage(
                    call_kind='stream_response',
                    source='unknown',
                    is_authoritative=False,
                )
            )

    async def stream_chitchat_response(
        self,
        user_message: str,
        intent: str,
        context: SessionContext | None = None,
    ):
        # Task 11: product_analysis 使用专用系统提示（商品分析师角色），而非闲聊提示
        system_prompt = PRODUCT_ANALYSIS_SYSTEM_PROMPT if intent == "product_analysis" else CHITCHAT_SYSTEM_PROMPT
        stream_kwargs: dict[str, Any] = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {'message': user_message, 'intent': intent},
                        ensure_ascii=False,
                    ),
                },
            ],
            'temperature': 0.4,
            'stream': True,
            'stream_options': {'include_usage': True},
            **self.reasoning_params,
        }
        try:
            stream = await self.client.chat.completions.create(**stream_kwargs)
        except Exception as exc:
            if not _is_unsupported_stream_options_error(exc):
                raise
            stream_kwargs.pop('stream_options', None)
            stream = await self.client.chat.completions.create(**stream_kwargs)
        observed_usage = False
        async for chunk in stream:
            text = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
            if text:
                yield text
            chunk_usage = extract_usage(chunk, call_kind='stream_chitchat')
            if chunk_usage.is_authoritative:
                self.record_usage(chunk_usage)
                observed_usage = True
        if not observed_usage:
            self.record_usage(
                LLMUsage(
                    call_kind='stream_chitchat',
                    source='unknown',
                    is_authoritative=False,
                )
            )


    async def generate_summary(self, history_text: str) -> str:
        """Generate a 1-2 sentence Chinese summary of shopping dialog history."""
        prompt_path = Path(__file__).parent / "prompts" / "v1" / "summary.txt"
        user_content = prompt_path.read_text(encoding="utf-8").replace("{history_text}", history_text)
        raw = await self._json_completion(
            [
                {"role": "system", "content": "你是对话摘要器。"},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
        )
        return (raw or "").strip()[:200]


class FakeLLMClient:
    async def parse_semantic_frame(
        self,
        message: str,
        context: SessionContext | None = None,
        request_type: str = 'user_message',
    ) -> str:
        return '{}'

    async def generate_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
        *,
        context=None,
    ) -> str:
        if not ranked_products:
            return (
                '**结论：** 我按你的条件筛了一遍，暂时没有找到完全合适的商品。'
                '\n\n**下一步：** 可以放宽预算或减少一个排除条件再试。'
            )
        primary = ranked_products[0]
        constraints = plan.hard_constraints
        handled: list[str] = []
        if constraints.price_min is not None:
            handled.append(f'预算 {constraints.price_min:.0f} 元以上')
        if constraints.price_max is not None:
            handled.append(f'预算 {constraints.price_max:.0f} 元以内')
        if constraints.include_brands:
            handled.append('指定品牌' + '、'.join(constraints.include_brands))
        if constraints.exclude_terms:
            handled.append('排除' + '、'.join(constraints.exclude_terms))
        if constraints.exclude_brand_regions:
            handled.append('排除' + '、'.join(constraints.exclude_brand_regions) + '品牌')
        handled_text = '，'.join(handled) if handled else '你的核心需求'
        review_summary = evidence_review_summary(
            primary.product,
            list(plan.soft_preferences.values()) + [plan.hard_constraints.sub_category or '', primary.product.brand],
        )
        review_text = review_summary.get('positive_summary') or '暂无足够相关评论'
        alternatives = ranked_products[1:4]
        alternatives_text = None
        if alternatives:
            alternatives_text = '备选差异：' + '；'.join(
                f'{item.product.title}偏{item.reason}' for item in alternatives
            ) + '。'
        return recommendation_contract_text(
            understanding=f'我按「{handled_text}」理解你的需求，并只从当前商品库候选里回答。',
            conclusion=f'优先看「{primary.product.title}」，它是当前最匹配的一款。',
            primary_reason=f'{primary.reason}，当前价格 {primary.product.price:.0f} 元。',
            review_summary=review_text,
            alternatives=alternatives_text,
            next_step='如果你想更便宜、更清爽或换个品牌，我可以继续帮你换。',
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
                'should_recommend': bool(selected),
                'need_clarification': False,
                'selected_product_ids': [item.product.product_id for item in selected],
                'reasons': {item.product.product_id: item.reason for item in selected},
            },
            ensure_ascii=False,
        )

    async def generate_summary(self, history_text: str) -> str:
        """Return a fixed summary for testing. Production override uses real LLM."""
        return "前几轮为购物咨询对话，用户当前需求如上。"

    async def classify_contextual_followup(self, message: str, context: dict[str, Any]) -> str:
        return json.dumps({'intent': 'unclear_input'}, ensure_ascii=False)

    async def stream_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
        *,
        context=None,
    ):
        text = await self.generate_response(user_message, plan, ranked_products, focus_product, context=context)
        for index in range(0, len(text), 12):
            yield text[index : index + 12]

    async def stream_chitchat_response(
        self,
        user_message: str,
        intent: str,
        context: SessionContext | None = None,
    ):
        if intent == 'unclear_input':
            text = '我还没太抓到你的购物需求。你可以随便说个想买的东西、预算，或者不想要什么，我再帮你筛。'
        else:
            text = '我在，可以陪你慢慢挑。你告诉我购物需求、预算多少，或者有什么偏好就行。'
        for index in range(0, len(text), 12):
            yield text[index : index + 12]


def _contextual_intent_task(message: str, context_payload: dict[str, Any]) -> dict[str, Any]:
    focus = context_payload.get('focus_product')
    return {
        'has_focus_product': bool(focus),
        'focus_product': focus,
        'instruction': (
            'If the user message is a contextual request about the focus product or last recommendations, '
            'classify it as product_followup and set target.reference to focus_product. '
            'Examples include cheaper alternative, another option, explain the previous item, and exclude this brand.'
        ),
        'user_message': message,
    }


def _is_unsupported_json_mode_error(exc: Exception) -> bool:
    text = str(exc)
    return 'response_format' in text and 'json_object' in text and 'not supported' in text


def _is_unsupported_stream_options_error(exc: Exception) -> bool:
    """Some OpenAI-compatible providers (older Doubao endpoints, proxies)
    reject the `stream_options` field. The caller should retry without it
    and accept that this stream will not report authoritative usage.
    """
    text = str(exc).lower()
    return 'stream_options' in text and ('not supported' in text or 'unknown' in text or 'invalid' in text)


def _constraint_sentence(plan: RetrievalPlan | None) -> str:
    """从 RetrievalPlan 中提取硬约束，生成用户条件摘要短句。

    用于注入 Response Prompt，让 LLM 明确知道当前生效的筛选条件。
    """
    if plan is None:
        return ""
    parts = []
    h = plan.hard_constraints
    if h.price_max is not None:
        parts.append(f"预算{h.price_max:.0f}以内")
    if h.price_min is not None:
        parts.append(f"预算{h.price_min:.0f}以上")
    if h.exclude_brands:
        parts.append(f"排除品牌{'、'.join(h.exclude_brands)}")
    if h.include_brands:
        parts.append(f"指定品牌{'、'.join(h.include_brands)}")
    for k, v in plan.soft_preferences.items():
        if k not in ("anchor_reference", "price_preference"):
            parts.append(str(v))
    return "已知用户条件：" + "、".join(parts) + "。" if parts else ""


def _build_recent_context_text(context: SessionContext | None) -> str:
    """从 SessionContext 中构建最近对话上下文文本。

    优先包含 living_summary（压缩摘要），然后拼接最近 10 条消息（5 轮完整对话）。
    当 context 为 None 或没有 dialog_turns 时返回空字符串。
    """
    if context is None or not context.dialog_turns:
        return ""
    parts = []
    # Phase 2 压缩摘要（Phase 1 中为占位符，通常为空）
    ls = context.compression_state.living_summary
    if ls.text:
        parts.append(f"[之前对话摘要] {ls.text}")
    # 最近 10 条消息（5 轮完整对话）
    recent = context.dialog_turns[-10:]
    for turn in recent:
        role = "用户" if turn.get("role") == "user" else "助手"
        content = turn.get('content', '')
        # B3: 压缩历史文本中的锚点标记，保留 product_id 去商品名和锚点语法
        content = re.sub(r"\[\[.+?#(.+?)\]\]", r"[商品:\1]", content)
        parts.append(f"{role}：{content}")
    return "\n".join(parts)


def _response_evidence_payload(
    plan: RetrievalPlan,
    ranked_products: list[RankedProduct],
    focus_product: Product | None = None,
    *,
    context: SessionContext | None = None,
) -> dict[str, Any]:
    products = [
        {
            'product_id': item.product.product_id,
            'title': item.product.title,
            'brand': item.product.brand,
            'category': item.product.category,
            'sub_category': item.product.sub_category,
            'price': item.product.price,
            'reason': item.reason,
            'review_summary': evidence_review_summary(
                item.product,
                list(plan.soft_preferences.values()) + [plan.hard_constraints.sub_category or '', item.product.brand],
            ),
        }
        for item in ranked_products[:4]
    ]
    constraints = plan.hard_constraints
    return {
        'allowed_products': products,
        'selected_primary': products[0]['product_id'] if products else None,
        'recent_context_text': _build_recent_context_text(context),
        'constraint_note': _constraint_sentence(plan),
        'response_contract': {
            'kind': 'recommendation_markdown_v2',
            'required_sections': ['理解', '结论', '主推', '下一步'],
            'optional_sections': ['评论摘要', '备选'],
            'primary_product_id': products[0]['product_id'] if products else None,
            'allowed_product_ids': [product['product_id'] for product in products],
        },
        'hard_constraints_applied': {
            'category': constraints.category,
            'sub_category': constraints.sub_category,
            'price_min': constraints.price_min,
            'price_max': constraints.price_max,
            'exclude_terms': constraints.exclude_terms,
            'include_brands': constraints.include_brands,
            'exclude_brands': constraints.exclude_brands,
            'exclude_brand_regions': constraints.exclude_brand_regions,
        },
        'focus_product': focus_product.model_dump(mode='json') if focus_product else None,
        'forbidden_claims': ['疗效承诺', '未给出的商品属性', '后端没有返回的 product_id'],
    }


def _selection_candidates_payload(candidates: list[RankedProduct]) -> list[dict[str, Any]]:
    return [
        {
            'product_id': item.product.product_id,
            'title': item.product.title,
            'brand': item.product.brand,
            'category': item.product.category,
            'sub_category': item.product.sub_category,
            'price': item.product.price,
            'score': item.score,
            'tier': item.tier,
            'reason': item.reason,
            'evidence': item.evidence[:3],
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
    selected = same_tier[:limit]
    # When 3+ same-tier candidates have a ≥2× price spread, promote a
    # mid-price product to primary so cheaper-alternative follow-ups have
    # room — the cheapest match stays available as a replacement.
    if len(selected) >= 3:
        prices = [item.product.price for item in selected]
        min_price = min(prices)
        if min_price <= 0:
            return selected  # guard against zero/negative prices producing invalid ratios
        if max(prices) / min_price >= 2.0:
            by_price = sorted(selected, key=lambda item: item.product.price)
            mid = by_price[len(by_price) // 2]
            result = [mid]
            for item in selected:
                if item.product.product_id != mid.product.product_id:
                    result.append(item)
            return result
    return selected


async def _empty_json_fallback(*_args: Any, **_kwargs: Any) -> str:
    '''熔断打开或 _json_completion 失败时的兜底：返回空 JSON。

    下游（如 ComparisonEngine）应 catch JSON 解析失败并走 rule-based 降级。
    '''
    return '{}'


class LLMClientWithBreaker:
    '''为 LLM 客户端增加熔断器保护的包装类。

    当熔断器处于 OPEN 状态或底层调用抛出异常时，自动降级到 FakeLLMClient。
    '''

    def __init__(
        self,
        client: Any,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        from .circuit_breaker import CircuitBreaker
        self.client = client
        self.breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self._fallback = FakeLLMClient()

    async def parse_semantic_frame(
        self,
        message: str,
        context: SessionContext | dict[str, Any] | None = None,
        request_type: str = 'user_message',
    ) -> str:
        return await self.breaker.call(
            self.client.parse_semantic_frame,
            self._fallback.parse_semantic_frame,
            message,
            context,
            request_type,
        )

    async def classify_contextual_followup(self, message: str, context: dict[str, Any]) -> str:
        return await self.breaker.call(
            self.client.classify_contextual_followup,
            self._fallback.classify_contextual_followup,
            message,
            context,
        )

    async def generate_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
        *,
        context=None,
    ) -> str:
        return await self.breaker.call(
            self.client.generate_response,
            self._fallback.generate_response,
            user_message,
            plan,
            ranked_products,
            focus_product,
            context=context,
        )

    async def select_products(
        self,
        user_message: str,
        plan: RetrievalPlan,
        candidates: list[RankedProduct],
    ) -> str:
        return await self.breaker.call(
            self.client.select_products,
            self._fallback.select_products,
            user_message,
            plan,
            candidates,
        )

    async def stream_response(
        self,
        user_message: str,
        plan: RetrievalPlan,
        ranked_products: list[RankedProduct],
        focus_product: Product | None = None,
        *,
        context=None,
    ):
        async for chunk in self.breaker.call_stream(
            self.client.stream_response,
            self._fallback.stream_response,
            user_message, plan, ranked_products, focus_product, context=context,
        ):
            yield chunk

    async def stream_chitchat_response(
        self,
        user_message: str,
        intent: str,
        context: SessionContext | None = None,
    ):
        async for chunk in self.breaker.call_stream(
            self.client.stream_chitchat_response,
            self._fallback.stream_chitchat_response,
            user_message, intent, context,
        ):
            yield chunk

    async def generate_summary(self, history_text: str) -> str:
        return await self.breaker.call(
            self.client.generate_summary,
            self._fallback.generate_summary,
            history_text,
        )

    async def _json_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0,
    ) -> str:
        '''底层 JSON 补全（被 ComparisonEngine 等需要严格 JSON 输出的下游直接调用）。

        FakeLLMClient 没有这个方法，所以 fallback 不能透传到它——熔断打开或调用失败时
        返回 '{}'，让上游走自己的 rule-based 降级（如 ComparisonEngine._fallback_compare）。
        '''
        return await self.breaker.call(
            self.client._json_completion,
            _empty_json_fallback,
            messages,
            temperature,
        )
