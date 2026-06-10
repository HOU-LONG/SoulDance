import asyncio
import json
from pathlib import Path

from backend.app.agent import ShopGuideAgent
from backend.app.cart import CartService
from backend.app.constraint_filter import explain_filter, hard_filter
from backend.app.data_loader import load_products
from backend.app.llm_client import (
    RESPONSE_SYSTEM_PROMPT,
    DoubaoLLMClient,
    FakeLLMClient,
    _response_evidence_payload,
)
from backend.app.memory_cache import RecommendationMemoryCache, StructuredMemoryCache
from backend.app.models import (
    ChatRequest,
    HardConstraints,
    PendingClarification,
    Product,
    RankedProduct,
    RecommendationMemoryItem,
    RetrievalPlan,
)
from backend.app.taxonomy import TaxonomyResolver


class FakeRetriever:
    def search(self, query, top_k=20):
        return []


class CountingRetriever:
    def __init__(self, products):
        self.products = products
        self.calls = 0

    def search(self, query, top_k=20):
        self.calls += 1
        return [(product, 1.0 / (index + 1)) for index, product in enumerate(self.products[:top_k])]


class BlockingResponseLLM(FakeLLMClient):
    def __init__(self):
        self.generate_started = asyncio.Event()
        self.release_generate = asyncio.Event()

    async def generate_response(self, user_message, plan, ranked_products, focus_product=None):
        self.generate_started.set()
        await self.release_generate.wait()
        return "这是延迟生成的导购解释。"


class StreamingResponseLLM(FakeLLMClient):
    def __init__(self):
        self.generate_called = False
        self.chunks = ["第一段", "第二段", "第三段"]

    async def generate_response(self, user_message, plan, ranked_products, focus_product=None):
        self.generate_called = True
        return "不应该等待完整回复"

    async def stream_response(self, user_message, plan, ranked_products, focus_product=None):
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk


class ProductSelectionLLM(FakeLLMClient):
    def __init__(self, selected_ids, clarify=False):
        self.selected_ids = list(selected_ids)
        self.clarify = clarify
        self.candidate_count = 0
        self.calls = 0

    async def select_products(self, user_message, plan, candidates):
        self.calls += 1
        self.candidate_count = len(candidates)
        return json.dumps(
            {
                "should_recommend": not self.clarify,
                "need_clarification": self.clarify,
                "selected_product_ids": self.selected_ids,
                "reasons": {product_id: f"LLM选择{product_id}" for product_id in self.selected_ids},
            },
            ensure_ascii=False,
        )


class SemanticSelectionLLM(FakeLLMClient):
    def __init__(self, semantic_frames=None, selected_ids=None):
        self.semantic_frames = list(semantic_frames or [])
        self.selected_ids = list(selected_ids or [])

    async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
        if self.semantic_frames:
            return json.dumps(self.semantic_frames.pop(0), ensure_ascii=False)
        return json.dumps({"intent": "recommend_product"}, ensure_ascii=False)

    async def select_products(self, user_message, plan, candidates):
        selected_ids = [product_id for product_id in self.selected_ids if any(c.product.product_id == product_id for c in candidates)]
        if not selected_ids:
            selected_ids = [item.product.product_id for item in candidates[:1]]
        return json.dumps(
            {
                "should_recommend": bool(selected_ids),
                "need_clarification": False,
                "selected_product_ids": selected_ids,
                "reasons": {product_id: f"LLM选择{product_id}" for product_id in selected_ids},
            },
            ensure_ascii=False,
        )


def test_hard_filter_excludes_brand_aliases_and_explains_reason():
    huawei_product = Product(
        product_id="demo_huawei",
        title="HUAWEI Mate 测试手机",
        brand="HUAWEI",
        category="数码电子",
        sub_category="智能手机",
        price=3999,
        image_path="",
        search_text="HUAWEI Mate 测试手机",
    )
    apple_product = Product(
        product_id="demo_apple",
        title="苹果 MacBook 测试笔记本",
        brand="苹果",
        category="数码电子",
        sub_category="笔记本电脑",
        price=8999,
        image_path="",
        search_text="苹果 Apple MacBook 测试笔记本",
    )

    assert not hard_filter(huawei_product, HardConstraints(exclude_brands=["华为"]))
    assert not hard_filter(apple_product, HardConstraints(exclude_brands=["Apple"]))
    assert "华为" in explain_filter(huawei_product, HardConstraints(exclude_brands=["华为"]))


def test_response_prompt_requires_short_paragraphs_or_bullets():
    prompt = Path("backend/app/prompts/v1/response.txt").read_text(encoding="utf-8")

    assert "2-4" in prompt
    assert "短段落" in prompt
    assert "短列表" in prompt
    assert "**\u7ed3\u8bba\uff1a**" in prompt
    assert "**\u4e3b\u63a8\uff1a**" in prompt
    assert "**\u5907\u9009\uff1a**" in prompt
    assert "**\u4e0b\u4e00\u6b65\uff1a**" in prompt


class HumanizedChitchatLLM(FakeLLMClient):
    def __init__(self):
        self.messages = []

    async def stream_chitchat_response(self, user_message, intent, context=None):
        self.messages.append((user_message, intent))
        yield "我在，"
        yield "你可以慢慢说想买什么。"


class SemanticFrameLLM(FakeLLMClient):
    def __init__(self, *frames):
        self.frames = list(frames)

    async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
        if not self.frames:
            return "{}"
        return json.dumps(self.frames.pop(0), ensure_ascii=False)


class ContextRecordingSemanticLLM(FakeLLMClient):
    def __init__(self, *frames):
        self.frames = list(frames)
        self.contexts = []

    async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
        self.contexts.append(context)
        if not self.frames:
            return "{}"
        return json.dumps(self.frames.pop(0), ensure_ascii=False)


class ContextualFallbackLLM(FakeLLMClient):
    def __init__(self, primary_frames, contextual_frames):
        self.primary_frames = list(primary_frames)
        self.contextual_frames = list(contextual_frames)
        self.contextual_calls = []

    async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
        if self.primary_frames:
            return json.dumps(self.primary_frames.pop(0), ensure_ascii=False)
        return json.dumps({"intent": "unclear_input"}, ensure_ascii=False)

    async def classify_contextual_followup(self, message, context):
        self.contextual_calls.append((message, context))
        if not self.contextual_frames:
            return json.dumps({"intent": "unclear_input"}, ensure_ascii=False)
        return json.dumps(self.contextual_frames.pop(0), ensure_ascii=False)


class RawSemanticLLM(FakeLLMClient):
    def __init__(self, *raw_frames):
        self.raw_frames = list(raw_frames)

    async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
        if not self.raw_frames:
            return "{}"
        return self.raw_frames.pop(0)


class UnsupportedJsonModeError(Exception):
    pass


class FakeChatCompletionMessage:
    def __init__(self, content):
        self.content = content


class FakeChatCompletionChoice:
    def __init__(self, content):
        self.message = FakeChatCompletionMessage(content)


class FakeChatCompletionResponse:
    def __init__(self, content):
        self.choices = [FakeChatCompletionChoice(content)]


class JsonModeFallbackCompletions:
    def __init__(self, content):
        self.calls = []
        self.content = content

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("response_format") == {"type": "json_object"}:
            raise UnsupportedJsonModeError(
                "The parameter `response_format.type` specified in the request are not valid: "
                "`json_object` is not supported by this model."
            )
        return FakeChatCompletionResponse(self.content)


class JsonModeFallbackClient:
    def __init__(self, content):
        self.chat = type("Chat", (), {})()
        self.chat.completions = JsonModeFallbackCompletions(content)


class NoPlannerSemanticLLM(SemanticFrameLLM):
    pass


def test_load_products_reads_dataset():
    products = load_products("ecommerce_agent_dataset")

    assert len(products) == 100
    assert products[0].product_id
    assert products[0].title
    assert products[0].chunk


def test_taxonomy_resolver_covers_dataset_subcategories_and_aliases():
    products = load_products("ecommerce_agent_dataset")
    resolver = TaxonomyResolver.from_products(products)

    for product in products:
        resolved = resolver.resolve(product.sub_category)
        assert resolved is not None
        assert resolved.category == product.category
        assert resolved.sub_category == product.sub_category

    assert resolver.resolve("轻薄笔记本").sub_category == "笔记本电脑"
    assert resolver.resolve("精华液").sub_category == "精华"
    assert resolver.resolve("猫粮") is None

    dongpeng = resolver.resolve_task_object("\u6211\u8981\u4e00\u74f6\u4e1c\u9e4f\u7279\u996e")
    assert dongpeng is not None
    assert dongpeng.category == "\u98df\u54c1\u996e\u6599"
    assert dongpeng.sub_category == "\u529f\u80fd\u996e\u6599"


def test_specific_food_product_request_builds_retrieval_plan():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    plan = asyncio.run(
        agent.plan(ChatRequest(type="user_message", session_id="demo_dongpeng", message="\u6211\u8981\u4e00\u74f6\u4e1c\u9e4f\u7279\u996e"))
    )

    assert plan.intent == "recommend_product"
    assert plan.hard_constraints.category == "\u98df\u54c1\u996e\u6599"
    assert plan.hard_constraints.sub_category == "\u529f\u80fd\u996e\u6599"


def test_taxonomy_resolver_recognizes_unique_catalog_title_aliases():
    products = load_products("ecommerce_agent_dataset")
    resolver = TaxonomyResolver.from_products(products)

    alias_to_products = {}
    for product in products:
        alias = _catalog_title_alias_for_test(product)
        if alias:
            alias_to_products.setdefault(alias, []).append(product)

    failures = []
    for alias, matched_products in alias_to_products.items():
        if len(matched_products) != 1:
            continue
        product = matched_products[0]
        match = resolver.resolve_task_object(f"我要一个{alias}")
        if match is None or match.category != product.category or match.sub_category != product.sub_category:
            failures.append((alias, product.product_id, product.category, product.sub_category, match))

    assert failures == []


def _catalog_title_alias_for_test(product):
    title = (product.title or "").strip()
    if not title:
        return ""
    tokens = title.split()
    first = tokens[0].strip("，,、()（）") if tokens else ""
    if first and first != product.brand and len(first) >= 3:
        return first
    if len(tokens) >= 2:
        return f"{tokens[0]}{tokens[1]}".strip("，,、()（）")
    return first

def test_planner_extracts_budget_and_negative_constraints():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    plan = asyncio.run(
        agent.plan(
            ChatRequest(
                type="user_message",
                session_id="demo",
                message="推荐防晒霜，但不要含酒精的，也不要日系品牌，100以内",
            )
        )
    )

    assert plan.intent == "recommend_product"
    assert plan.hard_constraints.price_max == 100
    assert "酒精" in plan.hard_constraints.exclude_terms
    assert "日本" in plan.hard_constraints.exclude_brand_regions
    assert plan.category in {"防晒", "美妆护肤"}


def test_hard_constraints_filter_forbidden_products():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    plan = asyncio.run(
        agent.plan(
                ChatRequest(
                    type="user_message",
                    session_id="demo",
                    message="推荐防晒霜，但不要含酒精的，也不要日系品牌",
                )
            )
        )

    candidates = agent.retrieve_and_rank(plan)

    assert candidates
    for ranked in candidates:
        assert "日本" not in ranked.product.brand_region


