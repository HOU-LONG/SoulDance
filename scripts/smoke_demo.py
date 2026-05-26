import asyncio
import json
import os

import httpx
import websockets


BASE_URL = os.getenv("SHOPGUIDE_BASE_URL", "http://127.0.0.1:18080")
WS_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/chat"


async def main() -> None:
    async with websockets.connect(WS_URL) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "user_message",
                    "session_id": "demo_session_001",
                    "message": "推荐防晒霜，但不要含酒精的，也不要日系品牌",
                    "input_type": "text",
                    "tts_enabled": False,
                },
                ensure_ascii=False,
            )
        )
        primary_product_id = None
        print("== recommendation events ==")
        while True:
            event = json.loads(await ws.recv())
            print(json.dumps(event, ensure_ascii=False))
            if event.get("type") == "product_item" and event.get("role") == "primary":
                primary_product_id = event["product"]["product_id"]
            if event.get("type") == "done":
                break

        if not primary_product_id:
            raise RuntimeError("No primary product returned")

        await ws.send(
            json.dumps(
                {
                    "type": "product_followup",
                    "session_id": "demo_session_001",
                    "focus_product_id": primary_product_id,
                    "message": "这个有点贵，有没有100以内的？",
                    "tts_enabled": False,
                },
                ensure_ascii=False,
            )
        )
        print("== followup events ==")
        while True:
            event = json.loads(await ws.recv())
            print(json.dumps(event, ensure_ascii=False))
            if event.get("type") in {"focus_done", "done"}:
                break

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20) as client:
        print("== cart flow ==")
        add = await client.post(
            "/api/cart/add",
            json={"session_id": "demo_session_001", "product_id": primary_product_id, "quantity": 1},
        )
        print(add.json())
        update = await client.post(
            "/api/cart/update_quantity",
            json={"session_id": "demo_session_001", "product_id": primary_product_id, "quantity": 2},
        )
        print(update.json())
        checkout = await client.post("/api/cart/checkout", json={"session_id": "demo_session_001"})
        print(checkout.json())


if __name__ == "__main__":
    asyncio.run(main())
