# Task 06：实现购物车 CRUD、数量编辑与模拟下单

## 目标

实现完整购物车页面，支持增删改查、数量编辑、全选、合计、模拟下单。

## 需要创建/修改文件

```text
data/model/Cart.kt
data/remote/CartApiClient.kt
vm/CartViewModel.kt
ui/screen/CartScreen.kt
ui/component/CartItemCard.kt
ui/component/CartSummaryBar.kt
ui/component/CheckoutBottomSheet.kt
ui/component/EmptyCartView.kt
ui/component/CartBadge.kt
ui/component/ProductCard.kt
ui/component/ProductDetailBottomSheet.kt
navigation/AppNavGraph.kt
vm/ChatViewModel.kt
```

## 数据模型

```kotlin
data class CartItemUiModel(
    val productId: String,
    val name: String,
    val price: Double,
    val quantity: Int,
    val selected: Boolean = true,
    val imageUrl: String? = null,
    val tags: List<String> = emptyList(),
    val stock: Int? = null,
    val reason: String? = null
)

data class CartUiState(
    val isLoading: Boolean = false,
    val items: List<CartItemUiModel> = emptyList(),
    val selectedCount: Int = 0,
    val totalCount: Int = 0,
    val totalPrice: Double = 0.0,
    val errorMessage: String? = null,
    val showCheckoutSheet: Boolean = false,
    val checkoutResult: CheckoutResult? = null
)
```

## 后端接口

```http
GET  /api/cart?session_id=xxx
POST /api/cart/add
POST /api/cart/add_bundle
POST /api/cart/update_quantity
POST /api/cart/remove
POST /api/cart/select
POST /api/cart/clear
POST /api/cart/checkout
```

## CartScreen 布局

```text
顶部栏：
  返回按钮
  标题：购物车
  副标题：已选 x 件商品

中间：
  CartItemCard 列表

底部固定栏：
  全选 checkbox
  合计金额
  去结算按钮
```

## CartItemCard

包含：

```text
1. 选择框
2. 商品图
3. 商品名
4. 标签
5. 单价
6. 数量编辑器 [-] quantity [+]
7. 删除按钮
```

## ProductCard / ProductDetailBottomSheet 加购联动

商品卡片和商品详情浮层都要支持“加入购物车”：

```text
1. 调用 CartApiClient.addToCart。
2. 成功后按钮短暂显示“已加入”。
3. 更新 ChatScreen 顶部 CartBadge。
4. 显示 Snackbar：“已加入购物车”。
```

## CheckoutBottomSheet

点击“去结算”显示确认订单底部弹窗。

## 验收标准

```text
1. 商品卡片可加入购物车。
2. 商品详情浮层可加入购物车。
3. 购物车 badge 实时更新。
4. 购物车页面能展示商品。
5. 可以增加/减少/删除商品。
6. 可以全选/取消选择。
7. 合计金额正确。
8. 可以模拟下单。
9. 空购物车状态正常。
10. ./gradlew :app:assembleDebug 通过。
```