def test_negative_brand_apple_is_enforced_before_product_cards():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_no_apple",
                message="我想给大学生买一台轻薄笔记本，预算6000以内，不要苹果",
            )
        )
    )

    product_events = [event for event in events if event["type"] == "product_item"]
    if product_events:
        assert all(event["product"]["sub_category"] == "笔记本电脑" for event in product_events)
        assert all("Apple" not in event["product"]["brand"] and "苹果" not in event["product"]["brand"] for event in product_events)
    else:
        assert any(event["type"] == "filter_recovery_options" for event in events)


def test_subcategory_query_keeps_essence_results_strict():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_essence_budget",
                message="推荐精华，预算100以内",
            )
        )
    )

    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    assert all(event["product"]["sub_category"] == "精华" for event in product_events)
    assert all(event["product"]["price"] <= 100 for event in product_events)


def test_unknown_taxonomy_request_returns_recovery_without_cross_category_cards():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_unknown_taxonomy",
                message="推荐毛巾",
            )
        )
    )

    assert not [event for event in events if event["type"] == "product_item"]
    assert any(event["type"] == "filter_recovery_options" for event in events)


def test_greeting_does_not_recommend_products():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    plan = asyncio.run(
        agent.plan(ChatRequest(type="user_message", session_id="demo_greeting_plan", message="你好?"))
    )
    assert plan.intent == "small_talk"

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_greeting",
                message="你好?",
            )
        )
    )

    event_types = [event["type"] for event in events]
    assert "product_item" not in event_types
    assert "clarification_request" not in event_types
    merged_text = "".join(event["text"] for event in events if event["type"] == "text_delta")
    assert "购物需求" in merged_text


def test_small_talk_variants_do_not_trigger_retrieval():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    agent = ShopGuideAgent(products, FakeLLMClient(), retriever)

    for index, message in enumerate(["hello", "halo", "hallo", "在吗", "谢谢", "你是谁"]):
        events = asyncio.run(
            agent.handle_message(
                ChatRequest(type="user_message", session_id=f"demo_small_talk_{index}", message=message)
            )
        )
        event_types = [event["type"] for event in events]
        assert event_types[0] == "assistant_state"
        assert event_types[-1] == "done"
        assert "text_delta" in event_types
        assert "product_item" not in event_types
        assert "clarification_request" not in event_types

    assert retriever.calls == 0


def test_small_talk_identity_combo_stays_small_talk():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    agent = ShopGuideAgent(products, FakeLLMClient(), retriever)

    for index, message in enumerate(["你好，你是谁", "你好，你能做什么", "你是谁呀"]):
        plan = asyncio.run(
            agent.plan(
                ChatRequest(type="user_message", session_id=f"demo_small_talk_combo_plan_{index}", message=message)
            )
        )
        assert plan.intent == "small_talk"

        events = asyncio.run(
            agent.handle_message(
                ChatRequest(type="user_message", session_id=f"demo_small_talk_combo_{index}", message=message)
            )
        )

        event_types = [event["type"] for event in events]
        assert "product_item" not in event_types
        state = next(event for event in events if event["type"] == "assistant_state")
        assert state["intent"] == "small_talk"

    assert retriever.calls == 0


def test_shopping_request_overrides_llm_small_talk_intent():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    llm = SemanticFrameLLM({"intent": "small_talk"}, {"intent": "small_talk"})
    agent = ShopGuideAgent(products, llm, retriever)

    plan = asyncio.run(
        agent.plan(
            ChatRequest(
                type="user_message",
                session_id="demo_shopping_guard_plan",
                message="\u63a8\u8350\u9632\u6652\u971c",
            )
        )
    )
    assert plan.intent == "recommend_product"

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_shopping_guard",
                message="\u63a8\u8350\u9632\u6652\u971c",
            )
        )
    )

    event_types = [event["type"] for event in events]
    assert "product_item" in event_types
    assert retriever.calls > 0


def test_llm_small_talk_intent_is_honored_for_unlisted_greeting():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    llm = SemanticFrameLLM({"intent": "small_talk"}, {"intent": "small_talk"})
    agent = ShopGuideAgent(products, llm, retriever)

    plan = asyncio.run(agent.plan(ChatRequest(type="user_message", session_id="demo_halo_plan", message="halo")))
    assert plan.intent == "small_talk"

    events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_halo", message="halo"))
    )

    event_types = [event["type"] for event in events]
    assert event_types[0] == "assistant_state"
    assert event_types[-1] == "done"
    assert "product_item" not in event_types
    assert "clarification_request" not in event_types
    assert retriever.calls == 0


def test_doubao_semantic_parse_retries_without_json_mode_when_model_rejects_response_format():
    content = json.dumps(
        {
            "intent": "product_followup",
            "target": {"reference": "focus_product"},
            "response_goal": "explain_focus_product",
        },
        ensure_ascii=False,
    )
    client = object.__new__(DoubaoLLMClient)
    client.model = "doubao-test"
    client.client = JsonModeFallbackClient(content)

    raw = asyncio.run(
        client.parse_semantic_frame(
            "刚刚那个是什么？",
            {"has_focus_product": True, "focus_product": {"product_id": "p1"}},
        )
    )

    assert json.loads(raw)["intent"] == "product_followup"
    calls = client.client.chat.completions.calls
    assert len(calls) == 2
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in calls[1]


def test_semantic_parser_normalizes_empty_list_constraint_patches_from_llm():
    products = load_products("ecommerce_agent_dataset")
    llm = RawSemanticLLM(
        json.dumps({"intent": "recommend_product"}, ensure_ascii=False),
        json.dumps(
            {
                "intent": "product_followup",
                "target": {"reference": "focus_product"},
                "response_goal": "explain_focus_product",
                "constraint_edits": {"add": {}, "remove": [], "relax": []},
                "query_intent": {},
            },
            ensure_ascii=False,
        ),
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_empty_list_patch",
                message="推荐一款手机，预算4000，拍照优先",
            )
        )
    )
    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_empty_list_patch",
                message="刚刚那个是什么？",
            )
        )
    )

    state = next(event for event in events if event["type"] == "assistant_state")
    assert state["intent"] == "product_followup"


def test_unclear_input_does_not_trigger_retrieval_or_product_cards():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    agent = ShopGuideAgent(products, FakeLLMClient(), retriever)

    for index, message in enumerate(["sdfghjhgfdg", "我是猪"]):
        plan = asyncio.run(
            agent.plan(
                ChatRequest(
                    type="user_message",
                    session_id=f"demo_unclear_plan_{index}",
                    message=message,
                )
            )
        )
        assert plan.intent == "unclear_input"
        assert plan.retrieval_mode == "no_retrieval"

        events = asyncio.run(
            agent.handle_message(
                ChatRequest(type="user_message", session_id=f"demo_unclear_{index}", message=message)
            )
        )

        event_types = [event["type"] for event in events]
        assert event_types[0] == "assistant_state"
        assert event_types[-1] == "done"
        assert "product_item" not in event_types
        assert "clarification_request" not in event_types
        state = next(event for event in events if event["type"] == "assistant_state")
        assert state["intent"] == "unclear_input"
        assert state["retrieval_mode"] == "no_retrieval"
        merged_text = "".join(event["text"] for event in events if event["type"] == "text_delta")
        assert "购物需求" in merged_text

    assert retriever.calls == 0


def test_backend_admission_gate_blocks_llm_false_recommend_product_intent():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    llm = SemanticFrameLLM({"intent": "recommend_product"}, {"intent": "recommend_product"})
    agent = ShopGuideAgent(products, llm, retriever)

    plan = asyncio.run(
        agent.plan(ChatRequest(type="user_message", session_id="demo_llm_false_positive_plan", message="我是猪"))
    )
    assert plan.intent == "unclear_input"
    assert plan.retrieval_mode == "no_retrieval"

    events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_llm_false_positive", message="我是猪"))
    )

    event_types = [event["type"] for event in events]
    assert "product_item" not in event_types
    assert "clarification_request" not in event_types
    assert retriever.calls == 0


def test_greeting_with_product_request_still_recommends():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    plan = asyncio.run(
        agent.plan(
            ChatRequest(type="user_message", session_id="demo_greeting_product_plan", message="你好，推荐防晒霜")
        )
    )
    assert plan.intent == "recommend_product"

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_greeting_product", message="你好，推荐防晒霜")
        )
    )

    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    assert all(event["product"]["sub_category"] == "防晒" for event in product_events)


def test_llm_compare_misclassification_is_guarded_for_fresh_recommendation():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticFrameLLM({"intent": "compare_products"})
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_cat_food",
                message="想找一款猫粮，家里猫肠胃比较敏感，预算300左右，优先看口碑好的",
            )
        )
    )

    assert "comparison_result" not in [event["type"] for event in events]
    merged_text = "".join(event["text"] for event in events if event["type"] == "text_delta")
    assert "还没有足够的最近推荐商品可以对比" not in merged_text


def test_structured_memory_cache_reuses_ranked_results_for_same_plan():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    cache = StructuredMemoryCache()
    agent = ShopGuideAgent(products, FakeLLMClient(), retriever, memory_cache=cache)
    request = ChatRequest(type="user_message", session_id="demo_cache", message="推荐防晒霜")

    first_events = asyncio.run(agent.handle_message(request))
    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_cache_2", message="推荐防晒霜")
        )
    )

    first_products = [event["product"]["product_id"] for event in first_events if event["type"] == "product_item"]
    second_products = [event["product"]["product_id"] for event in second_events if event["type"] == "product_item"]
    assert first_products == second_products
    assert retriever.calls == 1
    assert cache.stats()["hits"] == 1


def test_structured_memory_cache_does_not_cross_hard_constraints():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    cache = StructuredMemoryCache()
    agent = ShopGuideAgent(products, FakeLLMClient(), retriever, memory_cache=cache)

    asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_cache_100", message="推荐精华，预算100以内")
        )
    )
    asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_cache_800", message="推荐精华，预算800以内")
        )
    )

    assert retriever.calls == 2
    assert cache.stats()["misses"] == 2


def test_recommendation_memory_exact_hit_skips_retriever_and_llm_selection():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    probe_agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    probe_plan = asyncio.run(
        probe_agent.plan(ChatRequest(type="user_message", session_id="demo_rec_memory_probe", message="推荐防晒霜"))
    )
    selected_ids = [item.product.product_id for item in probe_agent.retrieve_and_rank(probe_plan)[:2]]
    llm = ProductSelectionLLM(selected_ids)
    memory = RecommendationMemoryCache()
    agent = ShopGuideAgent(products, llm, retriever, recommendation_memory=memory)

    first_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_rec_memory_1", message="推荐防晒霜"))
    )
    second_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_rec_memory_2", message="推荐防晒霜"))
    )

    first_products = [event["product"]["product_id"] for event in first_events if event["type"] == "product_item"]
    second_products = [event["product"]["product_id"] for event in second_events if event["type"] == "product_item"]
    second_states = [event for event in second_events if event["type"] == "assistant_state"]
    assert first_products == second_products == selected_ids
    assert retriever.calls == 1
    assert llm.calls == 1
    assert memory.stats()["exact_hits"] == 1
    assert any(state.get("memory_mode") == "exact_hit" for state in second_states)


def test_recommendation_memory_does_not_cross_hard_constraints():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    memory = RecommendationMemoryCache()
    agent = ShopGuideAgent(products, ProductSelectionLLM([]), retriever, recommendation_memory=memory)

    asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_rec_constraint_1", message="推荐防晒霜"))
    )
    asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_rec_constraint_2", message="推荐防晒霜，预算1元以内"))
    )

    assert memory.stats()["exact_hits"] == 0
    assert memory.stats()["semantic_hits"] == 0
    assert memory.stats()["misses"] >= 2


