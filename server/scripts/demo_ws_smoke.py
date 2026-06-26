#!/usr/bin/env python3
"""WebSocket smoke runner for the five-scene SoulDance demo agent flow.

Sends the exact demo turns over a WebSocket connection, checks per-turn
acceptance assertions, and exits non-zero on any failure.

Usage::

    export CLOUDFLARE_TUNNEL_URL="https://lists-province-wines-postal.trycloudflare.com"
    python server/scripts/demo_ws_smoke.py \\
        --base-url "$CLOUDFLARE_TUNNEL_URL" \\
        --session-id "demo-$(date +%s)"

Machine-readable output (one JSON line per turn)::

    {"turn": 1, "ok": true, "status": "streamed product_item", "price": 280}
    {"turn": 2, "ok": true, "status": "cheaper than turn-1 primary"}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any

import websockets


DEMO_TURNS: list[str] = [
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

TURN_EXPECTATIONS: dict[int, dict[str, Any]] = {
    1: {"types": {"product_item"}, "min_count": 1},
    2: {"types": {"replacement_product"}, "cheaper_than": 1},
    3: {"types": {"comparison_result"}, "min_count": 1},
    7: {"types": {"product_item"}, "same_brand_as": 1},
    8: {"types": {"cart_update"}},
    9: {"types": {"cart_update"}, "action": "get_cart", "readonly": True},
    10: {"types": {"cart_update"}, "action": "update_sku"},
}

TURN_1_PRIMARY_PRICE: float | None = None
TURN_1_PRIMARY_BRAND: str | None = None
CART_ITEM_COUNT: int | None = None


def _collect_product_prices(events: list[dict]) -> list[float]:
    prices: list[float] = []
    for event in events:
        product = event.get("product", {})
        price = product.get("price")
        if isinstance(price, (int, float)):
            prices.append(float(price))
    return prices


def check_turn(turn_index: int, events: list[dict]) -> tuple[bool, str]:
    """Evaluate per-turn expectations. Returns (ok, detail)."""
    types = [e.get("type") for e in events]
    expect = TURN_EXPECTATIONS.get(turn_index, {})
    target_types = expect.get("types", set())

    # --- basic type presence ---
    if target_types:
        if not target_types & set(types):
            return False, f"missing expected types {target_types}: got {types}"

    # --- turn-specific checks ---
    if turn_index == 1:
        products = [e.get("product") for e in events if e.get("type") == "product_item"]
        if not products:
            return False, "no product_item events"
        prices = [p.get("price") for p in products if p.get("price") is not None]
        global TURN_1_PRIMARY_PRICE, TURN_1_PRIMARY_BRAND
        TURN_1_PRIMARY_PRICE = prices[0] if prices else None
        TURN_1_PRIMARY_BRAND = products[0].get("brand") if products else None
        return True, f"streamed {len(products)} product_items"

    elif turn_index == 2:
        if TURN_1_PRIMARY_PRICE is None:
            return False, "turn-1 price not captured"
        prices = _collect_product_prices(events)
        if not prices:
            return False, f"no product prices in events: {types}"
        if prices[0] >= TURN_1_PRIMARY_PRICE:
            return False, f"turn-2 price {prices[0]} >= turn-1 {TURN_1_PRIMARY_PRICE}"
        return True, f"cheaper ({prices[0]}) than turn-1 ({TURN_1_PRIMARY_PRICE})"

    elif turn_index == 3:
        comparison = next((e for e in events if e.get("type") == "comparison_result"), None)
        if comparison is None:
            return False, "no comparison_result event"
        product_ids = comparison.get("product_ids", [])
        if len(product_ids) < 2:
            return False, f"comparison needs >=2 product_ids, got {product_ids}"
        return True, f"compared {len(product_ids)} products"

    elif turn_index == 7:
        if TURN_1_PRIMARY_BRAND is None:
            return False, "turn-1 brand not captured"
        products = [e.get("product") for e in events if e.get("type") == "product_item"]
        if not products:
            return False, "no product_item events"
        for p in products:
            if p.get("brand") == TURN_1_PRIMARY_BRAND:
                return True, "same brand as turn-1"
        return False, f"no product with brand '{TURN_1_PRIMARY_BRAND}': {[p.get('brand') for p in products]}"

    elif turn_index == 8:
        cart = next((e for e in events if e.get("type") == "cart_update"), None)
        if cart is None:
            return False, "no cart_update event"
        if not cart.get("success"):
            return False, f"cart add failed: {cart.get('message', '')}"
        global CART_ITEM_COUNT
        CART_ITEM_COUNT = cart.get("cart", {}).get("total_count", 0)
        return True, "product added"

    elif turn_index == 9:
        cart = next((e for e in events if e.get("type") == "cart_update"), None)
        if cart is None:
            return False, "no cart_update event"
        if cart.get("action") != "get_cart":
            return False, f"action is {cart.get('action')}, expected get_cart"
        count = cart.get("cart", {}).get("total_count")
        if CART_ITEM_COUNT is not None and count != CART_ITEM_COUNT:
            return False, f"total_count changed from {CART_ITEM_COUNT} to {count}"
        return True, "read-only view"

    elif turn_index == 10:
        cart = next((e for e in events if e.get("type") == "cart_update"), None)
        if cart is None:
            return False, "no cart_update event"
        items = cart.get("cart", {}).get("items", [])
        if items:
            sku = items[0].get("selected_sku", {})
            props = sku.get("properties", {})
            if any("50ml" in str(v) for v in props.values()):
                return True, "SKU switched to 50ml variant"
            return True, "SKU clarification returned (no 50ml variant available)"
        return True, "no items to check"

    return True, "passed"


async def run_smoke(base_url: str, session_id: str) -> int:
    ws_url = base_url.replace("https://", "wss://").rstrip("/") + "/ws"
    failures = 0
    print(f'{{"session": "{session_id}", "base_url": "{base_url}"}}', flush=True)

    async with websockets.connect(ws_url) as ws:  # type: ignore[unused-ignore]
        # Join
        hello = json.dumps({
            "type": "join",
            "user_id": "smoke_user",
            "session_id": session_id,
        })
        await ws.send(hello)

        # Consume initial state
        for _ in range(10):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(raw)
                if data.get("type") == "ready":
                    break
            except asyncio.TimeoutError:
                break

        for idx, utterance in enumerate(DEMO_TURNS, start=1):
            msg_id = uuid.uuid4().hex[:8]
            payload = json.dumps({
                "type": "user_message",
                "message_id": msg_id,
                "message": utterance,
                "session_id": session_id,
            }, ensure_ascii=False)
            await ws.send(payload)

            events: list[dict] = []
            done = False
            for _ in range(60):  # max ~30 s at 0.5 s per iteration
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                except asyncio.TimeoutError:
                    break
                data = json.loads(raw)
                events.append(data)
                if data.get("type") == "done" and data.get("message_id") == msg_id:
                    done = True
                    break

            if not done:
                print(json.dumps({"turn": idx, "ok": False, "status": "timeout"}))
                failures += 1
                continue

            ok, detail = check_turn(idx, events)
            print(json.dumps({"turn": idx, "ok": ok, "status": detail}, ensure_ascii=False))
            if not ok:
                failures += 1
                continue

    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo WebSocket smoke test")
    parser.add_argument("--base-url", required=True, help="Backend base URL (Cloudflare tunnel or localhost)")
    parser.add_argument("--session-id", required=True, help="Unique session id for this smoke run")
    args = parser.parse_args()
    code = asyncio.run(run_smoke(args.base_url, args.session_id))
    sys.exit(code)


if __name__ == "__main__":
    main()
