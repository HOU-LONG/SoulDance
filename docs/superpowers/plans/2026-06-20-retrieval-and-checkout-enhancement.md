# SoulDance 里程碑 B：SQLite 交易闭环 + RAG 检索增强实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在坚持 SQLite 作为本阶段唯一数据库的前提下，补齐 Android 地址选择/订单确认流程，并把后端检索升级为 SQLite chunk 表 + BM25 + JSON embedding 向量相似度 + RRF 融合。

**Architecture:** 当前 baseline 已有 SQLite/SQLAlchemy 仓库层，但商品向量仍存放在 `products.embedding` JSON 字段中。本计划先新增 SQLite `product_chunks` 表，embedding 仍用 JSON 存储并在 Python 侧计算相似度；检索模块拆成 lexical/vector/fusion 三个边界，后续仍以 SQLite 为持久化基线。Android 订单流程通过 `/api/order/initiate -> /api/order/addresses -> /api/order/select_address -> /api/order/confirm` 完成，确认下单复用稳定 `idempotency_key`。

**Tech Stack:** Android Kotlin + Jetpack Compose + Retrofit；Python 3.12 + FastAPI + SQLAlchemy + SQLite + rank-bm25 + numpy + sentence-transformers（可选本地 embedding）。

---

## Global Constraints

- 使用 SQLite，不引入 PostgreSQL、pgvector、Docker 或容器化部署。
- 保持 `/health`、`/api/products`、`/api/cart/*`、`/api/order/*`、`/api/stt`、`/ws/chat` 兼容。
- WebSocket 事件类型 `text_delta`、`product_item`、`cart_update`、`done`、`error` 保持兼容。
- Android 不保存 LLM/TTS/STT API key，不实现商品推荐业务规则。
- Android 订单确认必须使用服务端 `confirmation_token`，重试必须复用同一个 `idempotency_key`。
- 后端检索必须保留旧 `EmbeddingRetriever.search()` 的 fallback；SQLite chunk 检索失败或无数据时不影响现有聊天链路。
- 不把 BM25 和 vector 做成同一路结果自融合；RRF 输入必须来自两个独立 ranked list。
- 新增实现遵循 TDD：先写失败测试，再实现，再跑目标测试和回归测试。

---

## Current Baseline Facts

- 当前远端分支为 `feat/postgres-baseline`。
- 当前 DB engine 默认 SQLite：`server/backend/app/db/engine.py`。
- 当前 ORM 商品表为 `server/backend/app/db/models.py::Product`，字段包含 `chunk` 与 JSON `embedding`，但没有 `product_chunks` 表。
- 当前 seed 只把单个商品整体 chunk/embedding 写入 `products`：`server/backend/app/db/seed.py`。
- 当前 Android `CartViewModel.checkout()` 仍走 `/api/cart/checkout` 的一步模拟结算，需改为订单确认流程。

---

## File Structure

### 新增

| 文件 | 职责 |
|------|------|
| `client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiService.kt` | Retrofit 接口与 DTO：订单发起、地址列表、选择地址、确认订单 |
| `client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiClient.kt` | 订单 API 包装、错误解析、DTO -> UI model 映射 |
| `client/app/src/main/java/com/example/shopguideagent/data/model/OrderFlowState.kt` | Android 订单状态机、地址 UI model、订单预览 model |
| `client/app/src/main/java/com/example/shopguideagent/ui/component/AddressSelectionSheet.kt` | 地址选择 BottomSheet |
| `server/backend/app/rag/__init__.py` | RAG 子包导出 |
| `server/backend/app/rag/chunking.py` | 商品细粒度 chunking |
| `server/backend/app/rag/lexical_search.py` | SQLite chunk 查询 + Python BM25 |
| `server/backend/app/rag/vector_search.py` | SQLite JSON embedding 读取 + numpy 相似度 |
| `server/backend/app/rag/fusion.py` | RRF 融合、HybridRetriever |
| `server/tests/test_chunking.py` | chunking 单元测试 |
| `server/tests/test_hybrid_retrieval.py` | SQLite chunk 检索 + RRF 测试 |
| `server/tests/test_order_flow.py` | 后端订单确认状态机集成测试 |