def test_recommendation_memory_semantic_hit_for_compatible_query():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    probe_agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    probe_plan = asyncio.run(
        probe_agent.plan(ChatRequest(type="user_message", session_id="demo_rec_sem_probe", message="推荐防晒霜"))
    )
    selected_ids = [item.product.product_id for item in probe_agent.retrieve_and_rank(probe_plan)[:1]]
    llm = ProductSelectionLLM(selected_ids)
    memory = RecommendationMemoryCache()
    agent = ShopGuideAgent(products, llm, retriever, recommendation_memory=memory)

    asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_rec_sem_1", message="推荐防晒霜"))
    )
    second_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_rec_sem_2", message="想买一款防晒霜"))
    )

    second_products = [event["product"]["product_id"] for event in second_events if event["type"] == "product_item"]
    assert second_products == selected_ids
    assert retriever.calls == 1
    assert llm.calls == 1
    assert memory.stats()["semantic_hits"] == 1
    assert any(event.get("memory_mode") == "semantic_hit" for event in second_events if event["type"] == "assistant_state")


def test_recommendation_memory_semantic_hit_requires_soft_preference_compatibility():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    memory = RecommendationMemoryCache()
    agent = ShopGuideAgent(products, ProductSelectionLLM(["p_beauty_001"]), retriever, recommendation_memory=memory)

    asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_rec_sem_strict_1", message="推荐防晒霜"))
    )
    second_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_rec_sem_strict_2", message="推荐清爽防晒"))
    )

    assert memory.stats()["semantic_hits"] == 0
    assert retriever.calls == 2
    assert all(event.get("memory_mode") != "semantic_hit" for event in second_events if event["type"] == "assistant_state")


def test_recommendation_memory_is_not_used_for_unclear_input():
    products = load_products("ecommerce_agent_dataset")
    retriever = CountingRetriever(products)
    memory = RecommendationMemoryCache()
    agent = ShopGuideAgent(products, FakeLLMClient(), retriever, recommendation_memory=memory)

    events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_rec_unclear", message="我是猪"))
    )

    assert retriever.calls == 0
    assert memory.stats()["misses"] == 0
    assert "product_item" not in [event["type"] for event in events]


def test_product_followup_inherits_original_constraints():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    initial = ChatRequest(
        type="user_message",
        session_id="demo",
        message="推荐一款适合油皮的洗面奶，不要含酒精",
    )
    events = asyncio.run(agent.handle_message(initial))
    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    focus_id = product_events[0]["product"]["product_id"]

    followup = ChatRequest(
        type="product_followup",
        session_id="demo",
        focus_product_id=focus_id,
        message="这个有点贵，有没有100以内的？",
    )
    followup_events = asyncio.run(agent.handle_message(followup))
    replacement = next(event for event in followup_events if event["type"] == "replacement_product")

    assert replacement["product"]["price"] <= 100
    assert "酒精" not in replacement["product"]["reason"]


def test_no_match_followup_does_not_emit_replacement_product():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_no_match",
                message="推荐防晒霜，但不要含酒精的，也不要日系品牌",
            )
        )
    )
    primary = next(event for event in events if event["type"] == "product_item")

    followup_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="product_followup",
                session_id="demo_no_match",
                focus_product_id=primary["product"]["product_id"],
                message="这个有点贵，有没有100以内的？",
            )
        )
    )

    assert not [event for event in followup_events if event["type"] == "replacement_product"]
    merged_text = "".join(event["text"] for event in followup_events if event["type"] == "text_delta")
    assert "没有完全满足" in merged_text


def test_followup_uses_semantic_constraint_edits_to_remove_old_constraints():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticFrameLLM(
        {
            "intent": "product_followup",
            "constraint_edits": {
                "add": {"price_max": 100},
                "remove": {"exclude_terms": ["酒精"]},
            },
        }
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_semantic_followup",
                message="推荐一款适合油皮的洗面奶，不要含酒精",
            )
        )
    )

    asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="product_followup",
                session_id="demo_semantic_followup",
                message="酒精可以接受，但要100以内",
            )
        )
    )

    updated_plan = agent.sessions.get("demo_semantic_followup").last_plan
    assert updated_plan.hard_constraints.price_max == 100
    assert "酒精" not in updated_plan.hard_constraints.exclude_terms
    assert updated_plan.hard_constraints.sub_category == "洁面"


def test_llm_product_followup_from_user_message_is_not_downgraded_to_unclear_input():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticFrameLLM(
        {"intent": "recommend_product"},
        {
            "intent": "product_followup",
            "target": {"reference": "focus_product", "selection_strategy": "primary"},
            "constraint_edits": {"add": {"soft_preferences": {"price_preference": "更便宜"}}},
            "response_goal": "recommend_cheaper_alternative",
        },
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_llm_followup_cheaper",
                message="推荐一款手机，预算4000，拍照优先",
            )
        )
    )
    primary = next(event for event in first_events if event["type"] == "product_item")

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_llm_followup_cheaper",
                message="换个更便宜的",
            )
        )
    )

    states = [event for event in second_events if event["type"] == "assistant_state"]
    assert states[0]["intent"] == "product_followup"
    assert states[0]["retrieval_mode"] == "product_focus_retrieval"
    assert not any(event.get("intent") == "unclear_input" for event in states)
    replacement_events = [event for event in second_events if event["type"] == "replacement_product"]
    if replacement_events:
        replacement = replacement_events[0]
        assert replacement["product"]["sub_category"] == primary["product"]["sub_category"]
        assert replacement["product"]["price"] < primary["product"]["price"]
    else:
        assert "filter_recovery_options" in [event["type"] for event in second_events]


def test_llm_product_followup_can_explain_focus_product_without_new_card():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticFrameLLM(
        {"intent": "recommend_product"},
        {
            "intent": "product_followup",
            "target": {"reference": "focus_product", "selection_strategy": "primary"},
            "response_goal": "explain_focus_product",
        },
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_llm_followup_explain",
                message="推荐一款手机，预算4000，拍照优先",
            )
        )
    )
    primary = next(event for event in first_events if event["type"] == "product_item")

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_llm_followup_explain",
                message="刚刚那个是什么？",
            )
        )
    )

    event_types = [event["type"] for event in second_events]
    states = [event for event in second_events if event["type"] == "assistant_state"]
    merged_text = "".join(event["text"] for event in second_events if event["type"] == "text_delta")
    assert states[0]["intent"] == "product_followup"
    assert "replacement_product" not in event_types
    assert "product_item" not in event_types
    assert primary["product"]["name"] in merged_text


def test_no_match_followup_preserves_focus_for_later_explanation():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticFrameLLM(
        {"intent": "recommend_product"},
        {
            "intent": "product_followup",
            "target": {"reference": "focus_product", "selection_strategy": "primary"},
            "constraint_edits": {"add": {"soft_preferences": {"price_preference": "更便宜"}}},
            "response_goal": "recommend_cheaper_alternative",
        },
        {
            "intent": "product_followup",
            "target": {"reference": "focus_product", "selection_strategy": "primary"},
            "response_goal": "explain_focus_product",
        },
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_preserve_focus_after_no_match",
                message="推荐一款手机，预算4000，拍照优先",
            )
        )
    )
    primary = next(event for event in first_events if event["type"] == "product_item")

    no_match_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_preserve_focus_after_no_match",
                message="换个更便宜的",
            )
        )
    )
    assert "filter_recovery_options" in [event["type"] for event in no_match_events]
    context_after_no_match = agent.sessions.get("demo_preserve_focus_after_no_match")
    assert context_after_no_match.focus_product_id == primary["product"]["product_id"]
    assert context_after_no_match.last_recommendations
    assert context_after_no_match.last_recommendations[0]["product_id"] == primary["product"]["product_id"]

    explain_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_preserve_focus_after_no_match",
                message="刚刚那个是什么？",
            )
        )
    )

    state = next(event for event in explain_events if event["type"] == "assistant_state")
    event_types = [event["type"] for event in explain_events]
    merged_text = "".join(event["text"] for event in explain_events if event["type"] == "text_delta")
    assert state["intent"] == "product_followup"
    assert "replacement_product" not in event_types
    assert "product_item" not in event_types
    assert primary["product"]["name"] in merged_text


def test_llm_product_followup_can_exclude_current_brand_from_user_message():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticFrameLLM(
        {"intent": "recommend_product"},
        {
            "intent": "product_followup",
            "target": {"reference": "focus_product", "selection_strategy": "primary"},
            "response_goal": "exclude_current_brand",
        },
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_llm_followup_brand",
                message="推荐一款手机，预算4000，拍照优先",
            )
        )
    )
    primary = next(event for event in first_events if event["type"] == "product_item")

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_llm_followup_brand",
                message="不要这个品牌",
            )
        )
    )

    states = [event for event in second_events if event["type"] == "assistant_state"]
    assert states[0]["intent"] == "product_followup"
    replacement_events = [event for event in second_events if event["type"] == "replacement_product"]
    if replacement_events:
        assert replacement_events[0]["product"]["brand"] != primary["product"]["brand"]
    else:
        assert "filter_recovery_options" in [event["type"] for event in second_events]


def test_contextual_short_cheaper_followup_keeps_product_context():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_short_cheaper_followup",
                message="我想要华为手机，预算8000，拍照优先",
            )
        )
    )
    primary = next(event for event in first_events if event["type"] == "product_item")

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_short_cheaper_followup",
                message="再便宜点的呢？",
            )
        )
    )

    states = [event for event in second_events if event["type"] == "assistant_state"]
    product_events = [event for event in second_events if event["type"] == "product_item"]
    assert states[0]["intent"] == "product_followup"
    assert agent.sessions.get("demo_short_cheaper_followup").last_plan.hard_constraints.include_brands == ["华为"]
    if product_events:
        assert all(event["product"]["sub_category"] == primary["product"]["sub_category"] for event in product_events)
        assert all(event["product"]["price"] < primary["product"]["price"] for event in product_events)
        for event in product_events:
            product = event["product"]
            brand = product["brand"]
            name = product["name"]
            text = f"{brand} {name}".lower()
            assert "华为" in text or "huawei" in text
    else:
        assert "filter_recovery_options" in [event["type"] for event in second_events]


def test_short_cheaper_followup_without_context_does_not_recommend_random_products():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_short_cheaper_no_context",
                message="再便宜点的呢？",
            )
        )
    )

    event_types = [event["type"] for event in events]
    states = [event for event in events if event["type"] == "assistant_state"]
    assert states[0]["intent"] == "unclear_input"
    assert "product_item" not in event_types
    assert "replacement_product" not in event_types


def test_contextual_followup_except_nike_excludes_nike_aliases():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_except_nike_followup",
                message="我要跑鞋，预算1500",
            )
        )
    )
    assert any(event["type"] == "product_item" for event in first_events)

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_except_nike_followup",
                message="除了耐克还有什么？",
            )
        )
    )

    states = [event for event in second_events if event["type"] == "assistant_state"]
    cards = [
        event["product"]
        for event in second_events
        if event["type"] in {"replacement_product", "product_item"}
    ]
    assert states[0]["intent"] == "product_followup"
    assert cards
    for product in cards:
        text = f"{product['brand']} {product['name']}".lower()
        assert "耐克" not in text
        assert "nike" not in text


def _primary_product_event(events):
    return next(event for event in events if event["type"] == "product_item" and event.get("role") == "primary")


