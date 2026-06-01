import asyncio
import json

from backend.app.agent import ShopGuideAgent
from backend.app.cart import CartService
from backend.app.data_loader import load_products
from backend.app.llm_client import FakeLLMClient
from backend.app.memory_cache import StructuredMemoryCache
from backend.app.models import ChatRequest, Product
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


class SemanticFrameLLM(FakeLLMClient):
    def __init__(self, *frames):
        self.frames = list(frames)

    async def parse_semantic_frame(self, message, context=None, request_type="user_message"):
        if not self.frames:
            return "{}"
        return json.dumps(self.frames.pop(0), ensure_ascii=False)


class NoPlannerSemanticLLM(SemanticFrameLLM):
    def __init__(self, *frames):
        super().__init__(*frames)
        self.plan_calls = 0

    async def plan(self, message, context=None):
        self.plan_calls += 1
        raise AssertionError("main agent flow must not call llm.plan()")


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

    assert llm.plan_calls == 0
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
    assert event_types.index("text_delta") < event_types.index("products_start")
    assert event_types.index("products_done") < event_types.index("quick_actions")
    assert event_types.index("quick_actions") < event_types.index("done")
    quick_actions = next(event for event in events if event["type"] == "quick_actions")
    assert {action["label"] for action in quick_actions["actions"]} >= {"更便宜", "不要这个品牌"}


def test_recommendation_stream_emits_products_before_llm_explanation_finishes():
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
            if event["type"] == "products_done":
                break

        assert [event["type"] for event in events][:2] == ["assistant_state", "text_delta"]
        assert any(event["type"] == "product_item" for event in events)
        assert events[-1]["type"] == "products_done"
        assert not llm.generate_started.is_set()

        llm.release_generate.set()
        while True:
            event = await asyncio.wait_for(anext(stream), timeout=0.2)
            if event["type"] == "done":
                break

    asyncio.run(run())


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
