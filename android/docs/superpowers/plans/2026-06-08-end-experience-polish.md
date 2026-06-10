# End Experience Polish Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the native Compose chat-to-detail-to-cart journey with assistant-style loading, refined product interactions, robust fallbacks, focused product follow-up verification, and cart undo feedback.

**Architecture:** Keep changes inside the existing MVVM + Compose structure. Add small UI-state contracts and helper functions, then enhance existing components instead of rewriting screens. Recommendation role/order must remain source-driven by backend or approved mock data; the client only reveals and styles what it receives.

**Tech Stack:** Kotlin, Jetpack Compose, ViewModel, StateFlow, Compose animation APIs, JUnit 4, Gradle Wrapper.

---

## File Structure

- Modify `app/src/main/java/com/example/shopguideagent/data/model/ChatMessage.kt`: add chat experience phase and focused follow-up payload model.
- Modify `app/src/main/java/com/example/shopguideagent/data/catalog/ProductCatalog.kt`: make the local approved mock catalog preserve source order/role instead of ranking products in the Android client.
- Modify `app/src/main/java/com/example/shopguideagent/data/model/Cart.kt`: add removed-item undo state.
- Modify `app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`: expose assistant loading phases, bounded stream interruption state, source-preserving product reveal, and testable focused follow-up payload.
- Modify `app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt`: implement remove undo and preserve cart count correctness.
- Modify `app/src/main/java/com/example/shopguideagent/ui/component/TypingIndicator.kt`: support two-stage assistant status labels.
- Modify `app/src/main/java/com/example/shopguideagent/ui/component/ProductImage.kt`: add loading shimmer/placeholder and error fallback.
- Modify `app/src/main/java/com/example/shopguideagent/ui/component/ProductSkeletonCard.kt`: make it the shared product loading surface.
- Modify `app/src/main/java/com/example/shopguideagent/ui/component/HeroProductCard.kt`: refine press/add-to-cart/favorite-ready interaction without changing recommendation role.
- Modify `app/src/main/java/com/example/shopguideagent/ui/component/AlternativeProductCard.kt`: align secondary card motion and add-to-cart feedback.
- Modify `app/src/main/java/com/example/shopguideagent/ui/component/ProductDetailBottomSheet.kt`: reinforce focused follow-up and synchronized add-to-cart feedback.
- Modify `app/src/main/java/com/example/shopguideagent/ui/component/CartBadge.kt`: trigger count-change animation only on meaningful count changes.
- Modify `app/src/main/java/com/example/shopguideagent/ui/component/CartItemCard.kt`: add remove feedback entry point if needed by `CartScreen`.
- Modify `app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`: render assistant phase, retry state, product skeletons, and block-level scrolling.
- Modify `app/src/main/java/com/example/shopguideagent/ui/screen/CartScreen.kt`: show undo snackbar/action and stable cart item animations.
- Modify `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`: add exact `focus_product_id` payload and source-order tests.
- Add or modify `app/src/test/java/com/example/shopguideagent/data/catalog/ProductCatalogTest.java`: verify source-order recommendation behavior.
- Modify `app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.java`: add remove undo tests.
- Modify or add focused UI helper tests under `app/src/test/java/com/example/shopguideagent/ui/...` only if helper functions are extracted.

## Task 1: Source-Driven Recommendation Contract

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/data/catalog/ProductCatalog.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
- Test: `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`
- Test: `app/src/test/java/com/example/shopguideagent/data/catalog/ProductCatalogTest.java`

- [ ] **Step 1: Add failing source-order tests**

Add or update tests proving local approved mock data order is preserved:

```java
@Test
public void listProductCatalogPreservesSourceOrderAndMarksFirstAsPrimaryOnlyBySourcePosition() {
    ProductUiModel first = product("sku_first");
    ProductUiModel second = product("sku_second");
    ListProductCatalog catalog = new ListProductCatalog(Arrays.asList(first, second));

    List<ProductUiModel> result = catalog.recommend("any query", 2);

    assertEquals("sku_first", result.get(0).getProductId());
    assertEquals("sku_second", result.get(1).getProductId());
    assertTrue(result.get(0).isPrimary());
    assertFalse(result.get(1).isPrimary());
}
```