def test_followup_more_expensive_filters_primary_above_focus_price():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    session_id = "demo_followup_more_expensive"

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id=session_id, message="想要一个面霜，送给妈妈")
        )
    )
    first_primary = _primary_product_event(first_events)["product"]

    second_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id=session_id, message="更贵一点的"))
    )

    second_primary = _primary_product_event(second_events)["product"]
    assert second_primary["price"] > first_primary["price"]
    assert agent.sessions.get(session_id).focus_product_id == second_primary["product_id"]


def test_followup_text_primary_matches_product_card_when_llm_drifts_to_alternative():
    class DriftResponseLLM(FakeLLMClient):
        async def stream_response(self, user_message, plan, ranked_products, focus_product=None):
            if len(ranked_products) > 1:
                yield f"主推{ranked_products[1].product.title}，它看起来更符合。"
            else:
                yield f"主推{ranked_products[0].product.title}。"

    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, DriftResponseLLM())
    session_id = "demo_followup_primary_drift_guard"

    asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id=session_id, message="想要一个面霜，送给妈妈")
        )
    )
    followup_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id=session_id, message="更贵一点的"))
    )

    primary = _primary_product_event(followup_events)["product"]
    text = "".join(event.get("text", "") for event in followup_events if event["type"] == "text_delta")
    assert primary["name"] in text
    for event in followup_events:
        if event["type"] == "product_item" and event.get("role") != "primary":
            assert f"主推{event['product']['name']}" not in text
            assert f"优先看「{event['product']['name']}」" not in text


def test_followup_primary_role_focus_and_recommendation_memory_are_same_product():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    session_id = "demo_followup_primary_state_consistency"

    asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id=session_id, message="想要一个面霜，送给妈妈")
        )
    )
    followup_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id=session_id, message="更贵一点的"))
    )

    primary = _primary_product_event(followup_events)["product"]
    context = agent.sessions.get(session_id)
    assert context.focus_product_id == primary["product_id"]
    assert context.last_product_ids[0] == primary["product_id"]
    assert context.last_recommendations[0]["product_id"] == primary["product_id"]
    assert context.last_recommendations[0]["role"] == "primary"


def test_chat_followup_recommendation_emits_standard_product_item_card():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticSelectionLLM(
        semantic_frames=[
            {"intent": "recommend_product"},
            {
                "intent": "product_followup",
                "target": {"reference": "focus_product", "selection_strategy": "primary"},
                "response_goal": "exclude_current_brand",
            },
        ],
        selected_ids=["p_digital_020"],
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_chat_followup_product_item",
                message="推荐一款笔记本电脑，预算10000以内，轻薄便携",
            )
        )
    )
    primary = next(event for event in first_events if event["type"] == "product_item")
    assert "Apple" in primary["product"]["brand"] or "苹果" in primary["product"]["brand"]

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_chat_followup_product_item",
                message="不要 Apple，换一款",
            )
        )
    )

    event_types = [event["type"] for event in second_events]
    product_events = [event for event in second_events if event["type"] == "product_item"]
    assert "products_start" in event_types
    assert product_events
    assert all("Apple" not in event["product"]["brand"] and "苹果" not in event["product"]["brand"] for event in product_events)


def test_chat_followup_explicit_huawei_exclusion_filters_alias_brand():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticSelectionLLM(
        semantic_frames=[
            {"intent": "recommend_product"},
            {
                "intent": "product_followup",
                "target": {"reference": "focus_product", "selection_strategy": "primary"},
                "response_goal": "exclude_current_brand",
            },
        ],
        selected_ids=["p_digital_002"],
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_chat_followup_huawei",
                message="我想要华为手机，预算8000，拍照优先",
            )
        )
    )
    primary = next(event for event in first_events if event["type"] == "product_item")
    assert "华为" in primary["product"]["brand"] or "HUAWEI" in primary["product"]["name"]

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_chat_followup_huawei",
                message="不要华为，换一款",
            )
        )
    )

    cards = [
        event["product"]
        for event in second_events
        if event["type"] in {"replacement_product", "product_item"}
    ]
    states = [event for event in second_events if event["type"] == "assistant_state"]
    assert states[0].get("memory_mode") == "disabled_for_followup"
    if cards:
        for product in cards:
            text = f"{product['brand']} {product['name']}".lower()
            assert "华为" not in text
            assert "huawei" not in text
    else:
        assert "filter_recovery_options" in [event["type"] for event in second_events]


def test_brand_quick_action_names_primary_brand_instead_of_this_brand():
    products = load_products("ecommerce_agent_dataset")
    llm = ProductSelectionLLM(["p_digital_020"])
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_brand_action_names_primary",
                message="推荐一款笔记本电脑，预算10000以内，轻薄便携",
            )
        )
    )

    primary = next(event for event in events if event["type"] == "product_item")
    assert "Apple" in primary["product"]["brand"] or "苹果" in primary["product"]["brand"]
    quick_actions = next(event for event in events if event["type"] == "quick_actions")
    labels = [action["label"] for action in quick_actions["actions"]]
    messages = [action["message"] for action in quick_actions["actions"]]
    assert "不要这个品牌" not in labels
    assert any("不要" in label and ("Apple" in label or "苹果" in label) for label in labels)
    assert any("不要" in message and ("Apple" in message or "苹果" in message) for message in messages)


def test_semantic_llm_receives_focus_product_and_recommendation_summaries():
    products = load_products("ecommerce_agent_dataset")
    llm = ContextRecordingSemanticLLM(
        {"intent": "recommend_product"},
        {
            "intent": "product_followup",
            "target": {"reference": "focus_product", "selection_strategy": "primary"},
            "response_goal": "explain_focus_product",
        },
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_llm_context_payload",
                message="推荐一款手机，预算4000，拍照优先",
            )
        )
    )
    asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_llm_context_payload",
                message="刚刚那个是什么？",
            )
        )
    )

    context_payload = llm.contexts[-1]
    assert context_payload["focus_product"]["product_id"]
    assert context_payload["focus_product"]["title"]
    assert context_payload["focus_product"]["sub_category"] == "智能手机"
    assert context_payload["last_recommendations"][0]["title"]
    assert context_payload["last_intent"] == "recommend_product"


def test_contextual_llm_judge_recovers_followup_when_primary_semantic_parse_is_unclear():
    products = load_products("ecommerce_agent_dataset")
    llm = ContextualFallbackLLM(
        primary_frames=[{"intent": "recommend_product"}],
        contextual_frames=[
            {
                "intent": "product_followup",
                "target": {"reference": "focus_product", "selection_strategy": "primary"},
                "constraint_edits": {"add": {"soft_preferences": {"price_preference": "更便宜"}}},
                "response_goal": "recommend_cheaper_alternative",
            }
        ],
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_contextual_judge",
                message="推荐一款手机，预算4000，拍照优先",
            )
        )
    )
    assert any(event["type"] == "product_item" for event in first_events)

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_contextual_judge",
                message="换个更便宜的",
            )
        )
    )

    states = [event for event in second_events if event["type"] == "assistant_state"]
    assert llm.contextual_calls
    assert states[0]["intent"] == "product_followup"
    assert states[0]["retrieval_mode"] == "product_focus_retrieval"


def test_llm_clients_do_not_expose_legacy_plan_method():
    assert not hasattr(FakeLLMClient(), "plan")
    assert not hasattr(DoubaoLLMClient, "plan")


def test_response_prompt_mentions_primary_and_alternative_differences():
    assert "主推一个" in RESPONSE_SYSTEM_PROMPT
    assert "备选差异" in RESPONSE_SYSTEM_PROMPT


def test_response_evidence_payload_includes_four_allowed_products():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    plan = asyncio.run(
        agent.plan(ChatRequest(type="user_message", session_id="demo_payload_four", message="推荐数码电子产品，预算20000"))
    )
    ranked = [
        RankedProduct(product=item.product, score=item.score, reason=item.reason, evidence=item.evidence, tier=item.tier)
        for item in agent.retrieve_and_rank(plan)[:4]
    ]

    payload = _response_evidence_payload(plan, ranked)

    assert len(payload["allowed_products"]) == 4
    assert payload["selected_primary"] == ranked[0].product.product_id


def test_recommendation_uses_single_intent_compiler_without_llm_plan():
    products = load_products("ecommerce_agent_dataset")
    llm = NoPlannerSemanticLLM(
        {
            "intent": "recommend_product",
            "constraint_edits": {
                "add": {
                    "category": "美妆护肤",
                    "sub_category": "防晒",
                    "exclude_terms": ["酒精"],
                    "exclude_brand_regions": ["日本"],
                    "soft_preferences": {"texture": "清爽"},
                }
            },
            "query_intent": {
                "category": "美妆护肤",
                "sub_category": "防晒",
                "query_terms": ["防晒", "清爽"],
                "soft_preferences": {"texture": "清爽"},
            },
        }
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_single_parse",
                message="推荐防晒霜，但不要含酒精的，也不要日系品牌",
            )
        )
    )

    assert any(event["type"] == "product_item" for event in events)
    context = agent.sessions.get("demo_single_parse")
    assert context.state.constraint_state.hard.sub_category == "防晒"
    assert "酒精" in context.state.constraint_state.hard.exclude_terms
    assert context.state.recommendation_memory.items[0].index == 0


def test_session_state_is_authoritative_for_followup_constraint_edits():
    products = load_products("ecommerce_agent_dataset")
    llm = NoPlannerSemanticLLM(
        {
            "intent": "recommend_product",
            "constraint_edits": {
                "add": {
                    "category": "美妆护肤",
                    "sub_category": "洁面",
                    "exclude_terms": ["酒精"],
                    "soft_preferences": {"skin_type": "油皮"},
                }
            },
            "query_intent": {
                "category": "美妆护肤",
                "sub_category": "洁面",
                "query_terms": ["洗面奶", "油皮"],
                "soft_preferences": {"skin_type": "油皮"},
            },
        },
        {
            "intent": "product_followup",
            "constraint_edits": {
                "add": {"price_max": 100},
                "remove": {"exclude_terms": ["酒精"]},
            },
        },
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_state_followup",
                message="推荐一款适合油皮的洗面奶，不要含酒精",
            )
        )
    )
    asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="product_followup",
                session_id="demo_state_followup",
                message="酒精可以接受，但要100以内",
            )
        )
    )

    context = agent.sessions.get("demo_state_followup")
    hard = context.state.constraint_state.hard
    assert hard.sub_category == "洁面"
    assert hard.price_max == 100
    assert "酒精" not in hard.exclude_terms
    assert context.last_plan.hard_constraints == hard


def test_cart_reference_resolver_ignores_hallucinated_product_id():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticFrameLLM(
        {
            "intent": "cart_operation",
            "cart_operation": {
                "action": "add_to_cart",
                "quantity": 1,
                "target": {
                    "reference": "last_recommendations",
                    "selection_strategy": "primary",
                    "product_id": "p_hallucinated_by_llm",
                },
            },
        }
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())
    cart = CartService(products)

    result = asyncio.run(
        agent.try_handle_cart_message(
            ChatRequest(
                type="user_message",
                session_id="demo_hallucinated_cart",
                message="把刚才那款加入购物车",
            ),
            cart,
        )
    )

    assert result["action"] == "get_cart"
    assert result["product_id"] is None
    assert result["cart"]["items"] == []


