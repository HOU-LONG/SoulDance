from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .agent import ShopGuideAgent
from .cart import CartService
from .config import Settings, get_settings
from .concurrency import ConcurrencyGuard
from .data_loader import load_products
from .db import get_session, init_db
from .embedding_retriever import BM25OnlyRetriever, EmbeddingRetriever
from .feedback_aggregator import FeedbackAggregator
from .feedback_ranker import FeedbackAwareRanker
from .feedback_store import FeedbackStore
from .identity import get_current_user_id, is_valid_user_id, ANONYMOUS_USER_ID
from .image_assets import product_image_url_auto as product_image_url
from .llm_client import DoubaoLLMClient, FakeLLMClient, LLMClientWithBreaker
from .memory_cache import RecommendationMemoryCache, StructuredMemoryCache
from .models import CartActionRequest, ChatRequest, FeedbackEvent, OrderActionRequest
from .order_service import OrderError, OrderService
from .rag.fusion import HybridRetriever
from .rag.reranker import build_reranker
from .rag.vector_search import DenseIndex, build_dense_index
from .semantic_layer import rule_semantic_frame
from .realtime_envelope import RealtimeEnvelope
from .session_store import SessionStore
from .stt_adapter import STTAdapter
from .tts_adapter import TTSAdapter
from .user_profile_store import UserProfileStore


from .observability import InMemoryMetrics