In `ChatViewModelTest`, add:

```java
@Test
public void followUpDoesNotPromoteClientRankedReplacement() {
    ChatViewModel viewModel = viewModelWithCatalog();
    viewModel.sendMessage("recommend");
    ProductUiModel focused = viewModel.getUiState().getValue().getMessages().get(2).getProducts().get(0);

    viewModel.sendProductFollowUp(focused, "compare");

    assertEquals(focused.getProductId(), viewModel.getLastProductFollowUpPayloadJson().getString("focus_product_id"));
}
```

- [ ] **Step 2: Run tests and verify failure**

Run: `gradlew.bat :app:testDebugUnitTest --tests com.example.shopguideagent.vm.ChatViewModelTest --tests com.example.shopguideagent.data.catalog.ProductCatalogTest`

Expected: FAIL until exact payload getter exists. If `ProductCatalogTest` does not compile yet, create the file and minimal helper product factory.

- [ ] **Step 3: Remove Android-side ranking from approved mock catalog**

In `ProductCatalog.kt`, replace `AndroidAssetProductCatalog.recommend()` sorting logic with source-order selection:

```kotlin
override fun recommend(query: String, limit: Int): List<ProductUiModel> =
    products
        .take(limit.coerceAtLeast(1))
        .mapIndexed { index, product -> product.copy(isPrimary = index == 0) }
```

Keep `ProductCatalogScorer` only if existing tests still need it as a pure scoring utility; do not use it to choose recommendations in the app flow.

- [ ] **Step 4: Remove client-side replacement promotion**

In `ChatViewModel.replacementFor()`, do not rank by query and do not invent a new primary by relevance. For local mock behavior, preserve catalog source order and avoid returning the focused product when an alternative is already present:

```kotlin
private fun replacementFor(product: ProductUiModel, userText: String): ProductUiModel {
    val candidates = productCatalog.recommend("", 4)
    return (candidates.firstOrNull { it.productId != product.productId } ?: candidates.firstOrNull() ?: product)
}
```

This still uses approved mock source order. It does not claim relevance beyond mock data.

- [ ] **Step 5: Run source-order tests**

Run: `gradlew.bat :app:testDebugUnitTest --tests com.example.shopguideagent.vm.ChatViewModelTest --tests com.example.shopguideagent.data.catalog.ProductCatalogTest`

Expected: PASS.

## Task 2: State Contracts And Exact Focused Payload Tests

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/data/model/ChatMessage.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
- Test: `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`

- [ ] **Step 1: Add failing tests for exact focused payload**

Add tests:

```java
@Test
public void productFollowUpPayloadIncludesFocusProductId() {
    ChatViewModel viewModel = viewModelWithCatalog();
    viewModel.sendMessage("recommend");
    ProductUiModel focused = viewModel.getUiState().getValue().getMessages().get(2).getProducts().get(0);

    viewModel.sendProductFollowUp(focused, "compare price");

    assertEquals(focused.getProductId(), viewModel.getLastProductFollowUpPayload().getFocusProductId());
    assertEquals("compare price", viewModel.getLastProductFollowUpPayload().getText());
}

@Test
public void productFollowUpJsonPayloadUsesSnakeCaseFocusProductId() throws Exception {
    ChatViewModel viewModel = viewModelWithCatalog();
    viewModel.sendMessage("recommend");
    ProductUiModel focused = viewModel.getUiState().getValue().getMessages().get(2).getProducts().get(0);

    viewModel.sendProductFollowUp(focused, "compare price");

    JSONObject payload = viewModel.getLastProductFollowUpPayloadJson();
    assertEquals("product_followup", payload.getString("type"));
    assertEquals(focused.getProductId(), payload.getString("focus_product_id"));
    assertEquals("compare price", payload.getString("text"));
}
```