def test_recommendation_streams_understanding_before_products_and_quick_actions():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_stream_order",
                message="推荐防晒霜，但不要含酒精的，也不要日系品牌",
            )
        )
    )

    event_types = [event["type"] for event in events]
    assert event_types[0] == "assistant_state"
    state = events[0]
    assert state["intent"] == "recommend_product"
    assert state["retrieval_mode"] == "single"
    assert state["llm_mode"] == "fake"
    assert event_types.index("text_delta") < event_types.index("products_start")
    assert event_types.index("products_done") < event_types.index("quick_actions")
    assert event_types.index("quick_actions") < event_types.index("done")
    quick_actions = next(event for event in events if event["type"] == "quick_actions")
    labels = {action["label"] for action in quick_actions["actions"]}
    assert "更便宜" in labels
    assert "不要这个品牌" not in labels
    assert any(label.startswith("不要") for label in labels)


def test_recovery_without_products_does_not_emit_product_focus_quick_actions():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_no_product_actions",
                message="我想给大学生买一台轻薄笔记本，预算1元以内，不要苹果",
            )
        )
    )

    assert not [event for event in events if event["type"] == "product_item"]
    assert any(event["type"] == "filter_recovery_options" for event in events)
    quick_actions = [event for event in events if event["type"] == "quick_actions"]
    assert not quick_actions


def test_unknown_taxonomy_recovery_does_not_emit_quick_actions():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="demo_towel_no_actions", message="推荐毛巾"))
    )

    assert "filter_recovery_options" in [event["type"] for event in events]
    assert "quick_actions" not in [event["type"] for event in events]


def test_llm_selection_controls_single_product_card_count():
    products = load_products("ecommerce_agent_dataset")
    probe_agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    probe_plan = asyncio.run(
        probe_agent.plan(
            ChatRequest(type="user_message", session_id="demo_select_one_probe", message="推荐数码电子产品，预算20000")
        )
    )
    first_id = probe_agent.retrieve_and_rank(probe_plan)[0].product.product_id
    llm = ProductSelectionLLM([first_id])
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_select_one", message="推荐数码电子产品，预算20000")
        )
    )

    product_events = [event for event in events if event["type"] == "product_item"]
    assert [event["product"]["product_id"] for event in product_events] == [first_id]
    assert product_events[0]["product"]["reason"] == f"LLM选择{first_id}"
    assert llm.candidate_count > 3
    selection_state = [event for event in events if event["type"] == "assistant_state"][-1]
    assert selection_state["selection_mode"] == "llm_selection"
    assert selection_state["candidate_count"] == llm.candidate_count
    assert selection_state["selected_count"] == 1


def test_llm_selection_can_emit_four_relevant_product_cards():
    products = load_products("ecommerce_agent_dataset")
    probe_agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    probe_plan = asyncio.run(
        probe_agent.plan(
            ChatRequest(type="user_message", session_id="demo_select_four_probe", message="推荐数码电子产品，预算20000")
        )
    )
    selected_ids = [item.product.product_id for item in probe_agent.retrieve_and_rank(probe_plan)[:4]]
    llm = ProductSelectionLLM(selected_ids)
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_select_four", message="推荐数码电子产品，预算20000")
        )
    )

    product_ids = [event["product"]["product_id"] for event in events if event["type"] == "product_item"]
    assert product_ids == selected_ids


def test_llm_selection_rejects_out_of_pool_and_hard_constraint_violations():
    products = load_products("ecommerce_agent_dataset")
    over_budget_id = next(product.product_id for product in products if product.sub_category == "精华" and product.price > 100)
    valid_id = next(product.product_id for product in products if product.sub_category == "精华" and product.price <= 100)
    llm = ProductSelectionLLM(["not_in_candidates", over_budget_id, valid_id])
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_select_safe", message="推荐精华，预算100以内")
        )
    )

    product_ids = [event["product"]["product_id"] for event in events if event["type"] == "product_item"]
    assert product_ids == [valid_id]


def test_recommendation_explanation_streams_before_product_cards():
    products = load_products("ecommerce_agent_dataset")
    llm = StreamingResponseLLM()
    agent = ShopGuideAgent(products, llm, FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_stream_chunks",
                message="推荐防晒霜，但不要含酒精的，也不要日系品牌",
            )
        )
    )

    event_types = [event["type"] for event in events]
    products_start_index = event_types.index("products_start")
    streamed_text = [
        event["text"]
        for event in events[:products_start_index]
        if event["type"] == "text_delta"
    ]
    assert streamed_text[-3:] == llm.chunks
    assert not llm.generate_called


def test_recommendation_stream_waits_for_llm_explanation_before_product_cards():
    async def run():
        products = load_products("ecommerce_agent_dataset")
        llm = BlockingResponseLLM()
        agent = ShopGuideAgent(products, llm, FakeRetriever())
        stream = agent.stream_message(
            ChatRequest(
                type="user_message",
                session_id="demo_true_stream",
                message="推荐防晒霜，但不要含酒精的，也不要日系品牌",
            )
        )

        events = []
        for _ in range(10):
            event = await asyncio.wait_for(anext(stream), timeout=0.2)
            events.append(event)
            if event.get("selection_mode") == "llm_selection" and "selected_count" in event:
                break

        pending_event = asyncio.create_task(anext(stream))
        await asyncio.wait_for(llm.generate_started.wait(), timeout=0.2)

        assert [event["type"] for event in events][:2] == ["assistant_state", "assistant_state"]
        assert not any(event["type"] == "product_item" for event in events)
        assert not pending_event.done()

        llm.release_generate.set()
        events.append(await asyncio.wait_for(pending_event, timeout=0.2))
        while True:
            event = await asyncio.wait_for(anext(stream), timeout=0.2)
            events.append(event)
            if event["type"] == "done":
                break

        event_types = [event["type"] for event in events]
        assert event_types.index("products_start") > event_types.index("text_delta")
        assert any(event["type"] == "product_item" for event in events)

    asyncio.run(run())


def test_small_talk_and_unclear_input_use_llm_humanized_text_without_products():
    products = load_products("ecommerce_agent_dataset")
    llm = HumanizedChitchatLLM()
    agent = ShopGuideAgent(products, llm, CountingRetriever(products))

    for index, message in enumerate(["你好", "我是猪"]):
        events = asyncio.run(
            agent.handle_message(
                ChatRequest(type="user_message", session_id=f"demo_human_chitchat_{index}", message=message)
            )
        )
        event_types = [event["type"] for event in events]
        assert "product_item" not in event_types
        assert "clarification_request" not in event_types
        merged_text = "".join(event["text"] for event in events if event["type"] == "text_delta")
        assert merged_text == "我在，你可以慢慢说想买什么。"

    assert llm.messages == [("你好", "small_talk"), ("我是猪", "unclear_input")]


def test_ambiguous_phone_request_asks_clarification_without_products():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_clarify", message="推荐一款手机")
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" in event_types
    assert "product_item" not in event_types
    question = next(event["question"] for event in events if event["type"] == "clarification_request")
    assert "拍照" in question


def test_phone_request_with_budget_and_priority_recommends_without_clarification():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_phone_ready",
                message="推荐一款手机，预算4000，拍照优先",
            )
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" not in event_types
    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    assert all(event["product"]["sub_category"] == "智能手机" for event in product_events)
    assert all(event["product"]["price"] <= 4000 for event in product_events)


def test_clarification_answer_reuses_session_category_and_soft_preference():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_clarify_answer", message="推荐一款手机")
        )
    )
    assert "clarification_request" in [event["type"] for event in first_events]

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_clarify_answer", message="拍照优先，预算4000")
        )
    )

    event_types = [event["type"] for event in second_events]
    assert "clarification_request" not in event_types
    product_events = [event for event in second_events if event["type"] == "product_item"]
    assert product_events
    assert all(event["product"]["sub_category"] == "智能手机" for event in product_events)
    plan = agent.sessions.get("demo_clarify_answer").last_plan
    assert plan.soft_preferences["priority"] == "拍照"


def test_new_taxonomy_request_replaces_pending_clarification_category():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_switch_pending", message="推荐一台笔记本")
        )
    )
    assert "clarification_request" in [event["type"] for event in first_events]

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_switch_pending", message="我想要手机")
        )
    )

    event_types = [event["type"] for event in second_events]
    assert "product_item" not in event_types
    assert "clarification_request" in event_types
    question = next(event["question"] for event in second_events if event["type"] == "clarification_request")
    assert "拍照" in question
    assert "笔记本" not in question
    plan = agent.sessions.get("demo_switch_pending").last_plan
    assert plan.hard_constraints.sub_category == "智能手机"


def test_clarification_preference_answer_inherits_pending_category():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_pending_answer", message="推荐一台笔记本")
        )
    )
    assert "clarification_request" in [event["type"] for event in first_events]

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_pending_answer", message="性价比优先，预算5000以内")
        )
    )

    event_types = [event["type"] for event in second_events]
    assert "clarification_request" not in event_types
    product_events = [event for event in second_events if event["type"] == "product_item"]
    if product_events:
        assert all(event["product"]["sub_category"] == "笔记本电脑" for event in product_events)
        assert all(event["product"]["price"] <= 5000 for event in product_events)
    else:
        assert "filter_recovery_options" in event_types
    plan = agent.sessions.get("demo_pending_answer").last_plan
    assert plan.hard_constraints.sub_category == "笔记本电脑"
    assert plan.soft_preferences["priority"] == "性价比"


def test_clarification_option_preference_does_not_add_hidden_budget():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_pending_no_hidden_budget", message="我要一个笔记本电脑")
        )
    )
    clarification = next(event for event in first_events if event["type"] == "clarification_request")
    value_option = next(option for option in clarification["options"] if option["label"] == "性价比")
    assert "预算" not in value_option["message"]
    assert "5000" not in value_option["message"]

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_pending_no_hidden_budget",
                message=value_option["message"],
            )
        )
    )

    assert "clarification_request" not in [event["type"] for event in second_events]
    plan = agent.sessions.get("demo_pending_no_hidden_budget").last_plan
    assert plan.hard_constraints.sub_category == "笔记本电脑"
    assert plan.hard_constraints.price_max is None
    assert plan.soft_preferences["priority"] == "性价比"


def test_explicit_budget_in_clarification_answer_is_still_hard_constraint():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_pending_explicit_budget", message="我要一个笔记本电脑")
        )
    )
    asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_pending_explicit_budget", message="性价比优先，预算5000以内")
        )
    )

    plan = agent.sessions.get("demo_pending_explicit_budget").last_plan
    assert plan.hard_constraints.price_max == 5000
    assert plan.soft_preferences["priority"] == "性价比"


def test_ambiguous_laptop_request_asks_clarification_without_products():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_laptop_clarify", message="推荐一台笔记本")
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" in event_types
    assert "product_item" not in event_types
    question = next(event["question"] for event in events if event["type"] == "clarification_request")
    assert "轻薄" in question


def test_ambiguous_computer_request_asks_clarification_without_products():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_computer_clarify", message="我要一个电脑")
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" in event_types
    assert "product_item" not in event_types
    question = next(event["question"] for event in events if event["type"] == "clarification_request")
    assert "轻薄" in question
    plan = agent.sessions.get("demo_computer_clarify").last_plan
    assert plan.hard_constraints.sub_category == "笔记本电脑"


