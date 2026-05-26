from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from .agent import ShopGuideAgent
from .cart import CartService
from .config import Settings, get_settings
from .data_loader import load_products
from .embedding_retriever import BM25OnlyRetriever, EmbeddingRetriever
from .llm_client import DoubaoLLMClient, FakeLLMClient
from .models import CartActionRequest, ChatRequest


def create_app(use_fake_llm: bool = False, use_fake_retriever: bool = False) -> FastAPI:
    settings = get_settings()
    products = load_products(settings.dataset_path)
    llm_client = FakeLLMClient() if use_fake_llm or not settings.ark_api_key else DoubaoLLMClient(settings)
    retriever = (
        BM25OnlyRetriever(products)
        if use_fake_retriever
        else EmbeddingRetriever(
            products,
            settings.embedding_path,
            settings.embedding_device,
            use_embedding=settings.use_embedding,
        )
    )
    agent = ShopGuideAgent(products, llm_client, retriever)
    cart = CartService(products)
    product_map = {product.product_id: product for product in products}

    app = FastAPI(title="SoulDance ShopGuide Agent Backend", version="0.1.0")
    app.state.products = products
    app.state.agent = agent
    app.state.cart = cart

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "product_count": len(products),
            "llm": "fake" if isinstance(llm_client, FakeLLMClient) else "doubao",
            "retriever": _retriever_label(retriever),
        }

    @app.get("/api/products")
    def list_products(limit: int = 20):
        return {"products": [_product_summary(product) for product in products[:limit]]}

    @app.get("/api/products/{product_id}")
    def get_product(product_id: str):
        product = product_map.get(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="product not found")
        return product.model_dump(mode="json")

    @app.post("/api/debug/retrieval_plan")
    async def debug_plan(request: ChatRequest):
        plan = await agent.plan(request)
        return plan.model_dump(mode="json")

    @app.websocket("/ws/chat")
    async def chat_ws(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                payload = await websocket.receive_json()
                request = ChatRequest.model_validate(payload)
                if request.type == "cart_action":
                    event = _handle_cart_action(cart, request)
                    await websocket.send_json({"type": "cart_update", "action": request.action or "add_to_cart", "cart": event})
                    await websocket.send_json({"type": "done"})
                    continue
                if agent.is_natural_language_cart_request(request):
                    event = agent.handle_cart_message(request, cart)
                    await websocket.send_json({"type": "cart_update", **event})
                    await websocket.send_json({"type": "done"})
                    continue
                async for event in agent.stream_message(request):
                    await websocket.send_json(event)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})

    @app.get("/api/cart")
    def get_cart(session_id: str):
        return cart.get(session_id)

    @app.post("/api/cart/add")
    def cart_add(request: CartActionRequest):
        return cart.add(request.session_id, request.product_id or "", request.quantity)

    @app.post("/api/cart/update_quantity")
    def cart_update(request: CartActionRequest):
        return cart.update_quantity(request.session_id, request.product_id or "", request.quantity)

    @app.post("/api/cart/remove")
    def cart_remove(request: CartActionRequest):
        return cart.remove(request.session_id, request.product_id or "")

    @app.post("/api/cart/clear")
    def cart_clear(request: CartActionRequest):
        return cart.clear(request.session_id)

    @app.post("/api/cart/checkout")
    def cart_checkout(request: CartActionRequest):
        return cart.checkout(request.session_id)

    return app


def _handle_cart_action(cart: CartService, request: ChatRequest) -> dict:
    action = request.action or "add_to_cart"
    if action == "add_to_cart":
        return cart.add(request.session_id, request.product_id or "", request.quantity)
    if action == "update_quantity":
        return cart.update_quantity(request.session_id, request.product_id or "", request.quantity)
    if action == "remove":
        return cart.remove(request.session_id, request.product_id or "")
    if action == "checkout":
        return cart.checkout(request.session_id)
    return cart.get(request.session_id)


def _product_summary(product):
    return {
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
        "price": product.price,
        "image_path": product.image_path,
    }


def _retriever_label(retriever) -> str:
    if isinstance(retriever, BM25OnlyRetriever):
        return "bm25"
    if getattr(retriever, "model", None) is None:
        return "bm25"
    return "embedding"


app = create_app()