### 修改

| 文件 | 职责 |
|------|------|
| `client/app/src/main/java/com/example/shopguideagent/data/model/Cart.kt` | 删除/保留兼容旧 `CheckoutResult`，增加订单展示需要的模型引用 |
| `client/app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt` | 注入 `OrderApiClient`，新增 `OrderFlowState` 状态流，禁用一步 checkout UI 路径 |
| `client/app/src/main/java/com/example/shopguideagent/ui/component/CheckoutBottomSheet.kt` | 支持订单预览与确认按钮 |
| `client/app/src/main/java/com/example/shopguideagent/ui/screen/CartScreen.kt` | 根据 `orderFlow` 展示地址选择或订单预览 |
| `client/app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.kt` | 覆盖订单流程与幂等键复用 |
| `server/backend/app/db/models.py` | 新增 SQLite `ProductChunk` ORM |
| `server/backend/app/db/seed.py` | seed 细粒度 chunks 与 JSON embeddings |
| `server/backend/app/embedding_retriever.py` | 保持旧接口，新增 query embedding helper 或给 vector search 复用 |
| `server/backend/app/adaptive_retriever.py` | 优先尝试 HybridRetriever，失败/空结果时 fallback 旧链路 |

---

## Task B0: SQLite ProductChunk 表与过渡 Seed

**Files:**
- Modify: `server/backend/app/db/models.py`
- Modify: `server/backend/app/db/seed.py`
- Create: `server/tests/test_sqlite_product_chunks.py`

**Interfaces:**
- Produces: `ProductChunk` ORM, table name `product_chunks`
- Embedding storage: `JSON` list of floats, not pgvector
- Compatibility: `products.chunk` / `products.embedding` 保留，用于旧链路 fallback

- [ ] **Step 1: 写失败测试**

Create `server/tests/test_sqlite_product_chunks.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models import ProductChunk
from backend.app.db.seed import seed_products
from backend.app.models import Product


def test_seed_writes_sqlite_product_chunks():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    products = [
        Product(
            product_id="p1",
            title="Test Cleanser",
            brand="BrandA",
            category="beauty",
            sub_category="cleanser",
            price=99.0,
            image_path="",
            chunk="温和洁面，适合敏感肌。",
            marketing_description="温和清洁。保湿不紧绷。",
            search_text="敏感肌 温和 保湿",
        )
    ]
    with Session(engine) as session:
        seed_products(products, session, embedder=None)
        chunks = session.query(ProductChunk).filter_by(product_id="p1").all()

    assert chunks
    assert chunks[0].content
    assert chunks[0].embedding is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_sqlite_product_chunks.py -q
```

Expected: fails because `ProductChunk` does not exist.

- [ ] **Step 3: 在 `db/models.py` 增加 ProductChunk**

Add imports if missing:

```python
from sqlalchemy import Boolean
```

Add relationship to `Product`:

```python
chunks: Mapped[list["ProductChunk"]] = relationship(
    "ProductChunk",
    back_populates="product",
    cascade="all, delete-orphan",
    lazy="selectin",
)
```

Add model:

```python
class ProductChunk(Base):
    __tablename__ = "product_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: f"chunk_{uuid.uuid4().hex[:12]}",
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sub_category: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    chunk_type: Mapped[str] = mapped_column(String(64), nullable=False, default="description", index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="official_detail")
    trust_level: Mapped[str] = mapped_column(String(32), nullable=False, default="official")
    document_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    product: Mapped[Product] = relationship("Product", back_populates="chunks")
```

- [ ] **Step 4: 修改 `db/seed.py` 写一个过渡 description chunk**

```python
from .models import Product as ProductOrm, ProductChunk, SKU as SkuOrm
```

In `seed_products`, delete old chunks before deleting products:

```python
session.execute(delete(ProductChunk))
session.execute(delete(SkuOrm))
session.execute(delete(ProductOrm))
```

After adding the product row, add:

```python
session.add(ProductChunk(
    chunk_id=f"chunk_{p.product_id}",
    product_id=p.product_id,
    category_id=p.category,
    sub_category=p.sub_category,
    chunk_type="description",
    source_type="fixture",
    trust_level="official",
    document_version=1,
    content=chunk_text,
    embedding=embedding,
))
```

