import asyncio

from backend.app.agent import ShopGuideAgent
from backend.app.cart import CartService
from backend.app.data_loader import load_products
from backend.app.llm_client import FakeLLMClient
from backend.app.models import ChatRequest


class FakeRetriever:
    def search(self, query, top_k=20):
        return []


def _send_turn(agent, session_id, message, *, request_type="user_message", focus_product_id=None):
    return asyncio.run(
        agent.handle_message(
            "anonymous",
            ChatRequest(
                type=request_type,
                session_id=session_id,
                message=message,
                focus_product_id=focus_product_id,
            ),
        )
    )


def _cart_turn(agent, cart, session_id, message):
    return asyncio.run(
        agent.try_handle_cart_message(
            "anonymous",
            ChatRequest(type="user_message", session_id=session_id, message=message),
            cart,
        )
    )


def _products(events):
    return [
        event["product"]
        for event in events
        if event.get("type") in {"product_item", "replacement_product"}
    ]


def _primary_product(events):
    primary = next(
        (
            event["product"]
            for event in events
            if event.get("type") == "product_item" and event.get("role") == "primary"
        ),
        None,
    )
    if primary is not None:
        return primary
    return next((event["product"] for event in events if event.get("type") == "replacement_product"), None)


def _comparison(events):
    return next((event for event in events if event.get("type") == "comparison_result"), None)


def _cart_item(cart_event, product_id):
    if cart_event is None:
        return None
    for item in cart_event.get("cart", {}).get("items", []):
        if item.get("product_id") == product_id:
            return item
    return None


DEMO_TURNS = [
    "我是干性皮肤，想找一款适合秋冬用的保湿精华，预算500以内",
    "有没有便宜一点的替代品？",
    "帮我对比一下雅诗兰黛小棕瓶和刚才那个便宜的",
    "推荐一款6000元左右的小米手机",
    "帮我看看适合办公室喝的咖啡",
    "找一个通勤耳机",
    "回到第一轮那个干皮的精华，有没有同品牌的其他系列？",
    "把第一款加入购物车",
    "查看购物车",
    "把刚才那个换成 50ml 的",
]