def create_app(use_fake_llm: bool = False, use_fake_retriever: bool = False, concurrency_guard: ConcurrencyGuard | None = None) -> FastAPI:
    """构建并装配 ShopGuide 后端 FastAPI 应用。

    按依赖顺序装配各组件：先加载商品数据与 LLM 客户端（生产用 DoubaoLLMClient 并叠加
    熔断包装，测试用 FakeLLMClient），再构建检索器（EmbeddingRetriever / BM25OnlyRetriever）、
    启动时一次性的共享 dense index、HybridRetriever 与重排器，最后组装 ShopGuideAgent、
    购物车、反馈闭环与会话存储，并注册 startup/shutdown 钩子。

    参数：
        use_fake_llm: True 时改用 FakeLLMClient，让测试不依赖真实 LLM API（无 API key 时也会自动启用）。
        use_fake_retriever: True 时改用 BM25OnlyRetriever，跳过向量模型加载，加速测试。
        concurrency_guard: 外部注入的并发限制器；为 None 时按 settings 的上限新建。

    数据库 session 仅在 settings.database_url 存在时创建，并在 shutdown 事件中关闭。
    """
    settings = get_settings()
    products = load_products(settings.dataset_path)
    llm_client = FakeLLMClient() if use_fake_llm or not settings.effective_api_key else DoubaoLLMClient(settings)
    if not isinstance(llm_client, FakeLLMClient):
        llm_client = LLMClientWithBreaker(llm_client)
    retriever = (
        BM25OnlyRetriever(products, config=settings.retrieval_config)
        if use_fake_retriever
        else EmbeddingRetriever(
            products,
            settings.embedding_path,
            settings.embedding_device,
            use_embedding=settings.use_embedding,
            config=settings.retrieval_config,
        )
    )
    # 启动时一次性构建 dense index，由所有检索器共享，避免每次查询循环反序列化。
    dense_index = build_dense_index(products, getattr(retriever, "embeddings", None))
    hybrid_retriever = HybridRetriever(
        retriever,
        config=settings.retrieval_config,
        dense_index=dense_index,
    )
    # 重排器：CrossEncoder 为默认，强场景（comparison/refinement/low-confidence）下回退到
    # LLM 重排，任何失败均静默降级回原序。metrics 与下方 app.state.metrics 复用同一实例，
    # 故在此提前创建；llm_client 直接复用上面已熔断包装的实例，使 HybridReranker 的 LLM 兜底真正生效。
    metrics = InMemoryMetrics()
    reranker = build_reranker(settings, llm_client=llm_client, metrics=metrics)
    memory_cache = StructuredMemoryCache(settings.memory_cache_path or None)
    recommendation_memory = RecommendationMemoryCache(_recommendation_memory_path(settings.memory_cache_path))

    # 数据库 session：database_url 存在时初始化并创建全局 session。
    # 注意：全局共享 session 仅适用于单 worker 演示部署；多 worker / 高并发环境下应改为
    # 请求级 session 或连接池，否则跨请求共享同一 session 存在线程安全问题。
    db_session = None
    if settings.database_url:
        init_db()
        db_session = get_session()

    session_store = SessionStore(settings.session_dir or None, ttl_days=settings.session_ttl_days, db_session=db_session)

    # 反馈闭环
    feedback_store = FeedbackStore(settings.feedback_path or None, db_session=db_session)
    feedback_aggregator = FeedbackAggregator(feedback_store)
    feedback_ranker = FeedbackAwareRanker(feedback_aggregator)
    user_profile_store = UserProfileStore(settings.user_profile_dir or None, db_session=db_session)

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
        hybrid_retriever=hybrid_retriever,
        reranker=reranker,
        settings=settings,
    )
    cart = CartService(products, settings.cart_path or None, db_session=db_session)
    product_map = {product.product_id: product for product in products}
    guard = concurrency_guard or ConcurrencyGuard(
        max_llm_calls=settings.max_llm_calls,
        max_connections=settings.max_connections,
    )

    app = FastAPI(title="SoulDance ShopGuide Agent Backend", version="0.1.0")
    app.state.metrics = metrics

    @app.on_event("shutdown")
    async def _close_db_session():
        if db_session is not None:
            db_session.close()

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
            "observability": metrics.snapshot(),
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
    async def debug_plan(request: ChatRequest, user_id: str = Depends(get_current_user_id)):
        plan = await agent.plan(user_id, request)
        return plan.model_dump(mode="json")

    @app.get("/api/debug/session")
    def debug_session(session_id: str, user_id: str = Depends(get_current_user_id)):
        ctx = agent.sessions.get(user_id, session_id)
        return ctx.model_dump(mode="json")

    @app.get("/api/debug/sessions")
    def debug_sessions():
        return [
            {
                "user_id": uid,
                "session_id": sid,
                "schema_version": ctx.schema_version,
                "last_activity_at": ctx.last_activity_at,
                "turn_index": ctx.state.dialog_state.turn_index,
            }
            for (uid, sid), ctx in agent.sessions._sessions.items()
        ]

    @app.get("/api/sessions/latest")
    def get_latest_session(user_id: str = Depends(get_current_user_id)):
        """获取用户最近使用的会话 ID；如果不存在则返回新的会话 ID，并确保落库。"""
        latest_session_id = session_store.get_latest_session_id(user_id)
        if latest_session_id is None:
            latest_session_id = f"{user_id}_session_default"
            # ensure it exists for subsequent loads
            session_store.get(user_id, latest_session_id)
            session_store.save(user_id, latest_session_id)
        return {"session_id": latest_session_id}

    @app.get("/api/sessions")
    def list_sessions(user_id: str = Depends(get_current_user_id)):
        """返回当前用户的会话列表摘要。"""
        sessions = session_store.list_sessions(user_id)
        return {
            "sessions": [
                {
                    "session_id": ctx.session_id,
                    "title": _session_title(ctx),
                    "updated_at": ctx.last_activity_at,
                    "message_count": len(ctx.display_messages),
                    "preview": _session_preview(ctx),
                }
                for ctx in sessions
            ]
        }

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str, user_id: str = Depends(get_current_user_id)):
        """返回指定会话的详细信息，包括所有展示消息。"""
        ctx = session_store.get(user_id, session_id)
        return {
            "session_id": ctx.session_id,
            "title": _session_title(ctx),
            "updated_at": ctx.last_activity_at,
            "messages": [m.model_dump(mode="json") for m in ctx.display_messages],
        }

    @app.delete("/api/sessions/{session_id}", status_code=204)
    def delete_session(session_id: str, user_id: str = Depends(get_current_user_id)):
        """删除指定会话。"""
        session_store.delete(user_id, session_id)
        return None

    def _session_title(ctx) -> str:
        for m in ctx.display_messages:
            if m.role == "user" and m.text:
                return m.text[:18]
        return "新会话"

    def _session_preview(ctx) -> str:
        for m in reversed(ctx.display_messages):
            if m.role == "assistant" and m.text:
                return m.text[:60]
        return ""

    @app.post("/api/chat")
    async def chat_json(request: ChatRequest, user_id: str = Depends(get_current_user_id)):
        events = [event async for event in agent.stream_message(user_id, request)]
        session_store.save(user_id, request.session_id)
        return events

    @app.websocket("/ws/chat")
    async def chat_ws(websocket: WebSocket):
        await websocket.accept()
        guard.connection_enter()
        active_sessions: set[tuple[str, str]] = set()
        envelope: RealtimeEnvelope | None = None
        # Get user_id from header
        raw_user_id = websocket.headers.get("X-User-Id")
        if raw_user_id is None:
            user_id = ANONYMOUS_USER_ID
        elif not is_valid_user_id(raw_user_id):
            await websocket.close(code=4400)
            return
        else:
            user_id = raw_user_id
        try:
            while True:
                payload = await websocket.receive_json()
                metrics.increment("ws.messages.received")
                request = ChatRequest.model_validate(payload)
                active_sessions.add((user_id, request.session_id))
                envelope = RealtimeEnvelope(session_id=request.session_id)
                await websocket.send_json(envelope.ack())
                metrics.increment("ws.events.sent")

                async def send_cart_tool_events(compiled_ir=None) -> bool:
                    handled = False
                    context = agent.sessions.get(user_id, request.session_id)
                    async for event in agent.tool_registry.execute(
                        "cart_operation",
                        request,
                        context,
                        cart_service=cart,
                        compiled_ir=compiled_ir,
                        user_id=user_id,
                    ):
                        handled = True
                        await websocket.send_json(envelope.wrap(event))
                        metrics.increment("ws.events.sent")
                    if handled:
                        session_store.save(user_id, request.session_id)
                    return handled

                if request.type == "cart_action":
                    await send_cart_tool_events()
                    continue

                compiled_ir = None
                if request.type != "product_followup":
                    rule_frame = rule_semantic_frame(request)
                    if rule_frame.intent == "cart_operation" and rule_frame.cart_operation is not None:
                        if await send_cart_tool_events(rule_frame):
                            continue
                    else:
                        compiled_ir = await agent.compile_intent(user_id, request)
                        if (
                            compiled_ir.intent == "cart_operation"
                            and compiled_ir.cart_operation is not None
                            and await send_cart_tool_events(compiled_ir)
                        ):
                            continue
                async for event in agent.stream_message(user_id, request, compiled_ir):
                    await websocket.send_json(envelope.wrap(event))
                    metrics.increment("ws.events.sent")
                session_store.save(user_id, request.session_id)
        except WebSocketDisconnect:
            for uid, sid in active_sessions:
                session_store.save(uid, sid)
            return
        except Exception as exc:
            if envelope is not None:
                await websocket.send_json(envelope.wrap({"type": "error", "message": str(exc)}))
                metrics.increment("ws.events.sent")
                await websocket.send_json(envelope.wrap({"type": "done"}))
                metrics.increment("ws.events.sent")
            else:
                await websocket.send_json({"type": "error", "message": str(exc)})
                metrics.increment("ws.events.sent")
                await websocket.send_json({"type": "done"})
                metrics.increment("ws.events.sent")
        finally:
            guard.connection_exit()

    @app.get("/api/cart")
    def get_cart(session_id: str, user_id: str = Depends(get_current_user_id)):
        return _cart_success(cart.get(user_id, session_id))

    @app.post("/api/cart/add")
    def cart_add(request: CartActionRequest, user_id: str = Depends(get_current_user_id)):
        return _cart_or_http(
            lambda: _cart_success(
                cart.add(
                    user_id,
                    request.session_id,
                    request.product_id or "",
                    request.quantity,
                    idempotency_key=request.idempotency_key,
                )
            )
        )

    @app.post("/api/cart/update_quantity")
    def cart_update(request: CartActionRequest, user_id: str = Depends(get_current_user_id)):
        return _cart_or_http(
            lambda: _cart_success(cart.update_quantity(user_id, request.session_id, request.product_id or "", request.quantity))
        )

    @app.post("/api/cart/remove")
    def cart_remove(request: CartActionRequest, user_id: str = Depends(get_current_user_id)):
        return _cart_or_http(lambda: _cart_success(cart.remove(user_id, request.session_id, request.product_id or "")))

    @app.post("/api/cart/clear")
    def cart_clear(request: CartActionRequest, user_id: str = Depends(get_current_user_id)):
        return _cart_success(cart.clear(user_id, request.session_id))

    @app.post("/api/cart/checkout")
    def cart_checkout(request: CartActionRequest, user_id: str = Depends(get_current_user_id)):
        snapshot = cart.get(user_id, request.session_id)
        if not snapshot.get("items"):
            raise HTTPException(status_code=400, detail="购物车为空，无法结算。")
        result = cart.checkout(user_id, request.session_id, idempotency_key=request.idempotency_key)
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
    # Feedback endpoints are OUT OF SCOPE for user_id threading per spec.
    # They remain session-only for now.

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

    order_service = OrderService(cart, settings.session_dir or None, db_session=db_session)

    @app.post("/api/order/initiate")
    def order_initiate(request: CartActionRequest, user_id: str = Depends(get_current_user_id)):
        return _order_or_http(lambda: order_service.initiate_checkout(user_id, request.session_id).model_dump(mode="json"))

    @app.get("/api/order/addresses")
    def order_addresses():
        return {"addresses": [a.model_dump(mode="json") for a in order_service.get_addresses()]}

    @app.post("/api/order/select_address")
    def order_select_address(request: OrderActionRequest, user_id: str = Depends(get_current_user_id)):
        return _order_or_http(
            lambda: order_service.select_address(request.order_id, request.address_id or "").model_dump(mode="json")
        )

    @app.post("/api/order/confirm")
    def order_confirm(request: OrderActionRequest, user_id: str = Depends(get_current_user_id)):
        return _order_or_http(
            lambda: order_service.confirm_order(
                user_id,
                request.order_id,
                request.confirmation_token,
                request.idempotency_key,
            ).model_dump(mode="json")
        )

    return app


def _handle_cart_action(cart: CartService, user_id: str, request: ChatRequest) -> dict:
    action = request.action or "add_to_cart"
    if action == "add_to_cart":
        return _cart_success(cart.add(user_id, request.session_id, request.product_id or "", request.quantity))
    if action == "update_quantity":
        return _cart_success(cart.update_quantity(user_id, request.session_id, request.product_id or "", request.quantity))
    if action == "remove":
        return _cart_success(cart.remove(user_id, request.session_id, request.product_id or ""))
    if action == "clear_cart":
        return _cart_success(cart.clear(user_id, request.session_id))
    if action == "checkout":
        snapshot = cart.get(user_id, request.session_id)
        if not snapshot.get("items"):
            return {**_cart_success(snapshot), "success": False, "message": "购物车为空，无法结算。"}
        result = cart.checkout(user_id, request.session_id)
        return {**result, "success": True, "message": "结算成功。", "total": result.get("paid_amount", 0.0)}
    return _cart_success(cart.get(user_id, request.session_id))


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