- [ ] **Step 5: 运行测试**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_sqlite_product_chunks.py -q
```

Expected: PASS.

- [ ] **Step 6: 回归 DB 测试**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_cart_db.py tests/test_db_stores.py -q
```

Expected: PASS.

- [ ] **Step 7: 提交**

```bash
git add server/backend/app/db/models.py server/backend/app/db/seed.py server/tests/test_sqlite_product_chunks.py
git commit -m "feat(rag): add SQLite product chunk table"
```

---

## Task B1: Android Order API Client 与订单模型

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiService.kt`
- Create: `client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiClient.kt`
- Create: `client/app/src/main/java/com/example/shopguideagent/data/model/OrderFlowState.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/model/Cart.kt`

**Interfaces:**
- Consumes: `/api/order/initiate`, `/api/order/addresses`, `/api/order/select_address`, `/api/order/confirm`
- Produces: injectable `OrderApiClient`; UI models for address and order flow

- [ ] **Step 1: 写 ViewModel 编译期/单测准备**

Create or update fake order client in `CartViewModelTest.kt` after B2 needs it. For B1, compile is enough.

- [ ] **Step 2: 创建 `OrderFlowState.kt`**

```kotlin
package com.example.shopguideagent.data.model

data class AddressUiModel(
    val addressId: String,
    val name: String,
    val phone: String,
    val province: String,
    val city: String,
    val detail: String,
    val isDefault: Boolean = false,
)

sealed class OrderFlowState {
    data object Idle : OrderFlowState()
    data object Creating : OrderFlowState()
    data class AddressRequired(
        val orderId: String,
        val addresses: List<AddressUiModel>,
        val isLoading: Boolean = false,
        val errorMessage: String? = null,
    ) : OrderFlowState()
    data class OrderPreview(
        val orderId: String,
        val confirmationToken: String,
        val idempotencyKey: String,
        val selectedAddress: AddressUiModel,
        val totalAmount: Double,
        val itemCount: Int,
        val isConfirming: Boolean = false,
    ) : OrderFlowState()
    data class OrderSuccess(val orderId: String, val message: String) : OrderFlowState()
    data class OrderError(val message: String) : OrderFlowState()
}
```

- [ ] **Step 3: 创建 `OrderApiService.kt`**

Use snake_case DTO fields to match current FastAPI/Pydantic request bodies.

```kotlin
package com.example.shopguideagent.data.remote

import com.example.shopguideagent.config.AppConfig
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

interface OrderApiService {
    @POST("/api/order/initiate")
    suspend fun initiate(@Body request: OrderInitiateRequest): OrderResponse

    @GET("/api/order/addresses")
    suspend fun getAddresses(): AddressListResponse

    @POST("/api/order/select_address")
    suspend fun selectAddress(@Body request: SelectAddressRequest): OrderResponse

    @POST("/api/order/confirm")
    suspend fun confirm(@Body request: OrderConfirmRequest): OrderResponse

    companion object {
        fun create(): OrderApiService {
            val httpClient = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .writeTimeout(20, TimeUnit.SECONDS)
                .build()
            return Retrofit.Builder()
                .baseUrl(AppConfig.BASE_HTTP_URL)
                .client(httpClient)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(OrderApiService::class.java)
        }
    }
}

data class OrderInitiateRequest(val session_id: String)
data class SelectAddressRequest(val order_id: String, val address_id: String)
data class OrderConfirmRequest(
    val order_id: String,
    val confirmation_token: String,
    val idempotency_key: String,
)

data class AddressDto(
    val address_id: String,
    val name: String,
    val phone: String,
    val province: String,
    val city: String,
    val detail: String?,
    val is_default: Boolean?,
)

data class AddressListResponse(val addresses: List<AddressDto>?)

data class OrderResponse(
    val order_id: String?,
    val status: String?,
    val total_amount: Double?,
    val confirmation_token: String?,
    val message: String?,
)
```

- [ ] **Step 4: 创建 `OrderApiClient.kt`**

```kotlin
package com.example.shopguideagent.data.remote

