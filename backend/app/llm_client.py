from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from .config import Settings
from .knowledge_base import evidence_review_summary
from .models import Product, RankedProduct, RetrievalPlan, SessionContext
from .prompt_registry import PromptRegistry


_prompts = PromptRegistry(Path(__file__).parent / "prompts")

SEMANTIC_SYSTEM_PROMPT = _prompts.load("semantic_parser")
RESPONSE_SYSTEM_PROMPT = _prompts.load("response")
SELECTION_SYSTEM_PROMPT = _prompts.load("selection")
CHITCHAT_SYSTEM_PROMPT = _prompts.load("chitchat")
CONTEXTUAL_FOLLOWUP_SYSTEM_PROMPT = _prompts.load("contextual_followup")


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
                            'evidence_payload': _response_evidence_payload(plan, ranked_products, focus_product),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.3,
            **self.reasoning_params,
        )
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
    ):
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {'role': 'system', 'content': RESPONSE_SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {
                            'message': user_message,
                            'evidence_payload': _response_evidence_payload(plan, ranked_products, focus_product),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.3,
            stream=True,
            **self.reasoning_params,
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
                {'role': 'system', 'content': CHITCHAT_SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps(
                        {'message': user_message, 'intent': intent},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.4,
            stream=True,
            **self.reasoning_params,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
            if text:
                yield text


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
    ) -> str:
        if not ranked_products:
            return '我按你的条件筛了一遍，暂时没有找到完全合适的商品。可以放宽预算或减少一个排除条件再试。'
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
        if alternatives:
            alt_text = '；备选差异：' + '、'.join(
                f'{item.product.title}偏{item.reason}' for item in alternatives
            )
        else:
            alt_text = ''
        return (
            f'结论：优先看「{primary.product.title}」。'
            f'我已按「{handled_text}」筛选，主推价 {primary.product.price:.0f} 元，{primary.reason}。'
            f'评论摘要：{review_text}。{alt_text} 如果你想更便宜、更清爽或换个品牌，我可以继续帮你换。'
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

    async def classify_contextual_followup(self, message: str, context: dict[str, Any]) -> str:
        return json.dumps({'intent': 'unclear_input'}, ensure_ascii=False)

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


def _response_evidence_payload(
    plan: RetrievalPlan,
    ranked_products: list[RankedProduct],
    focus_product: Product | None = None,
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
    return same_tier[:limit]


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
    ) -> str:
        return await self.breaker.call(
            self.client.generate_response,
            self._fallback.generate_response,
            user_message,
            plan,
            ranked_products,
            focus_product,
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
    ):
        async for chunk in self.breaker.call_stream(
            self.client.stream_response,
            self._fallback.stream_response,
            user_message, plan, ranked_products, focus_product,
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