- [ ] **Step 2: Run tests and verify failure**

Run: `gradlew.bat :app:testDebugUnitTest --tests com.example.shopguideagent.vm.ChatViewModelTest`

Expected: FAIL because payload model/getters and snake_case JSON payload do not exist.

- [ ] **Step 3: Add minimal models**

In `ChatMessage.kt`, add:

```kotlin
enum class ChatExperiencePhase {
    Idle,
    UserSending,
    AssistantThinking,
    RecommendationLoading,
    RecommendationReady,
    Error,
}

data class ProductFollowUpPayload(
    val type: String = "product_followup",
    val focusProductId: String,
    val text: String,
)
```

Extend `ChatUiState` with `phase: ChatExperiencePhase = ChatExperiencePhase.Idle`.

- [ ] **Step 4: Persist last focused payload and exact JSON in ViewModel**

In `ChatViewModel`, add a private nullable field and Java-visible getter:

```kotlin
private var lastProductFollowUpPayload: ProductFollowUpPayload? = null

fun getLastProductFollowUpPayload(): ProductFollowUpPayload? = lastProductFollowUpPayload
fun getLastProductFollowUpPayloadJson(): JSONObject? = lastProductFollowUpPayload?.toJson()
```

Set it at the start of `sendProductFollowUp()`:

```kotlin
lastProductFollowUpPayload = ProductFollowUpPayload(
    focusProductId = product.productId,
    text = text,
)
```

Add a payload builder using current `org.json` style, not a new serialization library:

```kotlin
fun ProductFollowUpPayload.toJson(): JSONObject =
    JSONObject()
        .put("type", type)
        .put("focus_product_id", focusProductId)
        .put("text", text)
```

- [ ] **Step 5: Run focused tests**

Run: `gradlew.bat :app:testDebugUnitTest --tests com.example.shopguideagent.vm.ChatViewModelTest`

Expected: PASS.

## Task 3: Chat Assistant Loading, Timeout, Retry, And Skeleton Exit

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/TypingIndicator.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductSkeletonCard.kt`
- Test: `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`

- [ ] **Step 1: Add tests for phase transitions, timeout, and disconnect helper**

Add a pure helper if needed:

```kotlin
fun shouldExitRecommendationSkeleton(isStreaming: Boolean, elapsedMillis: Long, timeoutMillis: Long): Boolean =
    isStreaming && elapsedMillis >= timeoutMillis

fun interruptedStreamMessage(partialText: String, reason: String): String =
    if (partialText.isBlank()) reason else "$partialText\n\n$reason"