import com.example.shopguideagent.data.model.AddressUiModel
import org.json.JSONObject
import retrofit2.HttpException

open class OrderApiClient(private val service: OrderApiService = OrderApiService.create()) {
    open suspend fun initiate(sessionId: String): Result<OrderResponse> = runCatching {
        backendRequest { service.initiate(OrderInitiateRequest(sessionId)) }
    }

    open suspend fun getAddresses(): Result<List<AddressUiModel>> = runCatching {
        backendRequest { service.getAddresses() }.addresses?.map { it.toUiModel() } ?: emptyList()
    }

    open suspend fun selectAddress(orderId: String, addressId: String): Result<OrderResponse> = runCatching {
        backendRequest { service.selectAddress(SelectAddressRequest(orderId, addressId)) }
    }

    open suspend fun confirm(orderId: String, token: String, idempotencyKey: String): Result<OrderResponse> = runCatching {
        backendRequest { service.confirm(OrderConfirmRequest(orderId, token, idempotencyKey)) }
    }

    private suspend fun <T> backendRequest(block: suspend () -> T): T =
        try {
            block()
        } catch (e: HttpException) {
            throw IllegalStateException(e.backendMessage() ?: e.message(), e)
        }

    private fun HttpException.backendMessage(): String? {
        val body = response()?.errorBody()?.string()?.takeIf { it.isNotBlank() } ?: return null
        return runCatching {
            val json = JSONObject(body)
            json.optString("detail").takeIf { it.isNotBlank() }
                ?: json.optString("message").takeIf { it.isNotBlank() }
                ?: json.optString("error").takeIf { it.isNotBlank() }
        }.getOrNull() ?: body
    }

    private fun AddressDto.toUiModel() = AddressUiModel(
        addressId = address_id,
        name = name,
        phone = phone,
        province = province,
        city = city,
        detail = detail ?: "",
        isDefault = is_default ?: false,
    )
}
```

- [ ] **Step 5: 编译验证**

```bash
cd client
./gradlew :app:compileDebugKotlin --no-daemon
```

Expected: BUILD SUCCESSFUL.

- [ ] **Step 6: 提交**

```bash
git add client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiService.kt \
        client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiClient.kt \
        client/app/src/main/java/com/example/shopguideagent/data/model/OrderFlowState.kt \
        client/app/src/main/java/com/example/shopguideagent/data/model/Cart.kt
git commit -m "feat(android): add order API client and flow models"
```

---

## Task B2: Android 订单确认状态机与 UI

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/component/CheckoutBottomSheet.kt`
- Create: `client/app/src/main/java/com/example/shopguideagent/ui/component/AddressSelectionSheet.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/screen/CartScreen.kt`
- Modify: `client/app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.kt`

**Interfaces:**
- Produces: `CartViewModel.orderFlow: StateFlow<OrderFlowState>`
- Keeps: existing `uiState` and `ordersState`
- Removes UI dependency on direct `/api/cart/checkout`

- [ ] **Step 1: 写失败测试：确认订单重试复用同一个 idempotency key**

In `CartViewModelTest.kt`, add a fake `OrderApiClient` that records confirm requests. Test flow:

1. Arrange cart with selected item.
2. Call `startOrderFlow()`.
3. Call `selectAddress("addr_1")`.
4. Call `confirmOrder()` twice after simulating a transient failure then success.
5. Assert both confirm calls use the same `idempotencyKey`.

Run:

```bash
cd client
./gradlew :app:testDebugUnitTest --tests '*CartViewModelTest*' --no-daemon
```

Expected: FAIL because order flow is not implemented.

- [ ] **Step 2: Inject `OrderApiClient`**

Change constructor:

```kotlin
private val orderApiClient: OrderApiClient = OrderApiClient(),
```

Add:

```kotlin
private val _orderFlow = MutableStateFlow<OrderFlowState>(OrderFlowState.Idle)
val orderFlow: StateFlow<OrderFlowState> = _orderFlow.asStateFlow()
```

- [ ] **Step 3: Add `startOrderFlow()`**

Behavior:

- Reject `selectedCount == 0`.
- Set `OrderFlowState.Creating`.
- Call `orderApiClient.initiate(activeSessionId)`.
- Fetch addresses.
- Set `OrderFlowState.AddressRequired`.

- [ ] **Step 4: Add `selectAddress(addressId)`**

Behavior:

- Only works from `AddressRequired`.
- Calls `orderApiClient.selectAddress(orderId, addressId)`.
- Requires nonblank `confirmation_token`.
- Creates stable `idempotencyKey = UUID.randomUUID().toString()`.
- Stores it in `OrderFlowState.OrderPreview`.

- [ ] **Step 5: Add `confirmOrder()`**

Behavior:

- Only works from `OrderPreview`.
- Reuses `current.idempotencyKey` exactly.
- On `status == "completed"`, persist an `OrderUiModel`, remove selected items locally, hide checkout sheet, set `OrderSuccess`.
- On failure, return to `OrderPreview(isConfirming=false)` or `OrderError` without changing the idempotency key.

- [ ] **Step 6: Replace direct checkout UI path**

Update `checkout()` to delegate to `startOrderFlow()` or mark it private and unused. The UI must not call `cartApiClient.checkout(activeSessionId)` for normal checkout.

- [ ] **Step 7: Create `AddressSelectionSheet.kt`**

Use Material 3 `ModalBottomSheet`, list addresses, keep a selected address id, call `onSelectAddress(selectedId)`.

- [ ] **Step 8: Update `CheckoutBottomSheet.kt`**

Add parameter:

```kotlin
orderFlowState: OrderFlowState = OrderFlowState.Idle
```

When `OrderPreview`, render:

- selected address
- selected item count
- total amount
- confirm button with loading state

When `Idle`, keep existing amount view but button text becomes `选择地址并确认`.

- [ ] **Step 9: Update `CartScreen.kt`**

Collect:

```kotlin
val orderFlow by cartViewModel.orderFlow.collectAsState()
```

Show:

- `AddressSelectionSheet` for `AddressRequired`
- `CheckoutBottomSheet(orderFlowState = flow)` for `OrderPreview`
- Existing checkout sheet for `Idle`

- [ ] **Step 10: Run Android tests**

```bash
cd client
./gradlew :app:testDebugUnitTest :app:assembleDebug --no-daemon
```

Expected: BUILD SUCCESSFUL.

- [ ] **Step 11: 提交**

```bash
git add client/app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/component/CheckoutBottomSheet.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/component/AddressSelectionSheet.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/screen/CartScreen.kt \
        client/app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.kt
git commit -m "feat(android): add token-confirmed order flow"
```

---

## Task B3: 细粒度 Chunking 写入 SQLite

**Files:**
- Create: `server/backend/app/rag/__init__.py`
- Create: `server/backend/app/rag/chunking.py`
- Modify: `server/backend/app/db/seed.py`
- Create: `server/tests/test_chunking.py`

**Interfaces:**
- `chunk_product(product: Product, version: int = 1) -> list[ChunkMeta]`
- `ChunkMeta` maps directly to SQLite `ProductChunk`

- [ ] **Step 1: 写失败测试**

Create `server/tests/test_chunking.py` with tests for:

- includes `specification`, `marketing`, `review`, `faq` when source data exists
- every chunk has `product_id`, `category_id`, `document_version`, nonblank content
- long description splits into multiple description chunks

- [ ] **Step 2: Run failing tests**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_chunking.py -q
```

Expected: FAIL because `backend.app.rag.chunking` does not exist.

- [ ] **Step 3: Implement `rag/chunking.py`**

Use a `dataclass ChunkMeta` with:

```python
product_id: str
sku_id: str | None
category_id: str
sub_category: str
chunk_type: str
source_type: str
trust_level: str
document_version: int
content: str
metadata: dict[str, Any]
```

Rules:

- specification: brand/category/sub_category/extracted_terms
- feature: sentence-split `marketing_description`, `trust_level="official"`
- marketing: full `marketing_description`, `trust_level="marketing"`
- review: aggregate reviews by 3-item batches, `trust_level="review_aggregate"`
- faq: one Q/A per chunk
- description: fallback from `product.chunk`, split around 300 chars

- [ ] **Step 4: Update seed to call `chunk_product`**

Replace single transition chunk from B0:

```python
from ..rag.chunking import chunk_product
```

For each `ChunkMeta`, insert `ProductChunk`. Compute JSON embedding only when `embedder.model` is available:

```python
embedding = embedder.model.encode([chunk.content], normalize_embeddings=True).tolist()[0]
```

- [ ] **Step 5: Run tests and seed smoke**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_chunking.py tests/test_sqlite_product_chunks.py -q
../env/venv_shopguide_backend/bin/python -m backend.app.db.seed
```

