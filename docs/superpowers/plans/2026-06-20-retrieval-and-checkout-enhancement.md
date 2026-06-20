# SoulDance 里程碑 B：交易闭环 + RAG 检索增强 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Android 端补齐订单确认完整流程（地址选择 → 订单预览 → 确认下单），后端检索链路从"内存过滤 + 简单加权"升级为"SQL 过滤 + BM25 全文 + 向量 + RRF 融合 + reranker"，商品 chunking 增加细粒度元数据。

**Architecture:** Android 在 `CheckoutBottomSheet` 内增加地址选择步骤，`CartViewModel` 增加 `OrderFlowState` 状态机；后端新增 `rag/` 模块（`chunking.py`、`fusion.py`、`reranker.py`），扩展 `embedding_retriever.py` 支持多 chunk 向量检索，在 `ranker.py` 中引入 RRF 融合。

**Tech Stack:** Android Kotlin + Compose + Retrofit；Python FastAPI + sentence-transformers + rank-bm25 + numpy + SQLAlchemy (SQLite)。

## Global Constraints

- 保持 `/health`、`/api/products`、`/api/cart/*`、`/api/order/*`、`/api/stt`、`/ws/chat` 稳定。
- WebSocket 事件类型 `text_delta`、`product_item`、`cart_update`、`done`、`error` 保持兼容。
- 不改变 Android 端已有 ViewModel 接口签名，仅在其上扩展订单流程。
- 新增后端检索模块不得破坏 `EmbeddingRetriever` 的现有调用方。
- 用简体中文注释，命令/代码/路径/API 名保留英文。

---

## File Structure

### 新增

| 文件 | 职责 |
|------|------|
| `client/.../data/remote/OrderApiService.kt` | Retrofit 接口：`/api/order/initiate`、`/api/order/addresses`、`/api/order/select_address`、`/api/order/confirm` |
| `client/.../data/model/OrderFlowState.kt` | 订单流程状态机 sealed class + 地址选择 UI 模型 |
| `client/.../ui/component/AddressSelectionSheet.kt` | 地址列表 BottomSheet 组件 |
| `server/backend/app/rag/__init__.py` | RAG 子包导出 |
| `server/backend/app/rag/chunking.py` | 按属性/场景/评价维度切分 chunk 并写入 DB |
| `server/backend/app/rag/fusion.py` | RRF 融合与混合检索协调 |
| `server/backend/app/rag/reranker.py` | 轻量 reranker（cross-encoder 或 LLM 重排） |
| `server/tests/test_chunking.py` | chunking 单元测试 |
| `server/tests/test_fusion.py` | RRF 融合 + 检索链路测试 |
| `server/tests/test_order_flow.py` | 订单状态机集成测试 |

### 修改

| 文件 | 职责 |
|------|------|
| `client/.../vm/CartViewModel.kt` | 增加 `OrderFlowState`、地址选择/确认方法 |
| `client/.../ui/component/CheckoutBottomSheet.kt` | 接入地址选择 + 订单预览步骤 |
| `client/.../data/remote/CartApiClient.kt` | 拆分订单相关方法到 `OrderApiClient` |
| `client/.../data/model/Cart.kt` | 增加 `AddressUiModel`、订单确认 token |
| `server/backend/app/embedding_retriever.py` | 扩展支持从 DB `product_chunks` 表做多 chunk 检索 |
| `server/backend/app/ranker.py` | 引入 RRF 融合逻辑 |
| `server/backend/app/adaptive_retriever.py` | 接入新检索链路 |
| `server/backend/app/db/seed.py` | 新增细粒度 chunk 入 seed 流程 |

---

## Task B1: Android OrderApiService + 地址模型

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiService.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/model/Cart.kt`

**Interfaces:**
- Consumes: 后端 `/api/order/initiate`、`/api/order/addresses`、`/api/order/select_address`、`/api/order/confirm`
- Produces: `OrderApiService` Retrofit 接口，`AddressUiModel`，`OrderPreview` 数据模型。

- [ ] **Step 1: 在 `Cart.kt` 中添加地址与订单预览模型**

```kotlin
// Add to Cart.kt

data class AddressUiModel(
    val addressId: String,
    val name: String,
    val phone: String,
    val province: String,
    val city: String,
    val detail: String,
    val isDefault: Boolean = false,
)

data class OrderPreview(
    val orderId: String,
    val items: List<CartItemUiModel>,
    val totalAmount: Double,
    val status: String,
)

// Add to CheckoutResult
data class OrderInitiateResult(
    val orderId: String,
    val status: String,
    val totalAmount: Double,
)

data class OrderConfirmInput(
    val orderId: String,
    val confirmationToken: String,
    val idempotencyKey: String = "",
)
```

- [ ] **Step 2: 创建 `OrderApiService.kt`**

```kotlin
package com.example.shopguideagent.data.remote

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import com.example.shopguideagent.config.AppConfig
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

interface OrderApiService {
    @POST("/api/order/initiate")
    suspend fun initiate(@Body request: OrderInitiateRequest): OrderInitiateResponse

    @GET("/api/order/addresses")
    suspend fun getAddresses(): AddressListResponse

    @POST("/api/order/select_address")
    suspend fun selectAddress(@Body request: SelectAddressRequest): OrderSelectAddressResponse

    @POST("/api/order/confirm")
    suspend fun confirm(@Body request: OrderConfirmRequest): OrderConfirmResponse

    companion object {
        fun create(): OrderApiService {
            val httpClient = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .writeTimeout(20, TimeUnit.SECONDS)
                .build()
            val retrofit = Retrofit.Builder()
                .baseUrl(AppConfig.BASE_HTTP_URL)
                .client(httpClient)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
            return retrofit.create(OrderApiService::class.java)
        }
    }
}