def test_generic_shoe_request_after_computer_pending_switches_task():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_computer_to_shoe", message="我要一个电脑")
        )
    )
    assert "clarification_request" in [event["type"] for event in first_events]

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_computer_to_shoe", message="我想要个鞋")
        )
    )

    event_types = [event["type"] for event in second_events]
    assert "product_item" not in event_types
    assert "clarification_request" in event_types
    question = next(event["question"] for event in second_events if event["type"] == "clarification_request")
    assert "笔记本" not in question
    assert "电脑" not in question
    assert any(word in question for word in ["跑步", "篮球", "户外", "通勤"])
    options = next(event["options"] for event in second_events if event["type"] == "clarification_request")
    option_labels = [option["label"] for option in options]
    assert any("跑步" in label for label in option_labels)
    assert any("篮球" in label for label in option_labels)
    plan = agent.sessions.get("demo_computer_to_shoe").last_plan
    assert plan.hard_constraints.category == "服饰运动"
    assert plan.hard_constraints.sub_category is None


def test_rejecting_computer_then_requesting_shoes_clears_pending_computer():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_reject_computer_to_shoe", message="我要一个电脑")
        )
    )
    assert "clarification_request" in [event["type"] for event in first_events]

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_reject_computer_to_shoe",
                message="我不想要笔记本了，我想要个鞋",
            )
        )
    )

    event_types = [event["type"] for event in second_events]
    assert "clarification_request" in event_types
    question = next(event["question"] for event in second_events if event["type"] == "clarification_request")
    assert "笔记本" not in question
    assert "电脑" not in question
    plan = agent.sessions.get("demo_reject_computer_to_shoe").last_plan
    assert plan.hard_constraints.category == "服饰运动"
    assert plan.hard_constraints.sub_category is None


def test_explicit_running_shoes_request_uses_running_shoes_not_generic_shoe_clarification():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_running_shoes", message="我要跑鞋")
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" not in event_types
    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    assert all(event["product"]["sub_category"] == "跑步鞋" for event in product_events)


def test_generic_gift_request_asks_clarification_without_cross_category_cards():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_gift_clarify", message="送女朋友礼物")
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" in event_types
    assert "product_item" not in event_types
    question = next(event["question"] for event in events if event["type"] == "clarification_request")
    assert "预算" in question


def test_generic_skincare_request_asks_clarification_but_specific_essence_does_not():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    generic_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_skincare_clarify", message="推荐护肤品")
        )
    )
    assert "clarification_request" in [event["type"] for event in generic_events]
    assert not any(event["type"] == "product_item" for event in generic_events)

    specific_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_skincare_specific", message="推荐精华，预算100以内")
        )
    )
    assert "clarification_request" not in [event["type"] for event in specific_events]
    product_events = [event for event in specific_events if event["type"] == "product_item"]
    assert product_events
    assert all(event["product"]["sub_category"] == "精华" for event in product_events)
    assert all(event["product"]["price"] <= 100 for event in product_events)


def test_no_match_returns_filter_recovery_options():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_recovery",
                message="推荐防晒霜，但不要含酒精的，也不要日系品牌，1元以内",
            )
        )
    )

    assert "filter_recovery_options" in [event["type"] for event in events]
    recovery = next(event for event in events if event["type"] == "filter_recovery_options")
    labels = [option["label"] for option in recovery["options"]]
    assert any("预算" in label for label in labels)


def test_compare_products_uses_last_recommendations_without_hallucinating():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    initial_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_compare", message="推荐防晒霜")
        )
    )
    product_ids = [
        event["product"]["product_id"] for event in initial_events if event["type"] == "product_item"
    ]
    assert len(product_ids) >= 2

    compare_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_compare", message="第一款和第二款哪个更适合油皮？")
        )
    )

    comparison = next(event for event in compare_events if event["type"] == "comparison_result")
    compared_ids = {item["product_id"] for item in comparison["items"]}
    assert compared_ids == set(product_ids[:2])
    assert comparison["recommendation"]["product_id"] in compared_ids


def test_compare_three_products_returns_structured_dimensions():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    initial_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_compare_three", message="推荐防晒霜")
        )
    )
    product_ids = [
        event["product"]["product_id"] for event in initial_events if event["type"] == "product_item"
    ]
    assert len(product_ids) >= 3

    compare_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_compare_three", message="这三款对比一下")
        )
    )

    comparison = next(event for event in compare_events if event["type"] == "comparison_result")
    compared_ids = [item["product_id"] for item in comparison["items"]]
    assert compared_ids == product_ids[:3]
    assert {"价格", "品牌", "类目", "用户关心点"}.issubset(set(comparison["dimensions"]))
    assert comparison["recommendation"]["product_id"] in compared_ids
    for item in comparison["items"]:
        assert set(comparison["dimensions"]).issubset(set(item["dimension_values"]))
        assert isinstance(item["risk_flags"], list)


def test_reference_can_resolve_first_product_from_previous_previous_recommendation_set():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    laptop_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_reference_history",
                message="推荐笔记本电脑，预算15000，轻薄便携",
            )
        )
    )
    laptop_primary = next(event for event in laptop_events if event["type"] == "product_item")["product"]

    asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_reference_history",
                message="推荐一款手机，预算8000，拍照优先",
            )
        )
    )

    explain_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_reference_history",
                message="上上轮第一款是什么？",
            )
        )
    )

    event_types = [event["type"] for event in explain_events]
    text = "".join(event.get("text", "") for event in explain_events if event["type"] == "text_delta")
    states = [event for event in explain_events if event["type"] == "assistant_state"]
    assert states[0]["intent"] == "product_followup"
    assert "product_item" not in event_types
    assert laptop_primary["name"] in text


def test_unknown_taxonomy_recovery_click_uses_pending_recovery_context():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_pending_recovery", message="我想要飞机")
        )
    )

    assert "filter_recovery_options" in [event["type"] for event in events]
    recovery = next(event for event in events if event["type"] == "filter_recovery_options")
    assert any(option.get("payload", {}).get("recovery_id") for option in recovery["options"])

    recovered = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_pending_recovery",
                message="换个相近需求重新筛",
            )
        )
    )

    states = [event for event in recovered if event["type"] == "assistant_state"]
    assert states[0]["intent"] != "unclear_input"
    assert "product_item" not in [event["type"] for event in recovered]
    assert "filter_recovery_options" in [event["type"] for event in recovered] or "clarification_request" in [
        event["type"] for event in recovered
    ]




def test_price_min_request_uses_recovery_instead_of_generic_phone_clarification():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_price_min_phone",
                message="我想要华为手机，10000元以上的",
            )
        )
    )

    event_types = [event["type"] for event in events]
    context = agent.sessions.get("demo_price_min_phone")
    assert context.last_plan.hard_constraints.price_min == 10000
    assert context.last_plan.hard_constraints.price_max is None
    assert "product_item" not in event_types
    assert "clarification_request" not in event_types
    assert "filter_recovery_options" in event_types
    text = "".join(event.get("text", "") for event in events if event["type"] == "text_delta")
    assert "10000" in text or "1万" in text


def test_price_min_and_price_max_parse_separately():
    products = load_products("ecommerce_agent_dataset")
    high_agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    low_agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    asyncio.run(
        high_agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_price_min_parse", message="推荐手机，预算10000以上")
        )
    )
    high_plan = high_agent.sessions.get("demo_price_min_parse").last_plan
    assert high_plan.hard_constraints.price_min == 10000
    assert high_plan.hard_constraints.price_max is None

    asyncio.run(
        low_agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_price_max_parse", message="推荐手机，预算4000以内")
        )
    )
    low_plan = low_agent.sessions.get("demo_price_max_parse").last_plan
    assert low_plan.hard_constraints.price_min is None
    assert low_plan.hard_constraints.price_max == 4000


def test_price_max_parse_common_upper_bound_phrases():
    products = load_products("ecommerce_agent_dataset")
    phrases = [
        "我想要一杯不超过30元的咖啡",
        "30以内咖啡",
        "预算30买咖啡",
        "低于30元的咖啡",
        "咖啡最多30元",
        "coffee under 30",
    ]

    for index, message in enumerate(phrases):
        agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
        asyncio.run(
            agent.handle_message(
                ChatRequest(type="user_message", session_id=f"demo_price_max_phrase_{index}", message=message)
            )
        )
        plan = agent.sessions.get(f"demo_price_max_phrase_{index}").last_plan
        assert plan.hard_constraints.price_min is None
        assert plan.hard_constraints.price_max == 30


def test_budget_limited_coffee_never_returns_over_budget_products():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_coffee_under_30", message="我想要一杯不超过30元的咖啡")
        )
    )

    product_events = [event for event in events if event["type"] == "product_item"]
    assert all(event["product"]["price"] <= 30 for event in product_events)
    text = "".join(event.get("text", "") for event in events if event["type"] == "text_delta")
    if not product_events:
        assert "30 元以内" in text or "30元以内" in text


def test_product_followup_excludes_named_brand_from_recommendations():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    session_id = "demo_followup_no_nestle"

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id=session_id, message="推荐一款咖啡")
        )
    )
    primary = next(event["product"] for event in first_events if event["type"] == "product_item")

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="product_followup",
                session_id=session_id,
                focus_product_id=primary["product_id"],
                message="不要雀巢，换一款",
            )
        )
    )

    products_after_followup = [
        event["product"]
        for event in second_events
        if event["type"] in {"replacement_product", "product_item"}
    ]
    assert products_after_followup
    assert all("雀巢" not in product["brand"] for product in products_after_followup)
    context = agent.sessions.get(session_id)
    assert "雀巢" in context.last_plan.hard_constraints.exclude_brands


def test_cheaper_followup_does_not_persist_focus_price_as_budget_cap():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    session_id = "demo_cheaper_not_budget"

    initial_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id=session_id, message="推荐一款手机，预算8000，拍照优先")
        )
    )
    visible_products = [event["product"] for event in initial_events if event["type"] == "product_item"]
    assert visible_products
    focus_product = max(visible_products, key=lambda product: product["price"])
    focus_price = focus_product["price"]
    context = agent.sessions.get(session_id)
    context.focus_product_id = focus_product["product_id"]
    context.state.active_focus.product_id = focus_product["product_id"]

    followup_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id=session_id, message="换个更便宜的"))
    )

    context = agent.sessions.get(session_id)
    assert context.last_plan.hard_constraints.price_max == 8000
    assert context.state.constraint_state.hard.price_max == 8000
    product_prices = [event["product"]["price"] for event in followup_events if event["type"] == "product_item"]
    assert product_prices
    assert all(price < focus_price for price in product_prices)
    text = "".join(event.get("text", "") for event in followup_events if event["type"] == "text_delta")
    assert "6999" not in text

def test_compare_index_question_uses_recommendation_event_memory():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    session_id = "demo_compare_index_question"

    initial_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id=session_id, message="推荐一款手机，预算8000，拍照优先")
        )
    )
    product_ids = [event["product"]["product_id"] for event in initial_events if event["type"] == "product_item"]
    assert len(product_ids) >= 3

    compare_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id=session_id, message="第一款和第三款怎么选？"))
    )

    comparison = next(event for event in compare_events if event["type"] == "comparison_result")
    compared_ids = [item["product_id"] for item in comparison["items"]]
    assert compared_ids == [product_ids[0], product_ids[2]]
    assert comparison["dimensions"]
    assert all(item.get("dimension_values") for item in comparison["items"])


def test_compare_previous_products_survives_last_product_ids_single_focus_override():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    session_id = "demo_compare_previous_visible_set"

    initial_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id=session_id, message="推荐一款手机，预算8000，拍照优先")
        )
    )
    product_ids = [event["product"]["product_id"] for event in initial_events if event["type"] == "product_item"]
    assert len(product_ids) >= 3
    context = agent.sessions.get(session_id)
    context.last_product_ids = product_ids[:1]

    compare_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id=session_id, message="对比一下之前的手机"))
    )

    comparison = next(event for event in compare_events if event["type"] == "comparison_result")
    compared_ids = [item["product_id"] for item in comparison["items"]]
    assert compared_ids == product_ids[:3]