Verify:

```bash
cd server
../env/venv_shopguide_backend/bin/python - <<'PY'
from sqlalchemy.orm import Session
from backend.app.db import get_engine
from backend.app.db.models import ProductChunk

with Session(get_engine()) as s:
    print("chunks:", s.query(ProductChunk).count())
    print("types:", sorted(t[0] for t in s.query(ProductChunk.chunk_type).distinct().all()))
PY
```

Expected: chunk count is greater than product count; several chunk types exist.

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/rag/__init__.py server/backend/app/rag/chunking.py \
        server/backend/app/db/seed.py server/tests/test_chunking.py
git commit -m "feat(rag): seed fine-grained SQLite product chunks"
```

---

## Task B4: SQLite Hybrid Retrieval + True RRF

**Files:**
- Create: `server/backend/app/rag/lexical_search.py`
- Create: `server/backend/app/rag/vector_search.py`
- Create: `server/backend/app/rag/fusion.py`
- Modify: `server/backend/app/adaptive_retriever.py`
- Modify: `server/backend/app/embedding_retriever.py` if a query embedding helper is needed
- Create: `server/tests/test_hybrid_retrieval.py`

**Interfaces:**
- `lexical_search_chunks(session, query, constraints, top_k) -> list[tuple[str, float]]`
- `vector_search_chunks(session, query_vector, constraints, top_k) -> list[tuple[str, float]]`
- `rrf_fuse(lexical_results, vector_results, top_k) -> list[tuple[str, float]]`
- `HybridRetriever.search(plan, top_k) -> list[tuple[Product, float]]`

- [ ] **Step 1: Write failing tests for RRF**

In `test_hybrid_retrieval.py`:

```python
from backend.app.rag.fusion import rrf_fuse


def test_rrf_uses_two_independent_ranked_lists():
    lexical = [("p1", 10.0), ("p2", 8.0), ("p3", 1.0)]
    vector = [("p2", 0.9), ("p4", 0.8), ("p1", 0.1)]

    fused = rrf_fuse(lexical, vector, top_k=4)

    assert [pid for pid, _ in fused][:2] == ["p2", "p1"]
```

- [ ] **Step 2: Write failing tests for SQLite chunk retrieval**

Use in-memory SQLite, seed `Product` and `ProductChunk` rows manually. Tests:

- lexical search returns product with matching text
- vector search returns product with highest dot product from JSON embedding
- category/sub_category hard filters are applied before scoring

- [ ] **Step 3: Run failing tests**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_hybrid_retrieval.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 4: Implement `lexical_search.py`**

Use SQLAlchemy to load active chunks after hard category/sub_category filters. Use `rank_bm25.BM25Okapi` with the same tokenizer style as `EmbeddingRetriever`. Return best score per `product_id`.

- [ ] **Step 5: Implement `vector_search.py`**

Input query vector is a numpy array. Load chunks with non-null JSON embeddings, compute dot product, normalize scores, return best score per `product_id`.

Do not import pgvector. Do not use PostgreSQL operators.

- [ ] **Step 6: Implement `fusion.py`**

`rrf_fuse()` must accept two separately produced ranked lists. `HybridRetriever` should:

1. open a SQLite/SQLAlchemy session from `get_session()`
2. call lexical search
3. call vector search only if embedding model exists and query vector can be produced
4. RRF fuse
5. map product ids back to existing in-memory `Product`
6. apply existing `constraint_filter.hard_filter`
7. return top K

- [ ] **Step 7: Integrate in `adaptive_retriever.py`**

At the start of `AdaptiveRetriever.search()`:

```python
try:
    from .rag.fusion import HybridRetriever
    hybrid = HybridRetriever(self.retriever)
    results = hybrid.search(plan, top_k=top_k)
    if results:
        return results