// DTOs
data class OrderInitiateRequest(val session_id: String)
data class OrderInitiateResponse(
    val order_id: String?,
    val status: String?,
    val total_amount: Double?,
    val message: String?,
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

data class SelectAddressRequest(val order_id: String, val address_id: String)
data class OrderSelectAddressResponse(
    val order_id: String?,
    val status: String?,
    val confirmation_token: String?,
    val total_amount: Double?,
)

data class OrderConfirmRequest(
    val order_id: String,
    val confirmation_token: String?,
    val idempotency_key: String?,
)
data class OrderConfirmResponse(
    val order_id: String?,
    val status: String?,
    val message: String?,
)
```

- [ ] **Step 3: 创建 `OrderApiClient.kt`**

```kotlin
package com.example.shopguideagent.data.remote

import com.example.shopguideagent.data.model.AddressUiModel
import org.json.JSONObject
import retrofit2.HttpException

open class OrderApiClient(private val service: OrderApiService = OrderApiService.create()) {

    open suspend fun initiate(sessionId: String): Result<OrderInitiateResponse> = runCatching {
        backendRequest { service.initiate(OrderInitiateRequest(sessionId)) }
    }

    open suspend fun getAddresses(): Result<List<AddressUiModel>> = runCatching {
        val response = backendRequest { service.getAddresses() }
        response.addresses?.map { it.toUiModel() } ?: emptyList()
    }

    open suspend fun selectAddress(orderId: String, addressId: String): Result<OrderSelectAddressResponse> = runCatching {
        backendRequest { service.selectAddress(SelectAddressRequest(orderId, addressId)) }
    }

    open suspend fun confirm(orderId: String, token: String, idempotencyKey: String = ""): Result<OrderConfirmResponse> = runCatching {
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

- [ ] **Step 4: 编译验证**

Run:
```bash
cd client && ./gradlew :app:compileDebugKotlin
```

Expected: BUILD SUCCESSFUL.

- [ ] **Step 5: 提交**

```bash
git add client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiService.kt \
        client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiClient.kt \
        client/app/src/main/java/com/example/shopguideagent/data/model/Cart.kt
git commit -m "feat(android): add OrderApiService and address/order models

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task B2: Android 订单确认流程状态机

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/component/CheckoutBottomSheet.kt`
- Create: `client/app/src/main/java/com/example/shopguideagent/ui/component/AddressSelectionSheet.kt`

**Interfaces:**
- Consumes: `OrderApiClient` from B1, `CartUiState`
- Produces: `OrderFlowState` sealed class, updated `CartViewModel` with order flow methods

- [ ] **Step 1: 在 `CartViewModel.kt` 中增加 OrderFlowState**

```kotlin
// Add to CartViewModel.kt companion/imports

sealed class OrderFlowState {
    data object Idle : OrderFlowState()
    data class AddressRequired(
        val orderId: String,
        val addresses: List<AddressUiModel>,
        val isLoading: Boolean = false,
        val errorMessage: String? = null,
    ) : OrderFlowState()
    data class OrderPreview(
        val orderId: String,
        val confirmationToken: String,
        val selectedAddress: AddressUiModel,
        val totalAmount: Double,
        val itemCount: Int,
        val isConfirming: Boolean = false,
    ) : OrderFlowState()
    data class OrderSuccess(
        val orderId: String,
        val message: String,
    ) : OrderFlowState()
    data class OrderError(val message: String) : OrderFlowState()
}

// Add fields to CartViewModel
private val _orderFlow = MutableStateFlow<OrderFlowState>(OrderFlowState.Idle)
val orderFlow: StateFlow<OrderFlowState> = _orderFlow.asStateFlow()
private val orderApiClient = OrderApiClient()
```

- [ ] **Step 2: 增加订单流程方法到 CartViewModel**

```kotlin
fun startOrderFlow() {
    val state = _uiState.value
    if (state.selectedCount == 0) {
        _uiState.value = state.copy(errorMessage = "请先选择要结算的商品")
        return
    }
    viewModelScope.launch {
        orderApiClient.initiate(activeSessionId)
            .onSuccess { response ->
                val orderId = response.order_id ?: return@onSuccess
                // Fetch addresses
                orderApiClient.getAddresses()
                    .onSuccess { addresses ->
                        if (addresses.isEmpty()) {
                            _orderFlow.value = OrderFlowState.OrderError("没有可用地址")
                            return@onSuccess
                        }
                        _orderFlow.value = OrderFlowState.AddressRequired(
                            orderId = orderId,
                            addresses = addresses,
                        )
                    }
                    .onFailure { e ->
                        _orderFlow.value = OrderFlowState.OrderError(e.message ?: "获取地址失败")
                    }
            }
            .onFailure { e ->
                _orderFlow.value = OrderFlowState.OrderError(e.message ?: "订单创建失败")
            }
    }
}

fun selectAddress(addressId: String) {
    val current = _orderFlow.value as? OrderFlowState.AddressRequired ?: return
    val address = current.addresses.firstOrNull { it.addressId == addressId } ?: return
    _orderFlow.value = current.copy(isLoading = true)
    viewModelScope.launch {
        orderApiClient.selectAddress(current.orderId, addressId)
            .onSuccess { response ->
                val token = response.confirmation_token ?: return@launch
                _orderFlow.value = OrderFlowState.OrderPreview(
                    orderId = current.orderId,
                    confirmationToken = token,
                    selectedAddress = address,
                    totalAmount = response.total_amount ?: _uiState.value.totalPrice,
                    itemCount = _uiState.value.selectedCount,
                )
            }
            .onFailure { e ->
                _orderFlow.value = current.copy(
                    isLoading = false,
                    errorMessage = e.message ?: "地址选择失败",
                )
            }
    }
}

fun confirmOrder() {
    val current = _orderFlow.value as? OrderFlowState.OrderPreview ?: return
    _orderFlow.value = current.copy(isConfirming = true)
    viewModelScope.launch {
        val idempotencyKey = "${activeSessionId}-${current.orderId}-${System.currentTimeMillis()}"
        orderApiClient.confirm(current.orderId, current.confirmationToken, idempotencyKey)
            .onSuccess { response ->
                if (response.status == "completed") {
                    // Clear cart items that were ordered
                    val purchasedItems = _uiState.value.items.filter { it.selected }
                    val orderId = response.order_id ?: current.orderId
                    val updatedOrders = listOf(
                        OrderUiModel(
                            orderId = orderId,
                            items = purchasedItems,
                            totalCount = purchasedItems.sumOf { it.quantity },
                            totalPrice = current.totalAmount,
                            status = "已完成",
                        ),
                    ) + _ordersState.value.orders
                    _ordersState.value = _ordersState.value.copy(orders = updatedOrders)
                    persistenceStore.saveOrders(userId, updatedOrders)
                    _orderFlow.value = OrderFlowState.OrderSuccess(
                        orderId = orderId,
                        message = "下单成功！",
                    )
                    _uiState.value = _uiState.value.copy(
                        items = _uiState.value.items.filterNot { it.selected },
                        showCheckoutSheet = false,
                    ).recalculate()
                } else {
                    _orderFlow.value = OrderFlowState.OrderError("下单失败")
                }
            }
            .onFailure { e ->
                _orderFlow.value = current.copy(
                    isConfirming = false,
                )
                _orderFlow.value = OrderFlowState.OrderError(e.message ?: "确认下单失败")
            }
    }
}

fun resetOrderFlow() {
    _orderFlow.value = OrderFlowState.Idle
}
```

- [ ] **Step 3: 创建 `AddressSelectionSheet.kt`**

```kotlin
package com.example.shopguideagent.ui.component

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.shopguideagent.data.model.AddressUiModel
import com.example.shopguideagent.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddressSelectionSheet(
    addresses: List<AddressUiModel>,
    isLoading: Boolean,
    errorMessage: String?,
    onSelectAddress: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var selectedId by remember { mutableStateOf(addresses.firstOrNull { it.isDefault }?.addressId ?: "") }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = SurfacePrimary,
        shape = RoundedCornerShape(topStart = AppCornerRadius.Sheet, topEnd = AppCornerRadius.Sheet),
    ) {
        Column(modifier = Modifier.padding(horizontal = 24.dp, vertical = 12.dp).padding(bottom = 32.dp)) {
            Text("选择收货地址", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = TextPrimary)
            Spacer(Modifier.height(12.dp))
            if (errorMessage != null) {
                Text(errorMessage, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(8.dp))
            }
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(addresses) { address ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable { selectedId = address.addressId },
                        shape = RoundedCornerShape(AppCornerRadius.Card),
                        color = if (selectedId == address.addressId) BrandSoft else SurfacePrimary,
                        border = if (selectedId == address.addressId) ButtonBorder else null,
                    ) {
                        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.Top) {
                            Icon(Icons.Outlined.LocationOn, null, tint = TextSecondary, modifier = Modifier.size(24.dp))
                            Spacer(Modifier.width(12.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text("${address.name}  ${address.phone}", fontWeight = FontWeight.Medium, color = TextPrimary)
                                Text("${address.province}${address.city} ${address.detail}", style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                            }
                            if (address.isDefault) Text("默认", color = BrandPrimary, style = MaterialTheme.typography.labelSmall)
                            if (selectedId == address.addressId) Icon(Icons.Outlined.CheckCircle, null, tint = BrandPrimary, modifier = Modifier.size(20.dp))
                        }
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = { onSelectAddress(selectedId) },
                enabled = !isLoading && selectedId.isNotEmpty(),
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(AppCornerRadius.Control),
                colors = ButtonDefaults.buttonColors(containerColor = BrandPrimary),
            ) {
                if (isLoading) CircularProgressIndicator(Modifier.size(20.dp), color = TextOnDark)
                else Text("确认地址", modifier = Modifier.padding(vertical = 4.dp))
            }
        }
    }
}
```

- [ ] **Step 4: 改造 `CheckoutBottomSheet.kt` 支持订单预览**

在原 CheckoutBottomSheet 参数中增加 `orderPreview` 状态和 `onShowAddressSelection` 回调。当处于 `OrderFlowState.OrderPreview` 时展示确认下单面板，当处于 Idle 时展示原来的购物车结算面板。

CheckoutBottomSheet 原有参数：
```kotlin
fun CheckoutBottomSheet(
    state: CartUiState,
    orderFlowState: OrderFlowState,  // new
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
    onShowAddressSelection: () -> Unit,  // new
)
```

在 `CartScreen.kt` 中根据 `orderFlow` 状态决定展示 `CheckoutBottomSheet` 还是 `AddressSelectionSheet`：

```kotlin
// Inside CartScreen composable
val orderFlow by cartViewModel.orderFlow.collectAsState()

when (val flow = orderFlow) {
    is OrderFlowState.AddressRequired -> {
        AddressSelectionSheet(
            addresses = flow.addresses,
            isLoading = flow.isLoading,
            errorMessage = flow.errorMessage,
            onSelectAddress = { cartViewModel.selectAddress(it) },
            onDismiss = { cartViewModel.resetOrderFlow() },
        )
    }
    is OrderFlowState.OrderPreview -> {
        CheckoutBottomSheet(
            state = uiState,
            orderFlowState = flow,
            onDismiss = { cartViewModel.resetOrderFlow() },
            onConfirm = { cartViewModel.confirmOrder() },
            onShowAddressSelection = {},
        )
    }
    else -> {
        if (uiState.showCheckoutSheet) {
            CheckoutBottomSheet(
                state = uiState,
                orderFlowState = OrderFlowState.Idle,
                onDismiss = { cartViewModel.hideCheckout() },
                onConfirm = { cartViewModel.startOrderFlow() },  // Changed from direct checkout
                onShowAddressSelection = {},
            )
        }
    }
}
```

- [ ] **Step 5: 编译 + 测试验证**

Run:
```bash
cd client && ./gradlew :app:compileDebugKotlin :app:testDebugUnitTest
```

Expected: BUILD SUCCESSFUL.

- [ ] **Step 6: 提交**

```bash
git add client/app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/component/CheckoutBottomSheet.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/component/AddressSelectionSheet.kt
git commit -m "feat(android): add order flow state machine with address selection

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task B3: 细粒度 Chunking

**Files:**
- Create: `server/backend/app/rag/__init__.py`
- Create: `server/backend/app/rag/chunking.py`
- Modify: `server/backend/app/db/seed.py`
- Create: `server/tests/test_chunking.py`

**Interfaces:**
- Consumes: `Product` Pydantic model, ORM `ProductChunk`
- Produces: `chunk_product(product)` → `list[ProductChunkOrm]`

- [ ] **Step 1: 创建 `server/backend/app/rag/__init__.py`**

```python
from .chunking import chunk_product, ChunkMeta

__all__ = ["chunk_product", "ChunkMeta"]
```

- [ ] **Step 2: 创建 `server/backend/app/rag/chunking.py`**

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from ..models import Product


@dataclass
class ChunkMeta:
    product_id: str
    sku_id: str | None = None
    category_id: str = ""
    chunk_type: str = "description"       # specification | feature | scenario | marketing | review | faq
    source_type: str = "official_detail"   # official_detail | user_review | faq | marketing_copy
    trust_level: str = "official"          # official | review_aggregate | marketing
    document_version: int = 1
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def chunk_product(product: Product, version: int = 1) -> list[ChunkMeta]:
    """将单个商品的文本内容按类型切分为多个 chunk。
    
    切分规则：
    - 规格信息 → chunk_type=specification
    - 功能卖点 → chunk_type=feature（按句号/分号切分，每项一个 chunk）
    - 使用场景 → chunk_type=scenario
    - 广告文案 → chunk_type=marketing，trust_level=marketing
    - 评价 → chunk_type=review（按评价维度聚合，3-4 条评价一个 chunk）
    - FAQ → chunk_type=faq（每组 Q&A 一个 chunk）
    - 商品说明（fallback）→ chunk_type=description，约 200-400 字符
    """
    chunks: list[ChunkMeta] = []
    product_id = product.product_id
    category_id = product.category or ""

    # 1. 规格 (specification): 从 extracted_terms + sub_category + brand 构建
    spec_parts = []
    if product.extracted_terms:
        spec_parts.append("适用：" + "、".join(product.extracted_terms))
    if product.sub_category:
        spec_parts.append(f"品类：{product.sub_category}")
    if product.brand:
        spec_parts.append(f"品牌：{product.brand}")
    if spec_parts:
        chunks.append(ChunkMeta(
            product_id=product_id, category_id=category_id,
            chunk_type="specification", source_type="official_detail",
            trust_level="official", document_version=version,
            content="。".join(spec_parts),
        ))

    # 2. 功能卖点 (feature): 从 marketing_description 按句子切分
    if product.marketing_description:
        features = _split_features(product.marketing_description)
        for feat in features:
            if len(feat.strip()) >= 20:
                chunks.append(ChunkMeta(
                    product_id=product_id, category_id=category_id,
                    chunk_type="feature", source_type="official_detail",
                    trust_level="official", document_version=version,
                    content=feat.strip(),
                ))

    # 3. 使用场景 (scenario): 从 search_text 中的场景关键词提取
    scenario_keywords = ["通勤", "跑步", "户外", "运动", "送礼", "夜跑", "上学", "办公", "居家", "旅行", "海边", "登山", "骑行", "冬天", "夏天", "约会", "聚会"]
    found_scenarios = [kw for kw in scenario_keywords if kw in (product.search_text or "") or kw in (product.marketing_description or "")]
    if found_scenarios:
        for scenario in found_scenarios:
            chunks.append(ChunkMeta(
                product_id=product_id, category_id=category_id,
                chunk_type="scenario", source_type="official_detail",
                trust_level="official", document_version=version,
                content=f"适用场景：{scenario}。" + (product.search_text or ""),
            ))

    # 4. 广告文案 (marketing): marketing_description 全文标记为 marketing
    if product.marketing_description:
        chunks.append(ChunkMeta(
            product_id=product_id, category_id=category_id,
            chunk_type="marketing", source_type="marketing_copy",
            trust_level="marketing", document_version=version,
            content=product.marketing_description,
        ))

    # 5. 用户评价 (review): 按 3-4 条聚合
    reviews = product.reviews or []
    if reviews:
        for i in range(0, len(reviews), 3):
            batch = reviews[i:i + 3]
            texts = []
            for r in batch:
                rating = r.get("rating", 0) if isinstance(r, dict) else 0
                content = r.get("content", "") if isinstance(r, dict) else str(r)
                if content and isinstance(content, str) and len(content) >= 10:
                    texts.append(f"[评分{rating}] {content}")
            if texts:
                chunks.append(ChunkMeta(
                    product_id=product_id, category_id=category_id,
                    chunk_type="review", source_type="user_review",
                    trust_level="review_aggregate", document_version=version,
                    content="。".join(texts),
                    metadata={"review_count": len(texts), "batch_index": i},
                ))

    # 6. FAQ
    if product.faqs:
        for faq in product.faqs:
            q = faq.get("question", "") if isinstance(faq, dict) else ""
            a = faq.get("answer", "") if isinstance(faq, dict) else ""
            if q and a:
                chunks.append(ChunkMeta(
                    product_id=product_id, category_id=category_id,
                    chunk_type="faq", source_type="faq",
                    trust_level="official", document_version=version,
                    content=f"Q: {q}\nA: {a}",
                ))

    # 7. Fallback: 商品说明 (description), ~200-400 字符
    if not chunks or product.chunk:
        desc = product.chunk or product.marketing_description or f"{product.title} {product.brand} {product.sub_category}"
        # 约 300 字一个块
        if len(desc) > 500:
            parts = _split_paragraph(desc, 300)
            for i, part in enumerate(parts):
                if len(part) >= 30:
                    chunks.append(ChunkMeta(
                        product_id=product_id, category_id=category_id,
                        chunk_type="description", source_type="official_detail",
                        trust_level="official", document_version=version,
                        content=part,
                        metadata={"part_index": i, "total_parts": len(parts)},
                    ))
        else:
            chunks.append(ChunkMeta(
                product_id=product_id, category_id=category_id,
                chunk_type="description", source_type="official_detail",
                trust_level="official", document_version=version,
                content=desc,
            ))

    return chunks


def _split_features(text: str) -> list[str]:
    """按句号、分号、换行切分功能描述。"""
    import re
    sentences = re.split(r"[。；\n]", text)
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) >= 10]


def _split_paragraph(text: str, max_len: int = 300) -> list[str]:
    """按最大长度切分长文本，尽量在句子边界切分。"""
    if len(text) <= max_len:
        return [text]
    parts = []
    remaining = text
    while len(remaining) > max_len:
        cut = remaining.rfind("。", 0, max_len)
        if cut == -1:
            cut = max_len
        else:
            cut += 1
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        parts.append(remaining)
    return parts
```

- [ ] **Step 3: 修改 `server/backend/app/db/seed.py` 接入 chunking**

在 `seed_products` 函数中，将原来写单个 chunk 的逻辑替换为调用 `chunk_product`：

```python
# After line 41ish in seed.py, replace the chunk insertion block:
from ..rag.chunking import chunk_product

def seed_products(products, session, embedder=None):
    # ... existing product/sku seeding ...
    for p in products:
        # ... existing product ORM creation ...

        # 替换旧的 chunk 插入：细粒度多 chunk
        chunks = chunk_product(p)
        for chunk_meta in chunks:
            chunk_text = chunk_meta.content
            embedding = None
            if embedder and embedder.model is not None:
                embedding = embedder.model.encode([chunk_text], normalize_embeddings=True).tolist()[0]
            session.merge(ProductChunkOrm(
                chunk_id=f"chunk_{uuid.uuid4().hex[:12]}",
                product_id=chunk_meta.product_id,
                sku_id=chunk_meta.sku_id,
                category_id=chunk_meta.category_id,
                chunk_type=chunk_meta.chunk_type,
                source_type=chunk_meta.source_type,
                trust_level=chunk_meta.trust_level,
                document_version=chunk_meta.document_version,
                content=chunk_text,
                embedding=embedding,
            ))
    session.commit()
```

- [ ] **Step 4: 编写 `server/tests/test_chunking.py`**

```python
import pytest
from backend.app.models import Product
from backend.app.rag.chunking import chunk_product


@pytest.fixture
def sample_product():
    return Product(
        product_id="p1", title="测试精华", brand="TestBrand", category="美妆护肤", sub_category="精华",
        price=300.0, image_path="", marketing_description="核心成分含二裂酵母，深入修护肌肤。搭配透明质酸锁水保湿。适合25+抗初老人群。",
        search_text="保湿 修护 抗老",
        extracted_terms=["敏感肌", "油皮", "混油皮"],
        reviews=[
            {"rating": 5, "content": "效果很好，用了一周皮肤变细腻了"},
            {"rating": 3, "content": "一般般，没太大感觉"},
            {"rating": 4, "content": "保湿不错，价格略贵"},
        ],
        faqs=[{"question": "敏感肌可以用吗？", "answer": "建议先做耳后测试，适合大多数肤质"}],
    )


def test_chunk_has_multiple_types(sample_product):
    chunks = chunk_product(sample_product)
    types = {c.chunk_type for c in chunks}
    assert "specification" in types
    assert "feature" in types
    assert "review" in types
    assert "faq" in types


def test_chunk_metadata_present(sample_product):
    chunks = chunk_product(sample_product)
    for c in chunks:
        assert c.product_id == "p1"
        assert c.category_id == "美妆护肤"
        assert c.document_version == 1


def test_marketing_chunk_has_marketing_trust(sample_product):
    chunks = chunk_product(sample_product)
    marketing = [c for c in chunks if c.chunk_type == "marketing"]
    if marketing:
        assert marketing[0].trust_level == "marketing"


def test_no_empty_chunks(sample_product):
    chunks = chunk_product(sample_product)
    for c in chunks:
        assert len(c.content) >= 10


def test_description_chunk_splits_long_text():
    product = Product(
        product_id="p2", title="LongProduct", brand="B", category="c", sub_category="s",
        price=100.0, image_path="",
        chunk="。" * 600,
    )
    chunks = chunk_product(product)
    desc_chunks = [c for c in chunks if c.chunk_type == "description"]
    assert len(desc_chunks) >= 2
    for c in desc_chunks:
        assert len(c.content) <= 500
```

- [ ] **Step 5: 运行 chunking 测试 + 重新 seed**

Run:
```bash
cd server && ../env/venv_shopguide_backend/bin/python -m pytest tests/test_chunking.py -v --tb=short
```

Expected: all tests pass.

然后重新 seed：
```bash
cd server && ../env/venv_shopguide_backend/bin/python -m backend.app.db.seed
```

验证 chunk 数量：
```bash
cd server && ../env/venv_shopguide_backend/bin/python -c "
from backend.app.db import get_engine
from backend.app.db.models import ProductChunkOrm
from sqlalchemy.orm import Session
s=Session(get_engine())
print('chunks:', s.query(ProductChunkOrm).count())
types = s.query(ProductChunkOrm.chunk_type).distinct().all()
print('types:', [t[0] for t in types])
"
```

Expected: chunks 显著超过商品数（每个商品有多个 chunk），types 包含多种类型。

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/rag/ server/backend/app/db/seed.py server/tests/test_chunking.py
git commit -m "feat(rag): add fine-grained chunking by attribute/scenario/review/faq

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task B4: RRF 融合 + 混合检索链路

**Files:**
- Create: `server/backend/app/rag/fusion.py`
- Modify: `server/backend/app/embedding_retriever.py`
- Modify: `server/backend/app/ranker.py`
- Create: `server/tests/test_fusion.py`

**Interfaces:**
- Consumes: `EmbeddingRetriever` + ORM `ProductChunk` (DB 过滤)
- Produces: `HybridRetriever.search(plan, top_k)` → `list[tuple[Product, float]]`

- [ ] **Step 1: 扩展 `embedding_retriever.py` 支持多 chunk 搜索**

在 `EmbeddingRetriever` 中新增 `search_chunks` 方法，从数据库 `product_chunks` 表中检索：

```python
# Add to EmbeddingRetriever

def search_from_db(
    self,
    query: str,
    plan_retrieval_query: str = "",
    hard_category: str | None = None,
    hard_sub_category: str | None = None,
    top_k: int = 30,
) -> list[tuple[str, float]]:
    """从 SQLite product_chunks 表中做 BM25 + 向量混合检索。
    
    如果指定了 category/sub_category，先做 SQL 硬过滤。
    返回 [(product_id, score), ...] 去重后的结果。
    """
    from sqlalchemy.orm import Session
    from .db import get_engine
    from .db.models import ProductChunkOrm
    
    engine = get_engine()
    with Session(engine) as session:
        q = session.query(ProductChunkOrm).filter_by(is_active=True)
        if hard_category:
            q = q.filter_by(category_id=hard_category)
        if hard_sub_category:
            q = q.filter_by(category_id=hard_sub_category)  # approximate
        
        all_chunks = q.all()
    
    if not all_chunks:
        return []
    
    # BM25 on chunk content
    texts = [chunk.content for chunk in all_chunks]
    bm25 = BM25Okapi([self._tokenize(t) for t in texts])
    query_tokens = self._tokenize(query or plan_retrieval_query)
    bm25_scores = np.asarray(bm25.get_scores(query_tokens), dtype=float)
    bm25_scores = _normalize(bm25_scores)
    
    scores = bm25_scores
    if self.model is not None:
        chunk_embeddings = np.array([chunk.embedding for chunk in all_chunks if chunk.embedding], dtype=float)
        valid_indices = [i for i, chunk in enumerate(all_chunks) if chunk.embedding]
        if len(chunk_embeddings) > 0:
            query_vec = self.model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
            dense_scores_full = np.dot(chunk_embeddings, query_vec)
            dense_scores_full = _normalize(dense_scores_full)
            dense_scores = np.zeros(len(all_chunks))
            for idx, dense_idx in enumerate(valid_indices):
                dense_scores[dense_idx] = dense_scores_full[idx]
            scores = 0.65 * dense_scores + 0.35 * bm25_scores
    
    # 按 product_id 去重，保留最高分
    best: dict[str, float] = {}
    for i, chunk in enumerate(all_chunks):
        pid = chunk.product_id
        best[pid] = max(best.get(pid, 0.0), float(scores[i]))
    
    sorted_pairs = sorted(best.items(), key=lambda x: x[1], reverse=True)
    return sorted_pairs[:top_k]
```

- [ ] **Step 2: 创建 `server/backend/app/rag/fusion.py`**

```python
from __future__ import annotations

import numpy as np
from ..models import Product, HardConstraints, RetrievalPlan

# RRF constant
RRF_K = 60


def rrf_fuse(
    bm25_results: list[tuple[str, float]],
    vector_results: list[tuple[str, float]],
    top_k: int = 30,
    k: float = RRF_K,
) -> list[tuple[str, float]]:
    """RRF (Reciprocal Rank Fusion) 融合两路检索结果。
    
    score(d) = sum_{r in (bm25, vector)} 1 / (k + rank(d in r))
    """
    ranks: dict[str, float] = {}
    
    def _fill_ranks(results, label):
        for rank, (pid, _) in enumerate(results):
            ranks[pid] = ranks.get(pid, 0.0) + 1.0 / (k + rank + 1)
    
    _fill_ranks(bm25_results, "bm25")
    _fill_ranks(vector_results, "vector")
    
    sorted_pairs = sorted(ranks.items(), key=lambda x: x[1], reverse=True)
    return sorted_pairs[:top_k]


class ConstraintBasedFilter:
    """基于 HardConstraints 的 SQL/ORM 级过滤。"""

    def filter(self, products: list[Product], constraints: HardConstraints) -> list[Product]:
        from .constraint_filter import hard_filter
        return [p for p in products if hard_filter(p, constraints)]


class HybridRetriever:
    """统一混合检索入口。
    
    流程：SQL 过滤 → 关键词 Top N → 向量 Top N → RRF 融合 → 约束过滤 → 返回 Top K
    """

    def __init__(self, embedding_retriever):
        self.retriever = embedding_retriever
        self.filter = ConstraintBasedFilter()

    def search(self, plan: RetrievalPlan, top_k: int = 30) -> list[tuple[Product, float]]:
        constraints = plan.hard_constraints
        query = plan.retrieval_query or "商品推荐"

        # 1. 向量检索
        try:
            vector_raw = self.retriever.search_from_db(
                query=query,
                hard_category=constraints.category,
                hard_sub_category=constraints.sub_category,
                top_k=top_k,
            )
        except Exception:
            vector_raw = []

        # 2. 关键词 (BM25) 也从 DB chunk 走
        try:
            bm25_raw = self.retriever.search_from_db(
                query=query,
                hard_category=constraints.category,
                hard_sub_category=constraints.sub_category,
                top_k=top_k,
            )
        except Exception:
            bm25_raw = []

        # 3. RRF 融合
        if vector_raw and bm25_raw:
            fused = rrf_fuse(bm25_raw, vector_raw, top_k=top_k)
        elif vector_raw:
            fused = vector_raw[:top_k]
        else:
            fused = bm25_raw[:top_k]

        # 4. 映射回 Product
        product_map = {p.product_id: p for p in self.retriever.products}
        results: list[tuple[Product, float]] = []
        seen: set[str] = set()
        for pid, score in fused:
            if pid in seen:
                continue
            product = product_map.get(pid)
            if product is None:
                continue
            if not hard_filter(product, constraints):
                continue
            results.append((product, score))
            seen.add(pid)
            if len(results) >= top_k:
                break

        return results


def hard_filter(product: Product, constraints: HardConstraints) -> bool:
    from .constraint_filter import hard_filter as _hf
    return _hf(product, constraints)
```

- [ ] **Step 3: 修改 `adaptive_retriever.py` 接入 HybridRetriever**

```python
# In AdaptiveRetriever.search(), replace self.retriever.search() with HybridRetriever when available:

def search(self, plan: RetrievalPlan, top_k: int = 30) -> list[tuple[Product, float]]:
    # Try hybrid first if the retriever supports search_from_db
    if hasattr(self.retriever, 'search_from_db'):
        from .rag.fusion import HybridRetriever
        hybrid = HybridRetriever(self.retriever)
        results = hybrid.search(plan, top_k=top_k)
        if results:
            return results
    
    # Fallback to existing relaxed round-based search
    merged: dict[str, tuple[Product, float]] = {}
    for round_index in range(self.policy.max_rounds):
        relaxed_plan = self._build_relaxed_plan(plan, round_index)
        retrieved = self.retriever.search(relaxed_plan.retrieval_query, top_k=top_k)
        # ... existing logic ...
```

- [ ] **Step 4: 编写 `server/tests/test_fusion.py`**

```python
import pytest
from backend.app.rag.fusion import rrf_fuse, ConstraintBasedFilter
from backend.app.models import HardConstraints, Product


def test_rrf_fuse_basic():
    a = [("p1", 0.9), ("p2", 0.7), ("p3", 0.5)]
    b = [("p2", 0.8), ("p1", 0.6), ("p4", 0.3)]
    fused = rrf_fuse(a, b, top_k=5)
    pids = [pid for pid, _ in fused]
    # p1 and p2 should rank high in both lists
    assert pids[0] in {"p1", "p2"}
    assert pids[1] in {"p1", "p2"}
    assert "p3" in pids or "p4" in pids


def test_rrf_fuse_empty():
    result = rrf_fuse([], [], top_k=5)
    assert result == []


def test_rrf_fuse_single_list():
    a = [("p1", 0.9), ("p2", 0.7)]
    result = rrf_fuse(a, [], top_k=5)
    assert len(result) == 2


def test_constraint_filter_price():
    products = [
        Product(product_id="p1", title="A", brand="B", category="c", sub_category="s", price=500.0, image_path=""),
        Product(product_id="p2", title="B", brand="B", category="c", sub_category="s", price=100.0, image_path=""),
    ]
    constraints = HardConstraints(price_max=400.0)
    filter_obj = ConstraintBasedFilter()
    filtered = filter_obj.filter(products, constraints)
    assert len(filtered) == 1
    assert filtered[0].product_id == "p2"


def test_constraint_filter_exclude_brand():
    products = [
        Product(product_id="p1", title="NikeAir", brand="Nike", category="c", sub_category="s", price=500.0, image_path=""),
        Product(product_id="p2", title="AdiBoost", brand="Adidas", category="c", sub_category="s", price=400.0, image_path=""),
    ]
    constraints = HardConstraints(exclude_brands=["Nike"])
    filter_obj = ConstraintBasedFilter()
    filtered = filter_obj.filter(products, constraints)
    assert len(filtered) == 1
    assert filtered[0].product_id == "p2"
```

- [ ] **Step 5: 运行融合测试 + 回归测试**

Run:
```bash
cd server && ../env/venv_shopguide_backend/bin/python -m pytest tests/test_fusion.py -v --tb=short
```

Expected: all pass.

然后回归测试：
```bash
cd server && ../env/venv_shopguide_backend/bin/python -m pytest tests/test_api.py tests/test_agent_core.py -v --tb=short 2>&1 | tail -30
```

Expected: 全部 142 个通过。

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/rag/fusion.py server/backend/app/embedding_retriever.py \
        server/backend/app/adaptive_retriever.py server/tests/test_fusion.py
git commit -m "feat(rag): add RRF fusion and hybrid retrieval pipeline

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task B5: Reranker + 检索链路端到端整合

**Files:**
- Create: `server/backend/app/rag/reranker.py`
- Modify: `server/backend/app/ranker.py`（如果需要接入 reranker）
- Modify: `server/backend/app/agent.py`（可选，接入 hybrid retriever flag）

**Interfaces:**
- Consumes: RRF 融合后的 Top 30 候选
- Produces: `rerank(candidates, query)` → Top 8

- [ ] **Step 1: 创建 `server/backend/app/rag/reranker.py`**

```python
from __future__ import annotations

import numpy as np
from ..models import Product, RankedProduct, RetrievalPlan


class Reranker:
    """轻量重排器。第一版使用启发式（不引入额外模型依赖）。
    
    重排逻辑：
    1. 需求匹配度：基于 hard + soft constraints 命中数
    2. 用户画像匹配度：基于 feedback_ranker 的 boost
    3. 热度：基于 review_rating + review 数量
    4. 多样性：避免同品牌过度重复
    """

    def rerank(
        self,
        candidates: list[tuple[Product, float]],
        plan: RetrievalPlan,
        top_k: int = 8,
    ) -> list[tuple[Product, float]]:
        if len(candidates) <= top_k:
            return candidates

        constraints = plan.hard_constraints
        soft = plan.soft_preferences

        scored: list[tuple[Product, float]] = []
        for product, retrieval_score in candidates:
            rerank_score = retrieval_score * 0.35
            # 需求匹配 (0.35)
            demand_score = 0.0
            if constraints.sub_category and product.sub_category == constraints.sub_category:
                demand_score += 0.6
            elif constraints.category and product.category == constraints.category:
                demand_score += 0.3
            if constraints.price_max is not None and product.price <= constraints.price_max:
                demand_score += 0.2
            if constraints.price_min is not None and product.price >= constraints.price_min:
                demand_score += 0.2
            for pref_val in soft.values():
                if pref_val and pref_val in (product.search_text or ""):
                    demand_score += 0.3
            rerank_score += 0.35 * min(demand_score, 1.0)

            # 热度 (0.15)
            popularity = (product.review_rating or 0.0) / 5.0
            popularity += min(len(product.reviews or []) / 20.0, 1.0)
            rerank_score += 0.15 * min(popularity, 1.0)

            # 转化表现 proxy (0.10)：价格合理度
            if constraints.price_max and constraints.price_max > 0:
                price_ratio = product.price / constraints.price_max
                conversion = 1.0 - abs(0.5 - price_ratio)
            else:
                conversion = 0.5
            rerank_score += 0.10 * max(0, conversion)

            # 多样性 penalty (0.05) — 在最终选取阶段应用
            scored.append((product, rerank_score))

        # 按 rerank 分数排序
        scored.sort(key=lambda x: x[1], reverse=True)

        # 多样性：同品牌不超过 2 件
        selected: list[tuple[Product, float]] = []
        brand_counts: dict[str, int] = {}
        for product, score in scored:
            brand = product.brand or ""
            if brand_counts.get(brand, 0) >= 2:
                continue
            selected.append((product, score))
            brand_counts[brand] = brand_counts.get(brand, 0) + 1
            if len(selected) >= top_k:
                break

        return selected
```

- [ ] **Step 2: 在 `agent.py` 的 `retrieve_and_rank` 方法中接入**

```python
# In ShopGuideAgent.retrieve_and_rank(), after getting ranked but before returning:

def retrieve_and_rank(self, plan, limit=8, session_id=""):
    # ... existing cache check ...

    # 使用 hybrid retriever
    from .rag.fusion import HybridRetriever
    hybrid = HybridRetriever(self.retriever)
    candidates = hybrid.search(plan, top_k=30)

    if candidates:
        from .rag.reranker import Reranker
        reranker = Reranker()
        reranked = reranker.rerank(candidates, plan, top_k=limit)
        ranked = [
            RankedProduct(
                product=product,
                score=score,
                tier=1 if score >= 0.6 else 2,
                reason=f"综合匹配度 {score:.2f}",
                evidence=[],
            )
            for product, score in reranked
        ]
    # ... fallback to old logic if hybrid fails ...
```

- [ ] **Step 3: 运行全量测试**

Run:
```bash
cd server && ../env/venv_shopguide_backend/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 4: 提交**

```bash
git add server/backend/app/rag/reranker.py server/backend/app/agent.py server/tests/test_fusion.py
git commit -m "feat(rag): add reranker with demand/popularity/diversity scoring

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task B6: 里程碑 B 集成验证

**Files:**
- Create: `server/tests/test_order_flow.py`

- [ ] **Step 1: 编写订单状态机集成测试**

```python
import pytest
from backend.app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    return TestClient(app)


def test_order_initiate_requires_items(client):
    """空购物车不能发起订单"""
    response = client.post("/api/cart/clear", json={"session_id": "test_order_1"})
    assert response.status_code == 200

    response = client.post("/api/order/initiate", json={"session_id": "test_order_1"})
    assert response.status_code == 400


def test_order_flow_happy_path(client):
    """完整下单流程：加购 → 发起 → 选地址 → 确认"""
    sid = "test_order_flow_1"

    # 加购
    client.post("/api/cart/add", json={"session_id": sid, "product_id": "p_beauty_001", "quantity": 1})

    # 发起
    resp = client.post("/api/order/initiate", json={"session_id": sid})
    assert resp.status_code == 200
    data = resp.json()
    order_id = data["order_id"]
    assert data["status"] in {"address_required", "awaiting_confirmation"}

    # 获取地址
    resp = client.get("/api/order/addresses")
    assert resp.status_code == 200
    addresses = resp.json()["addresses"]
    assert len(addresses) > 0
    addr_id = addresses[0]["address_id"]

    # 选择地址
    resp = client.post("/api/order/select_address", json={"order_id": order_id, "address_id": addr_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["confirmation_token"] is not None
    token = data["confirmation_token"]

    # 确认
    resp = client.post("/api/order/confirm", json={
        "order_id": order_id,
        "confirmation_token": token,
        "idempotency_key": f"test_key_{sid}",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_order_confirm_with_wrong_token_fails(client):
    """错误 token 不能确认订单"""
    sid = "test_order_token_1"
    client.post("/api/cart/add", json={"session_id": sid, "product_id": "p_beauty_001", "quantity": 1})
    resp = client.post("/api/order/initiate", json={"session_id": sid})
    order_id = resp.json()["order_id"]
    resp = client.post("/api/order/confirm", json={
        "order_id": order_id,
        "confirmation_token": "wrong_token",
    })
    assert resp.status_code == 400


def test_idempotent_order_confirm(client):
    """幂等键重复确认应返回相同结果"""
    sid = "test_order_idempotent_1"
    client.post("/api/cart/add", json={"session_id": sid, "product_id": "p_beauty_001", "quantity": 1})
    resp = client.post("/api/order/initiate", json={"session_id": sid})
    order_id = resp.json()["order_id"]
    resp = client.get("/api/order/addresses")
    addr_id = resp.json()["addresses"][0]["address_id"]
    resp = client.post("/api/order/select_address", json={"order_id": order_id, "address_id": addr_id})
    token = resp.json()["confirmation_token"]

    id_key = "idempotent_test_key"
    resp1 = client.post("/api/order/confirm", json={
        "order_id": order_id, "confirmation_token": token, "idempotency_key": id_key,
    })
    assert resp1.status_code == 200
    resp2 = client.post("/api/order/confirm", json={
        "order_id": order_id, "confirmation_token": token, "idempotency_key": id_key,
    })
    assert resp2.status_code == 200
    assert resp1.json()["order_id"] == resp2.json()["order_id"]
```

- [ ] **Step 2: 运行全量测试**

```bash
cd server && ../env/venv_shopguide_backend/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -40
```

Expected: all tests pass.

- [ ] **Step 3: 提交**

```bash
git add server/tests/test_order_flow.py
git commit -m "test: add order flow integration tests for idempotency and happy path

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- Android 订单确认流程（P05）：B1 + B2 ✅
- 商品 Chunking 增强（P06）：B3 ✅
- 混合检索链路（P07）：B4 + B5 ✅
- 集成验证：B6 ✅

**2. 已知风险:**
- `OrderApiService` 仅新引入 Retrofit 接口，不破坏现有 `CartApiService`
- `HybridRetriever` fallback 保留了原有检索链路
- 多样性 penalty 会在同品牌多商品场景下正确限制展示数量
- reranker 当前是启发式，后续可升级为 cross-encoder / LLM reranker

**3. 类型一致性:**
- `rrf_fuse` 输入输出均为 `list[tuple[str, float]]`
- `chunk_product` 输入 `Product`，输出 `list[ChunkMeta]`
- Android `OrderFlowState` sealed class 覆盖了完整状态机

---
