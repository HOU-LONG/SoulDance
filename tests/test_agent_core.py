import asyncio

from backend.app.agent import ShopGuideAgent
from backend.app.cart import CartService
from backend.app.data_loader import load_products
from backend.app.llm_client import FakeLLMClient
from backend.app.models import ChatRequest


class FakeRetriever:
    def search(self, query, top_k=20):
        return []


def test_load_products_reads_dataset():
    products = load_products("ecommerce_agent_dataset")

    assert len(products) == 100
    assert products[0].product_id
    assert products[0].title
    assert products[0].chunk


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