def test_compare_above_products_uses_recent_recommendation_set_and_structured_fields():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    initial_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_compare_above", message="推荐防晒霜")
        )
    )
    product_ids = [
        event["product"]["product_id"] for event in initial_events if event["type"] == "product_item"
    ]
    assert len(product_ids) >= 2

    compare_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_compare_above", message="对比以上几款我看看呢？")
        )
    )

    comparison = next(event for event in compare_events if event["type"] == "comparison_result")
    compared_ids = [item["product_id"] for item in comparison["items"]]
    assert compared_ids == product_ids[: min(3, len(product_ids))]
    assert comparison["dimensions"]
    assert all(item.get("dimension_values") for item in comparison["items"])


def test_test_client_renders_structured_comparison_result_fields():
    html = Path("test_client/index.html").read_text(encoding="utf-8")
    package_json = Path("test_client/package.json").read_text(encoding="utf-8")

    assert 'event.type === "comparison_result"' in html
    assert "renderComparison" in html
    assert "dimension_values" in html
    assert "risk_flags" in html
    assert "statComparison" in html
    assert "assertComparison" in html
    assert "收到对比结果" in html
    assert "风险提示" in html
    assert "resolveComparisonWinnerName" in html
    assert "log-comparison" in html
    for required in [
        "comparison_result",
        "renderComparison",
        "dimension_values",
        "risk_flags",
        "statComparison",
        "assertComparison",
    ]:
        assert required in package_json

def test_scenario_bundle_streams_grouped_items():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_bundle",
                message="下周去三亚度假，帮我搭配一套从防晒到穿搭的方案",
            )
        )
    )

    event_types = [event["type"] for event in events]
    assert "bundle_start" in event_types
    assert "bundle_item" in event_types
    assert "bundle_done" in event_types
    groups = {event["group"] for event in events if event["type"] == "bundle_item"}
    assert "防晒护理" in groups


def test_natural_language_cart_actions_resolve_recent_product():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    cart = CartService(products)

    initial_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_nl_cart", message="推荐适合油皮的洗面奶")
        )
    )
    primary = next(event for event in initial_events if event["type"] == "product_item")

    add_result = agent.handle_cart_message(
        ChatRequest(type="user_message", session_id="demo_nl_cart", message="把刚才那款加到购物车"),
        cart,
    )
    assert add_result["cart"]["items"][0]["product_id"] == primary["product"]["product_id"]
    assert add_result["action"] == "add_to_cart"

    update_result = agent.handle_cart_message(
        ChatRequest(type="user_message", session_id="demo_nl_cart", message="数量改成2"),
        cart,
    )
    assert update_result["cart"]["items"][0]["quantity"] == 2
    assert update_result["action"] == "update_quantity"


def test_semantic_cart_operation_targets_cheapest_recent_recommendation():
    products = load_products("ecommerce_agent_dataset")
    llm = SemanticFrameLLM(
        {
            "intent": "cart_operation",
            "cart_operation": {
                "action": "add_to_cart",
                "quantity": 2,
                "target": {
                    "reference": "last_recommendations",
                    "selection_strategy": "cheapest",
                },
            },
        }
    )
    agent = ShopGuideAgent(products, llm, FakeRetriever())
    cart = CartService(products)

    asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_semantic_cart", message="推荐防晒霜")
        )
    )
    context = agent.sessions.get("demo_semantic_cart")
    expected_product_id = min(
        (agent.product_map[product_id] for product_id in context.last_product_ids),
        key=lambda product: product.price,
    ).product_id

    result = asyncio.run(
        agent.try_handle_cart_message(
            ChatRequest(
                type="user_message",
                session_id="demo_semantic_cart",
                message="把刚才推荐里最便宜的加两件到购物车",
            ),
            cart,
        )
    )

    assert result["action"] == "add_to_cart"
    assert result["product_id"] == expected_product_id
    assert result["cart"]["items"][0]["product_id"] == expected_product_id
    assert result["cart"]["items"][0]["quantity"] == 2


def test_cart_service_add_update_checkout():
    products = load_products("ecommerce_agent_dataset")
    cart = CartService(products)
    product_id = products[0].product_id

    cart.add("demo", product_id, 1)
    cart.update_quantity("demo", product_id, 2)
    snapshot = cart.get("demo")

    assert snapshot["items"][0]["quantity"] == 2
    assert snapshot["total_amount"] == products[0].price * 2

    checkout = cart.checkout("demo")
    assert checkout["status"] == "ok"
    assert cart.get("demo")["items"] == []


def test_cart_checkout_order_id_is_unique_per_checkout():
    products = load_products("ecommerce_agent_dataset")
    cart = CartService(products)
    product_id = products[0].product_id

    cart.add("demo_unique_order", product_id, 1)
    first = cart.checkout("demo_unique_order")
    cart.add("demo_unique_order", product_id, 1)
    second = cart.checkout("demo_unique_order")

    assert first["order_id"] != second["order_id"]


def test_evidence_bundle_classifies_support_risk_and_ignored_chunks():
    from backend.app.knowledge_base import build_evidence_bundle

    phone = Product(
        product_id="p_bundle_phone",
        title="影像旗舰测试手机",
        brand="测试手机",
        category="数码电子",
        sub_category="智能手机",
        price=4999.0,
        image_path="",
        marketing_description="影像旗舰，适合夜景拍摄。",
        reviews=[
            {"rating": 5, "content": "夜拍清晰，抓拍速度快，成片很稳。"},
            {"rating": 5, "content": "老公和女儿吃了都觉得很好吃，入口香甜。"},
            {"rating": 5, "content": "物流很快，包装严实，客服回复及时。"},
        ],
        search_text="影像旗舰测试手机 夜拍清晰 抓拍速度快 成片很稳",
    )

    bundle = build_evidence_bundle(phone, ["手机", "拍照"])

    support_text = " ".join(chunk.text for chunk in bundle.support_chunks)
    ignored_text = " ".join(chunk.text for chunk in bundle.ignored_chunks)
    assert "夜拍" in support_text or "抓拍" in support_text
    assert "好吃" in ignored_text
    assert "物流" in ignored_text
    assert bundle.positive_summary != "暂无足够相关评论"
    assert bundle.evidence_score > 0


def test_evidence_bundle_keeps_relevant_risk_chunks():
    from backend.app.knowledge_base import build_evidence_bundle

    products = load_products("ecommerce_agent_dataset")
    product = next(product for product in products if product.product_id == "p_beauty_001")

    bundle = build_evidence_bundle(product, ["敏感肌"])

    risk_text = " ".join(chunk.text for chunk in bundle.risk_chunks)
    assert "泛红" in risk_text or "刺痛" in risk_text or "不适" in risk_text
    assert bundle.negative_summary != "暂无足够相关评论"


def test_ranker_uses_evidence_score_to_prefer_better_supported_product():
    from backend.app.ranker import rank_products

    noisy = Product(
        product_id="p_phone_noisy_support",
        title="A 测试拍照手机",
        brand="测试",
        category="数码电子",
        sub_category="智能手机",
        price=3999.0,
        image_path="",
        marketing_description="拍照手机。",
        reviews=[{"rating": 5, "content": "物流很快，包装严实，客服回复及时。"}],
        search_text="测试拍照手机 智能手机 拍照",
        review_rating=5.0,
    )
    supported = Product(
        product_id="p_phone_relevant_support",
        title="B 测试拍照手机",
        brand="测试",
        category="数码电子",
        sub_category="智能手机",
        price=3999.0,
        image_path="",
        marketing_description="拍照手机。",
        reviews=[{"rating": 5, "content": "夜拍清晰，抓拍速度快，成片很稳。"}],
        search_text="测试拍照手机 智能手机 拍照",
        review_rating=5.0,
    )
    plan = RetrievalPlan(
        retrieval_query="推荐拍照手机",
        hard_constraints=HardConstraints(category="数码电子", sub_category="智能手机"),
        soft_preferences={"priority": "拍照"},
    )

    ranked = rank_products([noisy, supported], plan, retrieval_scores={}, limit=2)

    assert ranked[0].product.product_id == "p_phone_relevant_support"
    assert any("夜拍" in item or "抓拍" in item for item in ranked[0].evidence)
    assert all("物流" not in item for item in ranked[0].evidence)


def test_noise_review_is_filtered_from_product_evidence():
    from backend.app.knowledge_base import product_evidence

    product = Product(
        product_id="p_towel_noise",
        title="柔软吸水毛巾",
        brand="测试品牌",
        category="食品饮料",
        sub_category="毛巾",
        price=39.0,
        image_path="",
        marketing_description="柔软吸水，适合浴后擦拭。",
        reviews=[
            {"rating": 5, "content": "老公和女儿吃了都觉得很好吃，入口香甜。"},
            {"rating": 5, "content": "毛巾柔软厚实，洗完澡擦身体很舒服。"},
        ],
        search_text="柔软吸水毛巾 毛巾柔软厚实 洗完澡擦身体很舒服",
    )

    evidence = product_evidence(product, ["柔软", "吸水"])

    assert any("毛巾柔软" in item for item in evidence)
    assert all("好吃" not in item and "入口" not in item for item in evidence)


def test_sensitive_skin_conflict_review_is_kept_as_risk_evidence():
    from backend.app.knowledge_base import product_evidence

    products = load_products("ecommerce_agent_dataset")
    product = next(product for product in products if product.product_id == "p_beauty_001")

    evidence = product_evidence(product, ["敏感肌"])

    assert any("泛红" in item or "刺痛" in item or "不适" in item for item in evidence)


def test_recommendation_product_card_uses_browser_accessible_image_url():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_product_image_url",
                message="推荐一款手机，预算8000，拍照优先",
            )
        )
    )

    product_event = next(event for event in events if event["type"] == "product_item")
    image_url = product_event["product"]["main_image_url"]
    assert image_url.startswith("/assets/products/")
    assert image_url.endswith(".jpg")
    assert "ecommerce_agent_dataset" not in image_url


def test_brand_phone_request_recommends_without_clarification():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_huawei_direct_recommend",
                message="我要华为手机",
            )
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" not in event_types
    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    for event in product_events:
        product = event["product"]
        assert product["sub_category"] == "智能手机"
        text = f"{product['brand']} {product['name']}".lower()
        assert "华为" in text or "huawei" in text


def test_pending_clarification_answer_wins_over_llm_followup_misroute():
    class MisrouteClarificationLLM(FakeLLMClient):
        async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
            if message == "拍照优先":
                return json.dumps({"intent": "product_followup", "response_goal": "recommend_alternative"}, ensure_ascii=False)
            return "{}"

    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, MisrouteClarificationLLM())
    session_id = "demo_pending_answer_priority"

    first_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id=session_id, message="推荐一款手机"))
    )
    assert "clarification_request" in [event["type"] for event in first_events]

    second_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id=session_id, message="拍照优先"))
    )

    text = "".join(event.get("text", "") for event in second_events if event["type"] == "text_delta")
    assert "缺少可追问商品" not in text
    assert any(event["type"] == "product_item" for event in second_events)
    assert agent.sessions.get(session_id).last_plan.soft_preferences.get("priority") == "拍照"