def test_five_scene_demo_flow_regression():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    cart = CartService(products)
    session_id = "golden_demo_agent_flow"

    # Turn 1 → Scene 1 (skincare serum recommendation)
    turn1_events = _send_turn(agent, session_id, DEMO_TURNS[0])
    turn1_products = [event["product"] for event in turn1_events if event.get("type") == "product_item"]
    assert turn1_products, f"Turn 1 expected at least one product_item, got {[e.get('type') for e in turn1_events]}"
    turn1_primary = turn1_products[0]
    assert turn1_primary["price"] <= 500, f"Turn 1 primary should respect budget <= 500, got {turn1_primary}"
    assert turn1_primary["category"] in {"美妆护肤", "beauty"}, (
        f"Turn 1 primary category should be beauty, got {turn1_primary['category']}"
    )

    # Turn 2 → Scene 2 (cheaper alternative follow-up)
    turn2_events = _send_turn(agent, session_id, DEMO_TURNS[1])
    turn2_primary = _primary_product(turn2_events)
    assert turn2_primary is not None, (
        f"Turn 2 expected a replacement product, got event types: {[e.get('type') for e in turn2_events]}"
    )
    assert turn2_primary["price"] < turn1_primary["price"], (
        f"Turn 2 should be cheaper than Turn 1 primary ({turn1_primary['price']}), got {turn2_primary}"
    )
    assert turn2_primary["product_id"] != turn1_primary["product_id"], (
        f"Turn 2 should not repeat Turn 1 product, got {turn2_primary['product_id']}"
    )

    # Turn 3 → Scene 3 (named + fuzzy comparison)
    turn3_events = _send_turn(agent, session_id, DEMO_TURNS[2])
    turn3_comparison = _comparison(turn3_events)
    assert turn3_comparison is not None, (
        f"Turn 3 expected comparison_result, got event types: {[e.get('type') for e in turn3_events]}"
    )
    assert set(turn3_comparison.get("product_ids", [])) == {"p_beauty_001", turn2_primary["product_id"]}, (
        f"Turn 3 comparison should compare p_beauty_001 and {turn2_primary['product_id']}, "
        f"got {turn3_comparison.get('product_ids', [])}"
    )

    # Turns 4-6 → unrelated category filler for Scene 4
    _send_turn(agent, session_id, DEMO_TURNS[3])
    _send_turn(agent, session_id, DEMO_TURNS[4])
    _send_turn(agent, session_id, DEMO_TURNS[5])

    # Turn 7 → Scene 4 (long-session reference)
    turn7_events = _send_turn(agent, session_id, DEMO_TURNS[6])
    turn7_products = _products(turn7_events)
    assert turn7_products, (
        f"Turn 7 expected at least one product, got event types: {[e.get('type') for e in turn7_events]}"
    )
    turn7_primary = turn7_products[0]
    assert turn7_primary["category"] == turn1_primary["category"], (
        "Turn 7 should resolve back to the first skincare anchor after unrelated turns, "
        f"got {turn7_primary}"
    )
    assert turn7_primary["brand"] == turn1_primary["brand"], (
        "Turn 7 asks for the same brand's other series and should not bind to the latest unrelated category, "
        f"Turn 1 primary={turn1_primary}, Turn 7 primary={turn7_primary}"
    )
    assert turn7_primary["sub_category"] not in {"智能手机", "咖啡", "耳机"}, (
        f"Turn 7 should not fall back to the latest unrelated category, got {turn7_primary}"
    )

    # Turns 8-10 → Scene 5 (cart add / view / SKU switch)

    # Turn 8: add to cart
    turn8_event = _cart_turn(agent, cart, session_id, DEMO_TURNS[7])
    assert turn8_event is not None, "Turn 8 cart add should produce a result"
    assert turn8_event.get("success") is True, f"Turn 8 cart add should succeed, got {turn8_event}"
    added_product_id = turn8_event["product_id"]
    added_item = _cart_item(turn8_event, added_product_id)
    assert added_item is not None, f"Added product {added_product_id} should be present in cart, got {turn8_event}"
    assert added_item["quantity"] == 1, f"Initial add should set quantity to 1, got {added_item}"

    # Turn 9: view cart
    turn9_event = _cart_turn(agent, cart, session_id, DEMO_TURNS[8])
    assert turn9_event is not None, "Turn 9 cart view should produce a result"
    assert turn9_event.get("action") == "get_cart", f"Turn 9 should be get_cart action, got {turn9_event}"
    assert turn9_event["cart"]["total_count"] == 1, (
        f"Turn 9 cart total_count should be 1, got {turn9_event['cart']}"
    )
    viewed_item = _cart_item(turn9_event, added_product_id)
    assert viewed_item is not None, f"Turn 9 viewed item should exist, got {turn9_event}"
    assert viewed_item["quantity"] == 1, (
        f"View-cart must not increment quantity, got {viewed_item}"
    )

    # Turn 10: SKU update to 50ml
    turn10_event = _cart_turn(agent, cart, session_id, DEMO_TURNS[9])
    assert turn10_event is not None, "Turn 10 SKU update should produce a result"
    turn10_item = _cart_item(turn10_event, added_product_id)
    assert turn10_item is not None, f"Turn 10 updated item should exist, got {turn10_event}"
    selected_sku = turn10_item.get("selected_sku") or turn10_item.get("sku") or turn10_item.get("sku_id")
    assert selected_sku is not None, f"Turn 10 should have a selected SKU, got {turn10_item}"
    # Flexible key matching: SKU property values like "50ml 加大装" contain "50ml"
    if isinstance(selected_sku, dict):
        assert any("50ml" in str(v) for v in selected_sku.values()), (
            f"Turn 10 selected SKU should have a property containing '50ml', got {selected_sku}"
        )
    else:
        assert "50" in str(selected_sku) or "50ml" in str(selected_sku).lower(), (
            f"Turn 10 selected SKU should indicate 50ml, got {selected_sku}"
        )
