# Cloudflare Cart Commands And Product Tags Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the Android app on the current Cloudflare tunnel backend scheme, make natural-language cart commands such as "将两份雀巢咖啡加入购物车" actually add the intended catalog product, and make product card tags reflect each product instead of generic defaults.

**Architecture:** The backend remains the source of truth for product identity, cart actions, and product-card metadata. Android keeps using `https://nsw-lasting-asked-issued.trycloudflare.com` / `wss://nsw-lasting-asked-issued.trycloudflare.com`, renders backend cart feedback, and uses backend-provided dynamic tags with local catalog as fallback only. Natural-language cart commands become a two-stage backend flow: parse action/quantity, resolve an explicit product mention from the catalog, then execute or ask for clarification if ambiguous.

**Tech Stack:** Python 3.12, FastAPI, WebSocket, Pydantic, pytest on `mix_A100`; Kotlin, Jetpack Compose, OkHttp WebSocket, JUnit/Gradle on Windows.

---

## Current Evidence

- Android config is already Cloudflare-first in `D:\项目\SoulDance\app\src\main\java\com\example\shopguideagent\config\AppConfig.kt`.
- Deleted obsolete `D:\项目\SoulDance\app\src\test\java\com\example\shopguideagent\config\AppConfigTest.java`; it asserted the old `10.0.2.2:8000` emulator backend.
- Cloudflare backend is live: `https://nsw-lasting-asked-issued.trycloudflare.com/health` returns `200`.
- Direct backend probe for `将两份雀巢咖啡加入购物车` currently compiles to `cart_operation`, but `target.reference=focus_product`, `product_id=None`, and `quantity=1`.
- Catalog has matching products: `p_food_002` and `p_food_023` are both `brand=雀巢`, `sub_category=咖啡`.
- Backend `_product_card()` currently sends `tags = [category, sub_category, brand_region] + extracted_terms[:3]`; it does not send `derived_attributes.generated_tags`.
- Android `displayTags()` already prefers `derivedAttributes.generatedTags`, but `RealtimeChatWebSocketClient.parseProduct()` can only use that if the backend sends `derived_attributes`.

## File Map

Backend files on `mix_A100:/home/huadabioa/houlong/SoulDance`:

- Modify `backend/app/semantic_layer.py`: expand quantity parsing and keep cart command intent deterministic.
- Modify `backend/app/agent.py`: resolve explicit product mentions for cart operations before falling back to focus product; enrich product cards with dynamic tag fields.
- Modify `backend/app/models.py`: add optional dynamic metadata fields to `ProductCard`.
- Modify `backend/app/data_loader.py`: if needed, expose reusable product tag candidates from title, brand, sub-category, extracted terms, reviews, and generated derived data.
- Test `tests/test_api.py`: WebSocket-level cart command tests.
- Test `tests/test_agent_core.py`: agent-level product resolution and dynamic tag tests.

Android files in `D:\项目\SoulDance`:

- Modify `app/src/main/java/com/example/shopguideagent/data/model/RealtimeEvent.kt`: include cart action payload fields.
- Modify `app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt`: parse `cart_update.message`, `cart`, and `items` instead of only `badge_count`.
- Modify `app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`: render cart feedback as assistant text and update badge count from cart total.
- Test `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`: cart feedback handling.
- Keep `app/src/main/java/com/example/shopguideagent/config/AppConfig.kt`: Cloudflare URLs stay active.

---

### Task 1: Lock Cloudflare Config And Remove Old Test Assumptions

**Files:**
- Already deleted: `D:\项目\SoulDance\app\src\test\java\com\example\shopguideagent\config\AppConfigTest.java`
- Verify: `D:\项目\SoulDance\app\src\main\java\com\example\shopguideagent\config\AppConfig.kt`

- [ ] **Step 1: Verify no stale AppConfig test remains**

Run:

```powershell
rg -n "AppConfigTest|defaultBackendUrlsPointToAndroidEmulatorHost|10\.0\.2\.2" D:\项目\SoulDance\app\src\test
```

Expected: no `AppConfigTest` hit. `10.0.2.2` may remain only in resolver tests as a generic base URL, not as the active backend config.

- [ ] **Step 2: Verify Cloudflare config remains active**

Run:

```powershell
Get-Content D:\项目\SoulDance\app\src\main\java\com\example\shopguideagent\config\AppConfig.kt
```

Expected: active constants are:

```kotlin
const val BASE_HTTP_URL = "https://nsw-lasting-asked-issued.trycloudflare.com"
const val BASE_WS_URL = "wss://nsw-lasting-asked-issued.trycloudflare.com"
```

---

### Task 2: Add Failing Backend Tests For Named-Product Cart Commands

**Files:**
- Modify: `/home/huadabioa/houlong/SoulDance/tests/test_api.py`
- Modify: `/home/huadabioa/houlong/SoulDance/tests/test_agent_core.py`