def test_specific_category_gift_recommends_without_generic_gift_clarification():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_cream_for_mom",
                message="想要一个面霜，送给妈妈",
            )
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" not in event_types
    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    assert all(event["product"]["sub_category"] == "面霜" for event in product_events)
    plan = agent.sessions.get("demo_cream_for_mom").last_plan
    assert plan.soft_preferences.get("recipient") == "长辈"
    assert plan.soft_preferences.get("occasion") == "送礼"


def test_generic_makeup_gift_uses_beauty_category_not_food_or_clothing():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_makeup_for_mom",
                message="想要一个化妆的，送给妈妈",
            )
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" not in event_types
    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    assert all(event["product"]["category"] == "美妆护肤" for event in product_events)
    plan = agent.sessions.get("demo_makeup_for_mom").last_plan
    assert plan.hard_constraints.category == "美妆护肤"
    assert plan.hard_constraints.sub_category is None
    assert plan.soft_preferences.get("recipient") == "长辈"
    assert plan.soft_preferences.get("occasion") == "送礼"


def test_makeup_aliases_resolve_to_beauty_category():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    for index, message in enumerate(["想买化妆品送妈妈", "彩妆送女朋友"]):
        events = asyncio.run(
            agent.handle_message(
                ChatRequest(type="user_message", session_id=f"demo_makeup_alias_{index}", message=message)
            )
        )

        product_events = [event for event in events if event["type"] == "product_item"]
        assert product_events
        assert all(event["product"]["category"] == "美妆护肤" for event in product_events)
        plan = agent.sessions.get(f"demo_makeup_alias_{index}").last_plan
        assert plan.hard_constraints.category == "美妆护肤"


def test_makeup_gift_clarification_answer_keeps_beauty_category():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    context = agent.sessions.get("demo_makeup_gift_pending")
    context.state.pending_clarification = PendingClarification(
        category="美妆护肤",
        sub_category=None,
        question="送礼我需要先确认预算和对象：更偏实用、惊喜感，还是稳妥不踩雷？",
    )
    context.state.constraint_state.hard.category = "美妆护肤"
    context.state.constraint_state.soft = {"recipient": "长辈", "occasion": "送礼"}

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_makeup_gift_pending", message="更有惊喜感")
        )
    )

    event_types = [event["type"] for event in events]
    assert "clarification_request" not in event_types
    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    assert all(event["product"]["category"] == "美妆护肤" for event in product_events)
    plan = agent.sessions.get("demo_makeup_gift_pending").last_plan
    assert plan.hard_constraints.category == "美妆护肤"


def test_makeup_followup_more_expensive_stays_in_beauty_category():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    session_id = "demo_makeup_followup_category_lock"

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id=session_id, message="想要一个化妆的，送给妈妈")
        )
    )
    first_primary = _primary_product_event(first_events)["product"]

    second_events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id=session_id, message="更贵一点的"))
    )

    product_events = [event for event in second_events if event["type"] == "product_item"]
    if product_events:
        assert all(event["product"]["category"] == "美妆护肤" for event in product_events)
        assert product_events[0]["product"]["price"] > first_primary["price"]
    else:
        assert "filter_recovery_options" in [event["type"] for event in second_events]
    plan = agent.sessions.get(session_id).last_plan
    assert plan.hard_constraints.category == "美妆护肤"


def test_generic_gift_without_category_still_clarifies():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id="demo_generic_gift", message="送妈妈礼物")
        )
    )

    assert "clarification_request" in [event["type"] for event in events]


def test_brand_preference_survives_direct_recommendation():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    session_id = "demo_huawei_direct_brand"

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id=session_id,
                message="我要一款华为手机",
            )
        )
    )

    assert "clarification_request" not in [event["type"] for event in events]
    product_events = [event for event in events if event["type"] == "product_item"]
    assert product_events
    assert agent.sessions.get(session_id).last_plan.hard_constraints.include_brands == ["华为"]
    for event in product_events:
        product = event["product"]
        brand = product["brand"]
        name = product["name"]
        text = f"{brand} {name}".lower()
        assert "华为" in text or "huawei" in text


def test_product_item_does_not_expose_raw_evidence_by_default():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_no_card_evidence",
                message="推荐一款手机，预算8000，拍照优先",
            )
        )
    )

    product = next(event["product"] for event in events if event["type"] == "product_item")
    assert "evidence" not in product
    assert product["reason"]


def test_response_payload_uses_review_summary_not_raw_evidence():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    plan = asyncio.run(
        agent.plan(ChatRequest(type="user_message", session_id="demo_review_summary_payload", message="推荐手机，拍照优先"))
    )
    ranked = agent.retrieve_and_rank(plan)[:2]

    payload = _response_evidence_payload(plan, ranked)

    first = payload["allowed_products"][0]
    assert "evidence" not in first
    assert "review_summary" in first
    assert set(first["review_summary"]).issuperset({"positive_summary", "negative_summary", "review_relevance"})


def test_irrelevant_review_is_not_used_in_review_summary():
    from backend.app.knowledge_base import evidence_review_summary

    product = Product(
        product_id="p_phone_noise_review",
        title="影像旗舰测试手机",
        brand="测试手机",
        category="数码电子",
        sub_category="智能手机",
        price=4999.0,
        image_path="",
        marketing_description="影像旗舰，适合夜景拍摄。",
        reviews=[
            {"rating": 5, "content": "夜拍清晰，抓拍速度快，成片很稳。"},
            {"rating": 5, "content": "老公和女儿吃了都觉得很好吃，入口香甜。"},
        ],
        search_text="影像旗舰测试手机 夜拍清晰 抓拍速度快 成片很稳",
    )

    summary = evidence_review_summary(product, ["手机", "拍照"])

    combined = " ".join(str(value) for value in summary.values())
    assert "夜拍" in combined or "抓拍" in combined
    assert "好吃" not in combined
    assert "入口香甜" not in combined


def test_generic_low_relevance_review_is_not_used_in_review_summary():
    from backend.app.knowledge_base import evidence_review_summary, product_evidence

    product = Product(
        product_id="p_phone_generic_review",
        title="影像旗舰测试手机",
        brand="测试手机",
        category="数码电子",
        sub_category="智能手机",
        price=4999.0,
        image_path="",
        marketing_description="影像旗舰，适合夜景拍摄。",
        reviews=[
            {"rating": 5, "content": "物流很快，包装严实，客服回复及时。"},
            {"rating": 5, "content": "夜拍清晰，抓拍速度快，成片很稳。"},
        ],
        search_text="影像旗舰测试手机 夜拍清晰 抓拍速度快 成片很稳",
    )

    evidence = product_evidence(product, ["手机", "拍照"])
    summary = evidence_review_summary(product, ["手机", "拍照"])
    combined = " ".join([*evidence, *[str(value) for value in summary.values()]])

    assert "夜拍" in combined or "抓拍" in combined
    assert "物流" not in combined
    assert "包装严实" not in combined


def test_explain_followup_can_still_use_internal_evidence_text():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    session_id = "demo_explain_internal_evidence"

    first_events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id=session_id,
                message="推荐一款手机，预算8000，拍照优先",
            )
        )
    )
    assert any(event["type"] == "product_item" and "evidence" not in event["product"] for event in first_events)

    second_events = asyncio.run(
        agent.handle_message(
            ChatRequest(type="user_message", session_id=session_id, message="为什么推荐刚刚那个？")
        )
    )

    assert "product_item" not in [event["type"] for event in second_events]
    text = "".join(event.get("text", "") for event in second_events if event["type"] == "text_delta")
    assert "推荐" in text
    assert "评论" in text or "证据" in text or "匹配" in text


def test_default_recommendation_text_starts_with_conclusion():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_conclusion_first_text",
                message="推荐一款手机，预算8000，拍照优先",
            )
        )
    )

    text = "".join(event.get("text", "") for event in events if event["type"] == "text_delta")
    assert text.startswith("**\u7ed3\u8bba\uff1a**")
    assert "\n\n" in text
    assert "**\u4e3b\u63a8\uff1a**" in text
    assert "**\u8bc4\u8bba\u6458\u8981\uff1a**" in text
    assert "**\u4e0b\u4e00\u6b65\uff1a**" in text
    assert "\u5148\u7ed9\u4f60\u4e00\u4e2a\u660e\u786e\u4e3b\u63a8" not in text
def test_named_product_cart_command_resolves_catalog_product():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    cart = CartService(products)

    event = asyncio.run(
        agent.try_handle_cart_message(
            ChatRequest(
                type="user_message",
                session_id="demo_named_product_cart",
                message="将两份雀巢咖啡加入购物车",
            ),
            cart,
        )
    )

    assert event["action"] == "add_to_cart"
    assert event["product_id"] == "p_food_002"
    assert event["cart"]["items"][0]["quantity"] == 2
    assert "雀巢" in event["cart"]["items"][0]["name"]


def test_named_alternative_phone_cart_command_uses_mentioned_product_not_focus():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    cart = CartService(products)
    context = agent.sessions.get("demo_phone_cart_binding")
    context.focus_product_id = "p_digital_016"
    context.last_product_ids = ["p_digital_016", "p_digital_008"]
    context.state.recommendation_memory.items = [
        RecommendationMemoryItem(product_id="p_digital_016", role="primary", index=0),
        RecommendationMemoryItem(product_id="p_digital_008", role="alternative", index=1),
    ]

    event = asyncio.run(
        agent.try_handle_cart_message(
            ChatRequest(
                type="user_message",
                session_id="demo_phone_cart_binding",
                message="将小米17ultra加入购物车",
            ),
            cart,
        )
    )

    assert event["action"] == "add_to_cart"
    assert event["product_id"] == "p_digital_008"
    assert event["cart"]["items"][0]["product_id"] == "p_digital_008"
    assert event["cart"]["items"][0]["quantity"] == 1


def test_named_phone_cart_command_resolves_compact_model_alias():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    cart = CartService(products)

    event = asyncio.run(
        agent.try_handle_cart_message(
            ChatRequest(
                type="user_message",
                session_id="demo_phone_compact_alias",
                message="将OPPO Reno16加入购物车",
            ),
            cart,
        )
    )

    assert event["action"] == "add_to_cart"
    assert event["product_id"] == "p_digital_016"
    assert event["cart"]["items"][0]["quantity"] == 1


def test_ambiguous_named_cart_command_does_not_fallback_to_focus_product():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())
    cart = CartService(products)
    context = agent.sessions.get("demo_ambiguous_named_phone")
    context.focus_product_id = "p_digital_016"
    context.last_product_ids = ["p_digital_016", "p_digital_008"]

    event = asyncio.run(
        agent.try_handle_cart_message(
            ChatRequest(
                type="user_message",
                session_id="demo_ambiguous_named_phone",
                message="将小米手机加入购物车",
            ),
            cart,
        )
    )

    assert event["success"] is False
    assert event["action"] == "add_to_cart"
    assert event["product_id"] is None
    assert event["cart"]["items"] == []
    assert "小米" in event["message"]


def test_product_card_includes_dynamic_generated_tags():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient())

    events = asyncio.run(
        agent.handle_message(
            ChatRequest(
                type="user_message",
                session_id="demo_dynamic_product_tags",
                message="推荐一款雀巢咖啡",
            )
        )
    )

    product = next(event["product"] for event in events if event["type"] == "product_item")
    generated = product["derived_attributes"]["generated_tags"]
    generated_values = [item["value"] for item in generated]
    assert generated_values
    assert any(tag in generated_values for tag in ["雀巢", "咖啡", "速溶", "三合一"])
    assert product["tags"] != [product["category"], product["sub_category"], product.get("brand_region")]
