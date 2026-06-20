from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .agent import ShopGuideAgent
from .cart import CartService
from .config import Settings, get_settings
from .concurrency import ConcurrencyGuard
from .data_loader import load_products
from .embedding_retriever import BM25OnlyRetriever, EmbeddingRetriever
from .image_assets import product_image_url_auto as product_image_url
from .feedback_aggregator import FeedbackAggregator
from .feedback_ranker import FeedbackAwareRanker
from .feedback_store import FeedbackStore
from .llm_client import DoubaoLLMClient, FakeLLMClient, LLMClientWithBreaker
from .memory_cache import RecommendationMemoryCache, StructuredMemoryCache
from .models import CartActionRequest, ChatRequest, FeedbackEvent, OrderActionRequest
from .order_service import OrderError, OrderService
from .semantic_layer import rule_semantic_frame
from .session_store import SessionStore
from .stt_adapter import STTAdapter
from .tts_adapter import TTSAdapter
from .user_profile_store import UserProfileStore


def create_app(use_fake_llm: bool = False, use_fake_retriever: bool = False, concurrency_guard: ConcurrencyGuard | None = None) -> FastAPI:
    settings = get_settings()
    products = load_products(settings.dataset_path)
    llm_client = FakeLLMClient() if use_fake_llm or not settings.effective_api_key else DoubaoLLMClient(settings)
    if not isinstance(llm_client, FakeLLMClient):
        llm_client = LLMClientWithBreaker(llm_client)
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
    memory_cache = StructuredMemoryCache(settings.memory_cache_path or None)
    recommendation_memory = RecommendationMemoryCache(_recommendation_memory_path(settings.memory_cache_path))
    session_store = SessionStore(settings.session_dir or None, ttl_days=settings.session_ttl_days)

    # 反馈闭环
    feedback_store = FeedbackStore(settings.feedback_path or None)
    feedback_aggregator = FeedbackAggregator(feedback_store)
    feedback_ranker = FeedbackAwareRanker(feedback_aggregator)
    user_profile_store = UserProfileStore(settings.user_profile_dir or None)

    tts = TTSAdapter(settings)
    stt_adapter = STTAdapter(settings)
    agent = ShopGuideAgent(
        products,
        llm_client,
        retriever,
        session_store=session_store,
        tts_adapter=tts,
        memory_cache=memory_cache,
        recommendation_memory=recommendation_memory,
        feedback_ranker=feedback_ranker,
        feedback_store=feedback_store,
        user_profile_store=user_profile_store,
    )
    cart = CartService(products, settings.cart_path or None)
    product_map = {product.product_id: product for product in products}
    guard = concurrency_guard or ConcurrencyGuard(
        max_llm_calls=10,
        max_connections=50,
    )

    app = FastAPI(title="SoulDance ShopGuide Agent Backend", version="0.1.0")

    @app.on_event("startup")
    async def _warmup_llm_connection():
        """预热 LLM API 连接池，避免首次请求的 TCP/TLS 握手延迟。"""
        if isinstance(llm_client, FakeLLMClient):
            return
        try:
            import logging
            _log = logging.getLogger("app.main")
            _ = await llm_client._json_completion([
                {"role": "user", "content": '{"task":"warmup","message":"ping"}'}
            ])
            _log.info("LLM connection pool warmed up")
        except Exception:
            pass

    # CORS: 允许 Android / Web 前端跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # GZip: 压缩响应体，移动网络下减少 60-80% 传输量
    app.add_middleware(GZipMiddleware, minimum_size=256)

    app.mount("/assets/products", StaticFiles(directory=str(settings.dataset_path)), name="product_assets")
    app.state.products = products
    app.state.agent = agent
    app.state.cart = cart
    app.state.concurrency_guard = guard

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "product_count": len(products),
            "llm": "fake" if isinstance(llm_client, FakeLLMClient) else settings.llm_provider,
            "llm_model": settings.effective_model if not isinstance(llm_client, FakeLLMClient) else "fake",
            "retriever": _retriever_label(retriever),
            "memory_cache": memory_cache.stats(),
            "recommendation_memory": recommendation_memory.stats(),
            "structured_rank_cache": memory_cache.stats(),
            "persisted_sessions": len(agent.sessions._sessions),
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

    @app.get("/api/debug/session")
    def debug_session(session_id: str):
        ctx = agent.sessions.get(session_id)
        return ctx.model_dump(mode="json")

    @app.get("/api/debug/sessions")
    def debug_sessions():
        return [
            {
                "session_id": sid,
                "schema_version": ctx.schema_version,
                "last_activity_at": ctx.last_activity_at,
                "turn_index": ctx.state.dialog_state.turn_index,
            }
            for sid, ctx in agent.sessions._sessions.items()
        ]

    @app.websocket("/ws/chat")
    async def chat_ws(websocket: WebSocket):
        await websocket.accept()
        guard.connection_enter()
        active_sessions: set[str] = set()
        try:
            while True:
                payload = await websocket.receive_json()
                request = ChatRequest.model_validate(payload)
                active_sessions.add(request.session_id)
                if request.type == "cart_action":
                    event = agent.execute_cart_action(
                        request.session_id,
                        request.action or "add_to_cart",
                        request.product_id,
                        request.quantity,
                        cart,
                    )
                    await websocket.send_json({"type": "cart_update", **event})
                    await websocket.send_json({"type": "done"})
                    session_store.save(request.session_id)
                    continue
                cart_event = None
                compiled_ir = None
                if request.type != "product_followup":
                    rule_frame = rule_semantic_frame(request)
                    if rule_frame.intent == "cart_operation" and rule_frame.cart_operation is not None:
                        cart_event = await agent.try_handle_cart_message(request, cart, rule_frame)
                    else:
                        compiled_ir = await agent.compile_intent(request)
                        cart_event = await agent.try_handle_cart_message(request, cart, compiled_ir)
                if cart_event is not None:
                    await websocket.send_json({"type": "cart_update", **cart_event})
                    await websocket.send_json({"type": "done"})
                    session_store.save(request.session_id)
                    continue
                async for event in agent.stream_message(request, compiled_ir):
                    await websocket.send_json(event)
                session_store.save(request.session_id)
        except WebSocketDisconnect:
            for sid in active_sessions:
                session_store.save(sid)
            return
        except Exception as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.send_json({"type": "done"})
        finally:
            guard.connection_exit()

    @app.get("/api/cart")
    def get_cart(session_id: str):
        return _cart_success(cart.get(session_id))

    @app.post("/api/cart/add")
    def cart_add(request: CartActionRequest):
        return _cart_or_http(
            lambda: _cart_success(
                cart.add(
                    request.session_id,
                    request.product_id or "",
                    request.quantity,
                    idempotency_key=request.idempotency_key,
                )
            )
        )

    @app.post("/api/cart/update_quantity")
    def cart_update(request: CartActionRequest):
        return _cart_or_http(
            lambda: _cart_success(cart.update_quantity(request.session_id, request.product_id or "", request.quantity))
        )

    @app.post("/api/cart/remove")
    def cart_remove(request: CartActionRequest):
        return _cart_or_http(lambda: _cart_success(cart.remove(request.session_id, request.product_id or "")))

    @app.post("/api/cart/clear")
    def cart_clear(request: CartActionRequest):
        return _cart_success(cart.clear(request.session_id))

    @app.post("/api/cart/checkout")
    def cart_checkout(request: CartActionRequest):
        snapshot = cart.get(request.session_id)
        if not snapshot.get("items"):
            raise HTTPException(status_code=400, detail="购物车为空，无法结算。")
        result = cart.checkout(request.session_id, idempotency_key=request.idempotency_key)
        return {
            **result,
            "success": True,
            "message": "结算成功。",
            "total": result.get("paid_amount", 0.0),
        }

    # ---- 语音输入 API ----

    @app.post("/api/stt")
    async def stt_endpoint(
        audio: UploadFile = File(...),
        session_id: str | None = Form(None),
        audio_format: str = Form("wav"),
    ):
        """语音识别：上传音频文件，返回转写文本。"""
        from .models import STTResponse

        if not settings.stt_enabled:
            raise HTTPException(status_code=503, detail="STT is disabled")

        audio_bytes = await audio.read()
        max_size = settings.stt_max_audio_size_mb * 1024 * 1024
        if len(audio_bytes) > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Audio exceeds {settings.stt_max_audio_size_mb}MB limit",
            )

        try:
            result = await stt_adapter.transcribe(audio_bytes, audio_format)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return STTResponse(**result)

    # ---- 反馈闭环 API ----

    @app.post("/api/feedback")
    def submit_feedback(request: FeedbackEvent):
        """显式反馈: {session_id, signal_type, product_id?, rating?, action_label?}"""
        feedback_store.record(request)
        return {"status": "ok", "total_events": feedback_store.count(request.session_id)}

    @app.get("/api/feedback/{session_id}")
    def get_feedback(session_id: str):
        """获取 session 的聚合反馈信号。"""
        signal = feedback_aggregator.aggregate(session_id)
        return signal.model_dump(mode="json")

    @app.get("/api/feedback/{session_id}/events")
    def get_feedback_events(session_id: str):
        """获取 session 的所有原始反馈事件。"""
        events = feedback_store.get_all_events(session_id)
        return {"session_id": session_id, "events": [e.model_dump(mode="json") for e in events]}

    @app.get("/api/profile/{user_id}")
    def get_user_profile(user_id: str):
        """获取用户长期偏好画像。"""
        profile = user_profile_store.get(user_id)
        ctx = user_profile_store.to_preference_context(user_id)
        return {"profile": profile.model_dump(mode="json"), "preference_context": ctx}

    order_service = OrderService(cart, settings.session_dir or None)

    @app.post("/api/order/initiate")
    def order_initiate(request: CartActionRequest):
        return _order_or_http(lambda: order_service.initiate_checkout(request.session_id).model_dump(mode="json"))

    @app.get("/api/order/addresses")
    def order_addresses():
        return {"addresses": [a.model_dump(mode="json") for a in order_service.get_addresses()]}

    @app.post("/api/order/select_address")
    def order_select_address(request: OrderActionRequest):
        return _order_or_http(
            lambda: order_service.select_address(request.order_id, request.address_id or "").model_dump(mode="json")
        )

    @app.post("/api/order/confirm")
    def order_confirm(request: OrderActionRequest):
        return _order_or_http(
            lambda: order_service.confirm_order(
                request.order_id,
                request.confirmation_token,
                request.idempotency_key,
            ).model_dump(mode="json")
        )

    return app