- [ ] **Step 1: Add WebSocket test for direct named-product add**

Add a test using fake LLM/retriever that sends:

```python
{
    "type": "user_message",
    "session_id": "demo_ws_named_cart_nestle",
    "message": "将两份雀巢咖啡加入购物车",
}
```

Expected events:

```python
assert cart_event["type"] == "cart_update"
assert cart_event["action"] == "add_to_cart"
assert cart_event["product_id"] in {"p_food_002", "p_food_023"}
assert cart_event["cart"]["items"][0]["quantity"] == 2
assert "雀巢" in cart_event["cart"]["items"][0]["name"]
assert done_event["type"] == "done"
```

- [ ] **Step 2: Add ambiguity test**

Send `将两份雀巢咖啡加入购物车` when multiple Nestle coffee products match. Decide expected behavior:

```python
# Preferred for low-friction demo:
# choose the best-ranked exact brand + sub_category match deterministically.
```

If product ambiguity is considered unsafe, expected behavior should be `text_delta` asking the user to choose between `p_food_002` and `p_food_023`; do not silently add an unrelated focus product.

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
cd /home/huadabioa/houlong/SoulDance
SERVER_BASE_URL= USE_EMBEDDING=0 SHOPGUIDE_CART_PATH= SHOPGUIDE_SESSION_DIR= \
  env/venv_shopguide_backend/bin/python -m pytest \
  tests/test_api.py::test_websocket_named_product_cart_command_adds_nestle_coffee \
  tests/test_agent_core.py::test_named_product_cart_command_resolves_catalog_product -q
```

Expected before implementation: failure because current code resolves `focus_product`, `product_id=None`, `quantity=1`.

---

### Task 3: Implement Backend Product Mention Resolution For Cart

**Files:**
- Modify: `/home/huadabioa/houlong/SoulDance/backend/app/semantic_layer.py`
- Modify: `/home/huadabioa/houlong/SoulDance/backend/app/agent.py`

- [ ] **Step 1: Expand quantity parsing**

In `semantic_layer._detect_quantity`, support common shopping units beyond `件/个`:

```python
units = ["件", "个", "份", "瓶", "盒", "包", "袋", "罐", "条"]
```

Expected: `两份`, `2瓶`, `三盒` parse correctly.

- [ ] **Step 2: Add explicit product mention resolver**

Add an agent helper near `try_handle_cart_message`:

```python
def _resolve_product_mention_for_cart(self, message: str) -> str | None:
    # Score catalog products by exact brand, sub_category, title terms, and search_text.
    # Return one deterministic product_id only when the top match is clearly stronger.
```

Minimum scoring requirements:

- `brand` exact in message: strong boost.
- `sub_category` exact in message: strong boost.
- title token match such as `雀巢咖啡`: strong boost.
- category or generic words alone should not add a random product.

- [ ] **Step 3: Use explicit mention before focus fallback**

In `try_handle_cart_message`, after semantic frame is built and before `reference_resolver.resolve(...)`, resolve explicit product mentions. If found, use that `product_id` directly. If not found, fall back to existing focus/recent recommendation behavior.

- [ ] **Step 4: Handle ambiguous named products explicitly**

If two products tie closely, return a user-visible assistant response rather than a silent cart noop. Prefer adding a backend event shape that Android can render:

```json
{"type":"text_delta","text":"我找到了两款雀巢咖啡：...你要哪一款？"}
{"type":"done"}
```

If keeping `cart_update`, include `message` and `cart` so Android can show the failure reason.

- [ ] **Step 5: Run backend tests**

Run:

```bash
cd /home/huadabioa/houlong/SoulDance
SERVER_BASE_URL= USE_EMBEDDING=0 SHOPGUIDE_CART_PATH= SHOPGUIDE_SESSION_DIR= \
  env/venv_shopguide_backend/bin/python -m pytest tests/test_api.py tests/test_agent_core.py -q