except Exception:
    pass
```

Then keep the current relaxed/fallback logic unchanged.

- [ ] **Step 8: Run target and regression tests**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_hybrid_retrieval.py -q
../env/venv_shopguide_backend/bin/python -m pytest tests/test_api.py tests/test_agent_core.py -q
```

Expected: PASS.

- [ ] **Step 9: 提交**

```bash
git add server/backend/app/rag/lexical_search.py server/backend/app/rag/vector_search.py \
        server/backend/app/rag/fusion.py server/backend/app/adaptive_retriever.py \
        server/backend/app/embedding_retriever.py server/tests/test_hybrid_retrieval.py
git commit -m "feat(rag): add SQLite hybrid retrieval with RRF"
```

---

## Task B5: 后端订单状态机集成测试

**Files:**
- Create: `server/tests/test_order_flow.py`

**Interfaces:**
- Validates existing `/api/order/*` contract from Android flow

- [ ] **Step 1: Write tests**

Cover:

- empty cart cannot initiate order
- happy path: add cart -> initiate -> addresses -> select -> confirm
- wrong token returns 400
- same idempotency key returns the same completed order

- [ ] **Step 2: Run tests**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_order_flow.py -q
```

Expected: PASS. If equivalent coverage already exists in `test_commerce_safety.py`, keep only missing cases and avoid duplicate assertions.

- [ ] **Step 3: Run full backend**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: 提交**

```bash
git add server/tests/test_order_flow.py
git commit -m "test: cover confirmed order flow"
```

---

## Task B6: Milestone B 集成验收

**Files:**
- Modify: `docs/api-contract.md` if new Android order behavior needs clarification
- Modify: `docs/realtime-protocol.md` only if WebSocket wording changes

- [ ] **Step 1: Backend verification**

```bash
cd server
../env/venv_shopguide_backend/bin/python -m pytest -q
../env/venv_shopguide_backend/bin/python -m backend.app.db.seed
```

- [ ] **Step 2: Android verification**

```bash
cd client
./gradlew :app:testDebugUnitTest :app:assembleDebug --no-daemon
```

- [ ] **Step 3: Manual order smoke**

Use the generated APK and Cloudflare-backed backend:

1. open cart with selected product
2. tap checkout
3. select address
4. confirm order
5. verify order appears once
6. repeat confirm action after transient failure simulation if possible; verify no duplicate order

- [ ] **Step 4: Manual retrieval smoke**

Run a backend websocket or API test query for:

- explicit model query
- price max constraint
- exclude brand
- sensitive-skin style semantic preference

Expected: no hard-constraint violation; if chunk DB is empty, fallback still returns current behavior.

- [ ] **Step 5: Final commit if docs changed**

```bash
git add docs/api-contract.md docs/realtime-protocol.md
git commit -m "docs: document SQLite order and retrieval milestone"
```

---

## Self-Review

- Android order flow now uses `confirmation_token` and stable `idempotency_key`; direct one-step checkout is no longer the normal UI path.
- SQLite is the explicit database target. No PostgreSQL, pgvector, Docker, or container runtime is required.
- `product_chunks` is an SQLite table with JSON embeddings; vector similarity is computed in Python.
- RRF uses independent lexical and vector ranked lists.
- Old `EmbeddingRetriever.search()` remains as fallback, so `/ws/chat` should keep working if chunk DB is unavailable.
- The plan intentionally does not add a cross-encoder reranker in this milestone. Existing `rank_products()` and feedback-aware ranking remain the final business ranking layer until retrieval metrics justify a new reranker.

---

## Execution Handoff

Plan updated and saved to `docs/superpowers/plans/2026-06-20-retrieval-and-checkout-enhancement.md`.

Execute with superpowers:executing-plans or subagent-driven development. Start from Task B0; do not begin B4 until B0 and B3 have produced real SQLite chunks.