def _handle_cart_action(cart: CartService, request: ChatRequest) -> dict:
    action = request.action or "add_to_cart"
    if action == "add_to_cart":
        return _cart_success(cart.add(request.session_id, request.product_id or "", request.quantity))
    if action == "update_quantity":
        return _cart_success(cart.update_quantity(request.session_id, request.product_id or "", request.quantity))
    if action == "remove":
        return _cart_success(cart.remove(request.session_id, request.product_id or ""))
    if action == "clear_cart":
        return _cart_success(cart.clear(request.session_id))
    if action == "checkout":
        snapshot = cart.get(request.session_id)
        if not snapshot.get("items"):
            return {**_cart_success(snapshot), "success": False, "message": "购物车为空，无法结算。"}
        result = cart.checkout(request.session_id)
        return {**result, "success": True, "message": "结算成功。", "total": result.get("paid_amount", 0.0)}
    return _cart_success(cart.get(request.session_id))


def _cart_or_http(operation):
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _order_or_http(operation):
    try:
        return operation()
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _cart_success(snapshot: dict) -> dict:
    return {
        **snapshot,
        "success": True,
        "total": snapshot.get("total_amount", snapshot.get("total", 0.0)),
        "message": snapshot.get("message", "ok"),
    }


def _product_summary(product):
    return {
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
        "price": product.price,
        "image_path": product.image_path,
        "main_image_url": product_image_url(product.image_path),
    }



def _recommendation_memory_path(path: str) -> str | None:
    if not path:
        return None
    return path + ".recommendation.jsonl"

def _retriever_label(retriever) -> str:
    if isinstance(retriever, BM25OnlyRetriever):
        return "bm25"
    if getattr(retriever, "model", None) is None:
        return "bm25"
    return "embedding"


app = create_app()