```

Expected: named-product cart tests pass; existing context-cart tests still pass.

---

### Task 4: Make Android Render Cart Operation Feedback

**Files:**
- Modify: `D:\项目\SoulDance\app\src\main\java\com\example\shopguideagent\data\model\RealtimeEvent.kt`
- Modify: `D:\项目\SoulDance\app\src\main\java\com\example\shopguideagent\data\remote\RealtimeChatWebSocketClient.kt`
- Modify: `D:\项目\SoulDance\app\src\main\java\com\example\shopguideagent\vm\ChatViewModel.kt`
- Test: `D:\项目\SoulDance\app\src\test\java\com\example\shopguideagent\vm\ChatViewModelTest.java`

- [ ] **Step 1: Extend `RealtimeEvent.CartUpdate`**

Add fields:

```kotlin
data class CartUpdate(
    val messageId: String,
    val badgeCount: Int,
    val message: String?,
    val action: String?,
    val productId: String?,
) : RealtimeEvent()
```

- [ ] **Step 2: Parse backend cart snapshot**

In `RealtimeChatWebSocketClient.parseEvent`, compute `badgeCount` from `cart.items[*].quantity` when `badge_count` is absent.

- [ ] **Step 3: Render cart message in chat**

In `ChatViewModel.handleRealtimeEvent`, when `CartUpdate.message` is present, append it to the active assistant bubble or set it as assistant text before `Done`.

- [ ] **Step 4: Add unit test**

Test that a `cart_update` payload with:

```json
{"type":"cart_update","message":"已把雀巢咖啡加入购物车。","cart":{"items":[{"quantity":2}]}}
```

updates badge count to `2` and renders the message, not just finishes a blank assistant bubble.

- [ ] **Step 5: Run Android checks**

Run:

```powershell
$env:JAVA_HOME='D:\项目\SoulDance\.tools\jdk17\jdk-17.0.19+10'
$env:PATH="$env:JAVA_HOME\bin;$env:PATH"
.\gradlew.bat :app:assembleDebug
.\gradlew.bat :app:testDebugUnitTest
```

Expected: compile passes; any remaining unrelated legacy Chat/Cart tests should be triaged separately and not hidden by the Cloudflare/cart changes.

---

### Task 5: Add Dynamic Product Tags To Backend Cards

**Files:**
- Modify: `/home/huadabioa/houlong/SoulDance/backend/app/models.py`
- Modify: `/home/huadabioa/houlong/SoulDance/backend/app/agent.py`
- Optional modify: `/home/huadabioa/houlong/SoulDance/backend/app/data_loader.py`
- Test: `/home/huadabioa/houlong/SoulDance/tests/test_agent_core.py`
- Verify Android display: `D:\项目\SoulDance\app\src\main\java\com\example\shopguideagent\ui\component\HeroProductCard.kt`

- [ ] **Step 1: Define backend card dynamic tag contract**

Add to `ProductCard`:

```python
derived_attributes: dict = Field(default_factory=dict)
positive_feedback_summary: list[str] = Field(default_factory=list)
negative_feedback_summary: list[str] = Field(default_factory=list)
risk_tags: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Generate product-specific tags**

Replace generic-only tag generation in `_product_card()` with a helper:

```python
def _product_dynamic_tags(product: Product) -> list[str]:
    candidates = [
        *product.extracted_terms,
        product.sub_category,
        product.brand,
        # selected title/review terms, capped and deduped
    ]
    return dedupe([tag for tag in candidates if tag and tag != "未知"])[:4]
```

For examples:

- `p_food_002` should include product-specific tags such as `雀巢`, `咖啡`, `速溶`, or `三合一`, not only `食品生活/咖啡/未知`.
- `p_digital_*` phone cards should include phone-specific tags such as `拍照`, `快充`, `轻薄`, or brand/subcategory terms when present.

- [ ] **Step 3: Populate `derived_attributes.generated_tags`**

Return Android-compatible structure:

```python
"derived_attributes": {
    "generated_tags": [
        {"value": "咖啡", "evidence": "title/sub_category", "confidence": 1.0}
    ]
}
```

This lets existing Android `displayTags(generatedTags, fallbackTags, ...)` show dynamic tags without UI rewrites.

- [ ] **Step 4: Add backend tests**

Add a test that calls a recommendation for coffee and asserts:

```python
product = product_event["product"]
assert product["derived_attributes"]["generated_tags"]
assert product["tags"] != [product["category"], product["sub_category"], product.get("brand_region")]
```

- [ ] **Step 5: Verify through Cloudflare**

After restarting backend/tunnel if needed:

```powershell
curl.exe --noproxy "*" -sS --max-time 20 https://nsw-lasting-asked-issued.trycloudflare.com/api/products?limit=1
```

Then perform a WebSocket recommendation and inspect `product_item.product.derived_attributes.generated_tags`.

---

### Task 6: End-To-End Acceptance

**Files:**
- Runtime only; no extra source file unless failures expose missing tests.

- [ ] **Step 1: Backend smoke via Cloudflare**

Send over WebSocket:

```json
{"type":"user_message","session_id":"accept_cart_named","message":"将两份雀巢咖啡加入购物车"}
```

Expected:

- `cart_update.action == "add_to_cart"`
- `cart_update.product_id` is a Nestle coffee product.
- `cart.items[*].quantity == 2`
- Android-visible message is non-empty.
- `done` arrives.

- [ ] **Step 2: Product tag smoke**

Send a recommendation request for two different categories, for example coffee and phone. Expected: product cards show different tag sets tied to each product.

- [ ] **Step 3: Android manual QA**

On phone using Cloudflare config:

- Ask `将两份雀巢咖啡加入购物车`.
- Confirm assistant says what happened.
- Confirm cart badge increments by 2.
- Open cart and confirm Nestle coffee item quantity is 2.
- Ask for a coffee recommendation and a phone recommendation.
- Confirm the tags under each product are not the same generic default set.