```

Test it from Java/Kotlin:

```java
assertFalse(ChatViewModelKt.shouldExitRecommendationSkeleton(true, 1000, 8000));
assertTrue(ChatViewModelKt.shouldExitRecommendationSkeleton(true, 9000, 8000));
assertTrue(ChatViewModelKt.interruptedStreamMessage("partial", "Retry").contains("partial"));
```

- [ ] **Step 2: Run tests and verify failure**

Run: `gradlew.bat :app:testDebugUnitTest --tests com.example.shopguideagent.vm.ChatViewModelTest`

Expected: FAIL until helpers and phase updates exist.

- [ ] **Step 3: Add explicit timeout state fields**

Extend `ChatUiState` with:

```kotlin
val retryMessageText: String? = null,
val streamStartedAtMillis: Long? = null,
```

Keep partial stream text in the existing assistant message instead of clearing it.

- [ ] **Step 4: Set phases in `ChatViewModel`**

Use existing `isSending` for input locking, but also set:

- `UserSending` when user message is accepted.
- `AssistantThinking` while initial assistant message is empty.
- `RecommendationLoading` while products are expected but not fully visible.
- `RecommendationReady` when final message replaces streaming placeholder.
- `Error` when a timeout/disconnect error is surfaced.

- [ ] **Step 5: Add bounded timeout job for local streaming**

In `sendMessageStreaming()`, set `streamStartedAtMillis = System.currentTimeMillis()` and launch a timeout job in `viewModelScope`.

The timeout job should:

- check that the same assistant message is still streaming
- preserve existing partial text
- change `phase` to `Error`
- set `errorMessage` and `retryMessageText` to the last user message
- clear `isSending`

Cancel this state path naturally when `replaceMessage(finalMessage.copy(isStreaming = false))` runs.

- [ ] **Step 6: Add explicit disconnect handler**

Add a method for later WebSocket integration:

```kotlin
fun handleStreamInterrupted(messageId: String, reason: String)
```

It should preserve partial text, set `phase = ChatExperiencePhase.Error`, set `retryMessageText`, and exit skeleton/loading state.

- [ ] **Step 7: Render phase in `ChatScreen`**

When latest assistant message is streaming:

- Show `TypingIndicator(label = "Understanding your need")` during `AssistantThinking`.
- Show `TypingIndicator(label = "Organizing recommendation")` during `RecommendationLoading`.
- If `expectedProductCount > products.size`, render `ProductSkeletonCard` placeholders for the missing count.

- [ ] **Step 8: Add retry affordance**

For current local/mock implementation, retry can call `sendMessageStreaming()` with the last user message text. Keep retry UI inline and low-interruption. Do not create infinite hidden reconnect loops.

- [ ] **Step 9: Run focused tests**

Run: `gradlew.bat :app:testDebugUnitTest --tests com.example.shopguideagent.vm.ChatViewModelTest`

Expected: PASS.

## Task 4: Product Image, Card Feedback, And Role-Preserving Reveal

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductImage.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductSkeletonCard.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/HeroProductCard.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/AlternativeProductCard.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductCarousel.kt`

- [ ] **Step 1: Inspect current product carousel role handling**

Confirm `ProductCarousel` uses `isPrimary` or first item as presentation only. It must not sort or rerank products.

- [ ] **Step 2: Add shared image state UI**

Update `ProductImage` to use Coil `AsyncImage` callbacks or painter state:

- loading: branded placeholder/skeleton
- success: image crop
- error: current fallback icon plus product initials

- [ ] **Step 3: Keep card actions local and light**

For `HeroProductCard` and `AlternativeProductCard`:

- use existing `clickableWithScale`
- keep add-to-cart complete state short or reset on product ID change
- avoid changing product order or role

- [ ] **Step 4: Verify compile**

Run: `gradlew.bat :app:assembleDebug`

Expected: PASS.

## Task 5: Product Detail Follow-Up And Add-To-Cart Feedback

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductDetailBottomSheet.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`
- Test: `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`

- [ ] **Step 1: Add or extend focused payload test**

Ensure `sendProductFollowUp(product, text)` updates both `lastProductFollowUpPayload.focusProductId` and exact JSON key `focus_product_id`.

- [ ] **Step 2: Keep BottomSheet follow-up bound to selected product**

In `ChatScreen`, keep:

```kotlin
onFollowUp = { followUp ->
    chatViewModel.sendProductFollowUp(product, followUp)
    selectedProduct = null
}
```

Do not replace this with generic chat send.

- [ ] **Step 3: Add detail add-to-cart feedback**

In `ProductDetailBottomSheet`, add a short `added` state so the button label/icon reflects completion after `onAddToCart(product)`.

- [ ] **Step 4: Run focused tests**

Run: `gradlew.bat :app:testDebugUnitTest --tests com.example.shopguideagent.vm.ChatViewModelTest`

Expected: PASS.

## Task 6: Cart Undo, Badge Stability, And Summary Feedback

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/data/model/Cart.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/screen/CartScreen.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/CartBadge.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/CartSummaryBar.kt`
- Test: `app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.java`

- [ ] **Step 1: Add failing undo tests**

Add tests:

```java
@Test
public void removeStoresUndoItemAndUpdatesTotals() {
    CartViewModel viewModel = new CartViewModel();
    viewModel.addItem(new CartItemUiModel("sku_001", "A", 100.0, 2, true, null, Collections.emptyList(), null, null));

    viewModel.remove("sku_001");

    assertEquals(0, viewModel.getUiState().getValue().getTotalCount());
    assertEquals("sku_001", viewModel.getUiState().getValue().getLastRemovedItem().getProductId());
}

@Test
public void undoRemoveRestoresItemAndTotals() {
    CartViewModel viewModel = new CartViewModel();
    viewModel.addItem(new CartItemUiModel("sku_001", "A", 100.0, 2, true, null, Collections.emptyList(), null, null));
    viewModel.remove("sku_001");

    viewModel.undoLastRemove();

    assertEquals(2, viewModel.getUiState().getValue().getTotalCount());
    assertEquals(2, viewModel.getUiState().getValue().getSelectedCount());
    assertEquals(200.0, viewModel.getUiState().getValue().getTotalPrice(), 0.001);
    assertEquals(null, viewModel.getUiState().getValue().getLastRemovedItem());
}

@Test
public void undoRemovePersistsRestoredCart() {
    FakeCartPersistenceStore store = new FakeCartPersistenceStore();
    CartViewModel viewModel = new CartViewModel("user_a", store);
    viewModel.addItem(new CartItemUiModel("sku_001", "A", 100.0, 2, true, null, Collections.emptyList(), null, null));
    viewModel.remove("sku_001");

    viewModel.undoLastRemove();

    CartViewModel reloaded = new CartViewModel("user_a", store);
    assertEquals(1, reloaded.getUiState().getValue().getItems().size());
    assertEquals(2, reloaded.getUiState().getValue().getTotalCount());
}
```

- [ ] **Step 2: Run tests and verify failure**

Run: `gradlew.bat :app:testDebugUnitTest --tests com.example.shopguideagent.vm.CartViewModelTest`

Expected: FAIL because `lastRemovedItem` and `undoLastRemove()` do not exist.

- [ ] **Step 3: Add undo state**

In `CartUiState`, add:

```kotlin
val lastRemovedItem: CartItemUiModel? = null
```

Update `recalculate()` to preserve it.

- [ ] **Step 4: Implement remove undo**

In `CartViewModel.remove(productId)`:

- find the removed item
- remove it from items
- set `lastRemovedItem`
- persist updated items

Add:

```kotlin
fun undoLastRemove() {
    val removed = _uiState.value.lastRemovedItem ?: return
    updateItems(_uiState.value.items + removed)
    _uiState.value = _uiState.value.copy(lastRemovedItem = null).recalculate()
}
```

Ensure persistence reflects restored items.

- [ ] **Step 5: Wire snackbar undo in `CartScreen`**

On `state.lastRemovedItem`, show snackbar with action label "Undo". If action performed, call `cartViewModel.undoLastRemove()`.

- [ ] **Step 6: Refine `CartBadge` bump**

Track previous count so the badge does not animate on initial composition with count `0`; animate only when count changes to a different positive value.

- [ ] **Step 7: Run cart tests**

Run: `gradlew.bat :app:testDebugUnitTest --tests com.example.shopguideagent.vm.CartViewModelTest`

Expected: PASS.

## Task 7: Full Verification

**Files:**
- No planned code changes unless verification finds defects.

- [ ] **Step 1: Run all unit tests**

Run: `gradlew.bat :app:testDebugUnitTest`

Expected: PASS.

- [ ] **Step 2: Build debug APK**

Run: `gradlew.bat :app:assembleDebug`

Expected: PASS.

- [ ] **Step 3: Manual QA checklist**

Verify on emulator/device if available:

- chat send enters assistant loading state
- recommendation text appears before product cards
- skeletons exit when products appear or retry state is shown
- product image loading and fallback do not show blank UI
- product card opens detail sheet
- focused follow-up sends payload with active `focus_product_id`
- add-to-cart updates badge and cart count
- cart quantity changes update summary
- cart remove supports undo
- empty cart routes back to chat
