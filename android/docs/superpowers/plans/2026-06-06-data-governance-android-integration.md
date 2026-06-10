# Data Governance And Android Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a verifiable pilot path for ShopGuide Agent where Houlong owns data governance, Android, and UI integration, while the RAG/cache service is delivered by a separate backend owner.

**Architecture:** Houlong's scope produces clean product data, review/tag governance outputs, Android protocol adapters, and the Compose user experience. The RAG owner provides retrieval, cache hits, model comparison, and recommendation decisions through the agreed backend protocol. Android consumes streamed WebSocket/REST events, renders the primary product, alternatives, bundle groups, cart/order state, product-focused follow-up, and a simplified read-aloud control. Local catalog scoring stays only as a demo/offline fallback and must be visibly separated from the production path.

**Tech Stack:** Kotlin, Jetpack Compose, MVVM, StateFlow, OkHttp WebSocket, Coil, JUnit, Python data pipeline, Pydantic schemas, Gradle Wrapper.

---

## Scope And Ownership

**Owners**
- RAG/cache service: Huiruize leads; Houlong consumes the agreed contract and validates Android behavior.
- Data governance: Houlong leads dataset quality, review filtering rules, generated tag requirements, image references, and Android-ready product fields.
- Android UI/client: Houlong leads.
- Joint acceptance: both owners run the demo checklist and compare backend traces with Android UI behavior.

**Houlong in scope for this pilot**
- Dataset enrichment and review filtering.
- Android-facing RAG/cache contract checklist and measurable integration acceptance.
- WebSocket protocol completion on Android.
- Product-focused follow-up with `focus_product_id`.
- Basic cart/order flow verification.
- UI polish for the current ChatScreen, product cards, bottom sheet, and simplified read-aloud button.

**Huiruize dependency for this pilot**
- RAG retrieval implementation.
- Cache key/store/invalidation implementation.
- Model comparison implementation.
- Backend recommendation decisioning and streamed product events.

**Out of scope for this pilot**
- Phone-call voice interaction.
- Complex image recognition or "find same item by image".
- Client-side hardcoded recommendation logic.
- Client-side TTS/LLM API keys.
- Houlong implementing the RAG cache internals.

---

## File Structure

### Backend/Data Pipeline

- Modify: `server/app/data_pipeline/schemas.py`
  - Add Android/RAG-ready data governance fields if they are missing from enriched product output: searchable tags, review safety labels, image references, and product evidence.
- Modify: `server/app/data_pipeline/derive_attributes.py`
  - Ensure LLM-derived tags come from product detail fields, product description, and review evidence, not existing weak tags alone.
- Modify: `server/app/data_pipeline/chunk_builder.py`
  - Produce governed chunks that include text plus product image references for the RAG owner to consume.
- Modify: `server/app/data_pipeline/validators.py`
  - Validate required product/image/review/tag fields and flag blocked review content.
- Create: `server/app/data_pipeline/review_filter.py`
  - Classify reviews as usable, irrelevant, malicious, unsafe, or low-signal, and return an auditable exclusion reason.
- Modify: `server/tests/test_data_pipeline.py`
  - Add deterministic tests for review relevance filtering, malicious/irrelevant review exclusion, generated tags, image references, and RAG handoff fields.

### Android Protocol And State

- Modify: `app/src/main/java/com/example/shopguideagent/data/model/RealtimeEvent.kt`
  - Add all backend event types from `docs/15_BACKEND_ANDROID_PROTOCOL.md`: bundle, focus, replacement, audio, cart, done, and error.
- Modify: `app/src/main/java/com/example/shopguideagent/data/model/Product.kt`
  - Ensure product models carry backend/data-governance generated tags with confidence/evidence when available, while preserving the existing simple `tags` UI list.
- Modify: `app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt`
  - Implement OkHttp WebSocket connect/send/close and JSON parsing.
- Modify: `app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
  - Move production recommendation flow to backend events. Keep local `ProductCatalog` only behind an explicit demo/offline path.
- Modify: `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`
  - Replace tests that expect local recommendation generation with event-driven tests.
- Create: `app/src/test/java/com/example/shopguideagent/data/remote/RealtimeEventParserTest.kt`
  - Parser tests for all event types and unknown/error handling.

### Android UI And Interaction

- Modify: `app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`
  - Keep lazy scroll stable, show connection/error state, and route focus follow-up through backend.
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/AiMessageBlock.kt`
  - Render text, primary product, alternatives, and bundle sections as event data arrives.
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductCard.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/HeroProductCard.kt`
  - Render generated product tags below the product title/reason area without changing card height unexpectedly.
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductImage.kt`
  - Polish product card hierarchy and image fallback.
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductDetailBottomSheet.kt`
  - Keep the bottom sheet open for focused follow-up response, render `focus_text_delta` and `replacement_product`.
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/SpeakerToggle.kt`
  - Convert TTS toggle into a read-aloud button state: idle, reading, stopped, unavailable.
- Modify: `app/src/main/java/com/example/shopguideagent/audio/StreamingAudioPlayer.kt`
  - Release AudioTrack and support stop/replay for read-aloud.

### Android Cart/Order

- Modify: `app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt`
  - Add repository seam for backend cart REST when available, preserving in-memory fallback for demo.
- Modify: `app/src/main/java/com/example/shopguideagent/data/remote/CartApiClient.kt`
  - Implement REST request/response mapping or mock-server compatible interface.
- Modify: `app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.java`
  - Verify add/update/remove/select/checkout count and total behavior.

### Documentation And Verification

- Modify: `docs/15_BACKEND_ANDROID_PROTOCOL.md`
  - Make protocol UTF-8 clean and add exact JSON examples for every event.
- Modify: `docs/16_DEMO_AND_EVAL_CHECKLIST.md`
  - Add RAG cache, model comparison, and Android UI smoke checks.
- Create: `docs/rag-android-contract-checklist.md`
  - Document the RAG owner's required event fields, cache status metadata, latency fields, and product payload rules.
- Create: `docs/rag-cache-pilot-report.md`
  - Capture pilot queries, cache hit rate, first token latency, first card latency, and model comparison notes.

---

## Milestone 0: Baseline Verification

### Task 0.1: Confirm Current Build And Tests

**Files:**
- Read: `app/build.gradle.kts`
- Read: `server/tests/test_data_pipeline.py`

- [ ] **Step 1: Run Android unit tests**

Run:

```bat
gradlew.bat :app:testDebugUnitTest
```

Expected: build finishes and reports `BUILD SUCCESSFUL`.

- [ ] **Step 2: Run Android debug build**

Run:

```bat
gradlew.bat :app:assembleDebug
```

Expected: debug APK is produced without Kotlin/Compose compile errors.

- [ ] **Step 3: Run backend data pipeline tests**

Run:

```bat
python -m unittest server.tests.test_data_pipeline
```

Expected: all data pipeline tests pass.

- [ ] **Step 4: Record baseline gaps**

Write any failures into `docs/rag-cache-pilot-report.md` under `Baseline`.

Expected: every later task can compare against this baseline.

---

## Milestone 1: Dataset, Tags, Review Filtering, And RAG Chunks

### Task 1.1: Add Product Review Relevance And Abuse Filtering

**Files:**
- Create: `server/app/data_pipeline/review_filter.py`
- Modify: `server/tests/test_data_pipeline.py`
- Modify: `server/app/data_pipeline/schemas.py`
- Modify: `server/app/data_pipeline/validators.py`
- Modify: `server/app/data_pipeline/chunk_builder.py`

- [ ] **Step 1: Add failing tests for irrelevant malicious reviews**

Add sample reviews such as:

```python
reviews = [
    {"rating": 1, "content": "物流太慢，客服态度差，和商品没关系"},
    {"rating": 1, "content": "竞品更好，这家就是垃圾，别买"},
    {"rating": 5, "content": "这款防晒不黏，户外两小时也没有明显闷痘"},
]
```

Assert:
- logistics/customer-service-only reviews are classified as `irrelevant`
- abusive or suspected malicious reviews are classified as `malicious`
- product-experience reviews are kept
- excluded reviews do not appear in RAG chunks

Expected failing reason before implementation: no review relevance/abuse classifier exists.

- [ ] **Step 2: Add failing tests for product-detail-derived tags**

Assert that a product with detail text such as `适合敏感肌、通勤防晒、无酒精` produces richer generated tags independent of the original `sub_category`.

Required generated tag properties:
- tag value is short enough for UI display, ideally 2-8 Chinese characters
- tag has evidence from product detail, description, or product-relevant review
- tag has confidence
- low-confidence or unsupported tags are excluded from the UI-facing top tags

- [ ] **Step 3: Implement review classifier**

Create `server/app/data_pipeline/review_filter.py` with a deterministic first-pass classifier:

```python
PRODUCT_SIGNAL_KEYWORDS = ("肤感", "效果", "材质", "尺码", "续航", "味道", "成分", "防晒", "控油", "保湿")
IRRELEVANT_KEYWORDS = ("物流", "快递", "客服", "包装破损", "发货", "仓库")
MALICIOUS_KEYWORDS = ("垃圾", "骗子", "刷单", "竞品", "全是假货")

def classify_review(content: str) -> tuple[str, str]:
    text = content.strip()
    if any(keyword in text for keyword in MALICIOUS_KEYWORDS):
        return "malicious", "contains_abuse_or_competitor_attack"
    if any(keyword in text for keyword in IRRELEVANT_KEYWORDS) and not any(keyword in text for keyword in PRODUCT_SIGNAL_KEYWORDS):
        return "irrelevant", "not_about_product_experience"
    if not any(keyword in text for keyword in PRODUCT_SIGNAL_KEYWORDS):
        return "low_signal", "no_product_evidence"
    return "usable", "product_experience"
```

Expected: the pilot is deterministic and auditable. Later the keyword lists can be replaced or augmented by an LLM classifier.

- [ ] **Step 4: Implement minimal schema/validator updates**

Add fields such as:

```python
class DerivedAttributes(BaseModel):
    # existing fields remain
    generated_tags: List[EvidenceItem] = Field(default_factory=list)
    review_filter_flags: List[EvidenceItem] = Field(default_factory=list)
```

Expected: existing tests still pass and new tests can assert the output shape.

- [ ] **Step 5: Exclude blocked reviews from chunks**

Update `server/app/data_pipeline/chunk_builder.py` so only `usable` reviews can contribute to `review_positive` and `review_negative` chunks.

Expected: negative product-experience reviews are preserved, but unrelated malicious reviews are blocked from retrieval.

- [ ] **Step 6: Run focused backend tests**

Run:

```bat
python -m unittest server.tests.test_data_pipeline
```

Expected: review relevance filtering, malicious review exclusion, and generated tag tests pass.

### Task 1.2: Produce Accurate UI-Facing Product Tags

**Files:**
- Modify: `server/app/data_pipeline/derive_attributes.py`
- Modify: `server/app/data_pipeline/schemas.py`
- Modify: `server/tests/test_data_pipeline.py`
- Modify if needed: `app/src/main/java/com/example/shopguideagent/data/catalog/ProductCatalog.kt`
- Modify if needed: `app/src/main/java/com/example/shopguideagent/data/model/Product.kt`

- [ ] **Step 1: Add failing tests for accurate generated tags**

Use a sample product with details, description, and reviews:

```python
product = sample_product() | {
    "sub_category": "防晒",
    "rag_knowledge": {
        "marketing_description": "无酒精配方，肤感清爽，适合敏感肌日常通勤防晒。",
        "user_reviews": [
            {"rating": 5, "content": "上脸不油，通勤用很舒服。"},
            {"rating": 4, "content": "敏感肌用了没有刺痛。"},
        ],
    },
}
```

Assert top tags include examples such as:

```text
无酒精, 清爽肤感, 敏感肌, 通勤防晒
```

Expected failing reason before implementation: tags are still too dependent on `sub_category` or generic keyword matching.

- [ ] **Step 2: Add tag quality rules**

Generated UI tags must satisfy:
- derived from product detail, description, product-relevant reviews, or structured attributes
- not copied blindly from category
- not based on excluded malicious/irrelevant reviews
- max 4 UI tags per product
- each tag has evidence and confidence
- duplicate/synonym tags are merged, such as `清爽` and `清爽肤感`

- [ ] **Step 3: Implement generated tag extraction**

In `server/app/data_pipeline/derive_attributes.py`, make generated tags part of `DerivedAttributes.generated_tags`. For dry-run/deterministic tests, implement a rule-based fallback from detail text and usable reviews; when an LLM is used, validate the LLM output against the same tag quality rules.

Expected: output remains deterministic in tests and richer in model-backed runs.

- [ ] **Step 4: Map generated tags to Android product payload**

Ensure `ProductCatalog.kt` or backend event parsing prefers `generated_tags` for card display, then falls back to existing `tags` only when generated tags are empty.

Expected: Android UI uses accurate product-specific tags, not generic category labels.

- [ ] **Step 5: Run focused tests**

Run:

```bat
python -m unittest server.tests.test_data_pipeline
gradlew.bat :app:testDebugUnitTest --tests "*ProductCatalogScorerTest"
```

Expected: generated tag tests pass and Android product parsing still compiles/tests.

### Task 1.3: Add Image References To RAG Chunks

**Files:**
- Modify: `server/app/data_pipeline/chunk_builder.py`
- Modify: `server/tests/test_data_pipeline.py`

- [ ] **Step 1: Add failing test for product image reference**

Assert every product-level chunk includes `product_id`, `image_path`, and `chunk_type`.

Expected failing reason before implementation: chunk metadata lacks image path on at least one chunk type.

- [ ] **Step 2: Add chunk metadata implementation**

Ensure chunk output contains:

```json
{
  "product_id": "p_test_001",
  "chunk_type": "attribute_summary",
  "content": "...",
  "image_path": "images/p_test_001.jpg"
}
```

Expected: Android can associate streamed text/product cards with actual images.

- [ ] **Step 3: Run focused backend tests**

Run:

```bat
python -m unittest server.tests.test_data_pipeline
```

Expected: all chunk tests pass.

---

## Milestone 2: RAG Contract Handoff And Integration Acceptance

### Task 2.1: Define The RAG Owner Delivery Contract

**Files:**
- Create: `docs/rag-android-contract-checklist.md`
- Modify: `docs/15_BACKEND_ANDROID_PROTOCOL.md`
- Modify: `docs/16_DEMO_AND_EVAL_CHECKLIST.md`

- [ ] **Step 1: Document required RAG response metadata**

In `docs/rag-android-contract-checklist.md`, require the RAG owner to expose these fields in backend traces or stream metadata:

```text
cache_status: hit | miss | bypass
model_name: doubao | chatgpt | other
retrieval_version: string
cache_key_debug: non-secret string or hash
first_token_ms: number
first_card_ms: number
primary_product_id: string
```

Expected: Android and UI validation can measure RAG behavior without Houlong implementing RAG internals.

- [ ] **Step 2: Document product payload rules**

Require streamed products to include:

```text
product_id, title/name, price, image_url or image_path, reason, generated_tags, tags fallback, role(primary|alternative), evidence/risk fields when available
```

Expected: Android can render real backend-selected products and image fallback without guessing.

- [ ] **Step 3: Document focused follow-up payload rules**

Require:

```text
client request: type=product_followup, session_id, focus_product_id, message
backend response: focus_text_delta, replacement_product, focus_done, error
```

Expected: context anchoring remains testable at the Android boundary.

### Task 2.2: Build The RAG Integration Report Template

**Files:**
- Create: `docs/rag-cache-pilot-report.md`
- Modify: `docs/16_DEMO_AND_EVAL_CHECKLIST.md`

- [ ] **Step 1: Add pilot measurement table**

In `docs/rag-cache-pilot-report.md`, add columns:

```text
query | model | cache_status | first_token_ms | first_card_ms | primary_product_id | focus_product_id | android_result | notes
```

- [ ] **Step 2: Add owner split to the report**

Add:

```text
RAG owner:
Data governance owner:
Android/UI owner:
Backend endpoint/date:
Dataset version:
```

- [ ] **Step 3: Add pass/fail criteria**

Acceptance:
- cache metadata is present for every RAG response
- primary product id in backend trace matches Android UI
- focused follow-up request includes `focus_product_id`
- replacement product appears in the bottom sheet flow
- no Android-side recommendation fallback is used in production mode

Expected: Houlong can verify the friend's RAG work through observable contract behavior.

---

## Milestone 3: Backend-Android Protocol Completion

### Task 3.1: Expand Realtime Event Model And Parser

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/data/model/RealtimeEvent.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt`
- Create: `app/src/test/java/com/example/shopguideagent/data/remote/RealtimeEventParserTest.kt`

- [ ] **Step 1: Write parser tests for all event types**

Cover:

```text
text_delta, products_start, product_item, products_done,
bundle_start, bundle_item, bundle_done,
focus_text_delta, replacement_product, focus_done,
audio_delta, cart_update, done, error, unknown
```

Expected failing reason before implementation: only a subset of events exists.

- [ ] **Step 2: Add sealed classes**

Add missing events to `RealtimeEvent.kt`, keeping unknown raw payload support.

- [ ] **Step 3: Implement JSON parser function**

Expose a pure parser such as:

```kotlin
internal fun parseRealtimeEvent(raw: String): RealtimeEvent
```

Expected: parser can be unit tested without network.

- [ ] **Step 4: Run focused Android tests**

Run:

```bat
gradlew.bat :app:testDebugUnitTest --tests "*RealtimeEventParserTest"
```

Expected: parser tests pass.

### Task 3.2: Implement OkHttp WebSocket Client

**Files:**
- Modify: `app/build.gradle.kts`
- Modify: `app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt`
- Modify: `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`

- [ ] **Step 1: Add OkHttp dependency if missing**

Add:

```kotlin
implementation("com.squareup.okhttp3:okhttp:4.12.0")
```

- [ ] **Step 2: Add client lifecycle tests where possible**

Test parser and send payload construction as pure functions. Avoid network in unit tests.

- [ ] **Step 3: Implement connect/send/close**

Requirements:
- `connect()` emits parsed events.
- `sendUserMessage()` sends `type=user_message`, `session_id`, `message`, `input_type=text`, and `tts_enabled`.
- `sendProductFollowUp()` or equivalent sends `type=product_followup` and `focus_product_id`.
- `close()` releases WebSocket without crashing.

- [ ] **Step 4: Run tests and compile**

Run:

```bat
gradlew.bat :app:testDebugUnitTest
gradlew.bat :app:assembleDebug
```

Expected: tests and build pass.

---

## Milestone 4: Event-Driven Android Chat Flow

### Task 4.1: Replace Production Local Recommendation With Backend Events

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
- Modify: `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`

- [ ] **Step 1: Write failing ViewModel event tests**

Cases:
- `text_delta` appends assistant text.
- `products_start` shows skeleton count.
- `product_item` replaces skeleton with real product.
- `error` sets `errorMessage`.
- `done` clears `isSending`.

Expected failing reason before implementation: ViewModel currently synthesizes recommendations locally.

- [ ] **Step 2: Introduce backend event handler**

Add a pure method:

```kotlin
fun onRealtimeEvent(event: RealtimeEvent)
```

Expected: tests can call it directly.

- [ ] **Step 3: Gate local catalog fallback**

Production path: backend events only.
Demo fallback path: only active when explicitly configured, such as `AppConfig.USE_LOCAL_DEMO_CATALOG`.

- [ ] **Step 4: Verify no client recommendation leakage**

Search:

```bat
rg -n "recommend\\(|replyFor\\(|productFollowUpReply\\(" app\src\main\java
```

Expected: production send path does not call local recommendation generation.

### Task 4.2: Keep Product Follow-Up Anchored

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductDetailBottomSheet.kt`
- Modify: `app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`

- [ ] **Step 1: Write failing test for `focus_product_id`**

Assert bottom-sheet follow-up sends payload containing the selected product id.

Expected failing reason before implementation: current method simulates a replacement locally.

- [ ] **Step 2: Keep bottom sheet open during focus stream**

`focus_text_delta` updates bottom-sheet state; `replacement_product` appears in the same sheet; `focus_done` stops loading.

- [ ] **Step 3: Run tests**

Run:

```bat
gradlew.bat :app:testDebugUnitTest --tests "*ChatViewModelTest"
```

Expected: focus tests pass.

---

## Milestone 5: UI Polish And Low-Pressure Interaction

### Task 5.1: Product Card Hierarchy And Image Fallback

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/HeroProductCard.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductCard.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/ProductImage.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/AiMessageBlock.kt`

- [ ] **Step 1: Preserve primary product visual priority**

Primary product is larger and visually stronger. Alternatives are secondary and capped at 1-2.

- [ ] **Step 2: Ensure image fallback is visible**

Broken images render a stable fallback with product name/category and do not collapse card height.

- [ ] **Step 3: Render generated tags below product card content**

Display up to 4 generated tags below the product title/reason area:
- primary card can show 3-4 tags
- alternative cards can show 2-3 tags
- tags wrap cleanly on narrow screens
- tags do not push price/add-to-cart controls out of view
- when `generated_tags` is empty, fall back to existing `tags`

Expected: users can quickly understand why the product is relevant, such as `敏感肌`, `无酒精`, `清爽肤感`, `通勤防晒`.

- [ ] **Step 4: Add a lightweight UI parsing/rendering test if feasible**

If there is no Compose UI test harness for card rendering, add a pure helper test for selecting display tags:

```kotlin
fun displayTags(generatedTags: List<String>, fallbackTags: List<String>, maxCount: Int): List<String>
```

Expected: generated tags are preferred, duplicates are removed, and fallback tags are used only when needed.

- [ ] **Step 5: Verify Compose preview/compile**

Run:

```bat
gradlew.bat :app:assembleDebug
```

Expected: no Compose layout compile errors.

### Task 5.2: Chat Scroll And Streaming Stability

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`
- Modify: `app/src/test/java/com/example/shopguideagent/ui/screen/ChatScrollTargetTest.java`

- [ ] **Step 1: Extend scroll tests**

Assert token streaming does not force-scroll when user is reading older content.

- [ ] **Step 2: Keep skeleton/product reveal stable**

Skeleton count comes from `products_start`; card dimensions stay stable as `product_item` arrives.

- [ ] **Step 3: Run UI logic tests**

Run:

```bat
gradlew.bat :app:testDebugUnitTest --tests "*ChatScrollTargetTest"
```

Expected: scroll tests pass.

### Task 5.3: Simplify TTS Into Read-Aloud Button

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/ui/component/SpeakerToggle.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/audio/StreamingAudioPlayer.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`

- [ ] **Step 1: Replace "TTS 开/关" wording**

Use an action button state: `朗读`, `停止`, `不可用`.

- [ ] **Step 2: Keep text and product stream independent from audio**

If `audio_delta` fails or is absent, text/product UI still completes.

- [ ] **Step 3: Verify release behavior**

On screen dispose, release AudioTrack. On stop, clear queue.

- [ ] **Step 4: Run build**

Run:

```bat
gradlew.bat :app:assembleDebug
```

Expected: build passes.

---

## Milestone 6: Cart, Order, And History Verification

### Task 6.1: Cart REST Seam

**Files:**
- Modify: `app/src/main/java/com/example/shopguideagent/data/remote/CartApiClient.kt`
- Modify: `app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt`
- Modify: `app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.java`

- [ ] **Step 1: Add repository/client seam tests**

Assert add/update/remove/select/clear/checkout can be verified without UI.

- [ ] **Step 2: Keep local fallback for demo**

If backend cart is unavailable, show a clear error or use explicitly configured local demo mode. Do not silently pretend server success in production mode.

- [ ] **Step 3: Run cart tests**

Run:

```bat
gradlew.bat :app:testDebugUnitTest --tests "*CartViewModelTest"
```

Expected: cart count, selected count, totals, and checkout result tests pass.

### Task 6.2: History Smoke Check

**Files:**
- Modify if needed: `app/src/main/java/com/example/shopguideagent/data/history/ChatHistoryRepository.kt`
- Modify if needed: `app/src/test/java/com/example/shopguideagent/data/history/ChatHistoryRepositoryTest.java`

- [ ] **Step 1: Verify conversation persistence**

Run:

```bat
gradlew.bat :app:testDebugUnitTest --tests "*ChatHistoryRepositoryTest"
```

Expected: sessions can be saved, selected, and restored.

---

## Milestone 7: Joint Demo And Evaluation

### Task 7.1: Update Demo Checklist

**Files:**
- Modify: `docs/16_DEMO_AND_EVAL_CHECKLIST.md`
- Modify: `docs/rag-cache-pilot-report.md`

- [ ] **Step 1: Add required pilot queries**

Include:

```text
1. 推荐一款适合油皮的洗面奶，预算100以内
2. 推荐防晒霜，但不要含酒精，也不要日系品牌
3. 下周去三亚度假，帮我搭配一套从防晒到穿搭的方案
4. 点开主推商品后问：这个有点贵，有没有100以内的？
5. 点开主推商品后问：这个适合敏感肌吗？
6. 把第一款加入购物车，把数量改成2
7. 看看购物车，然后下单
```

- [ ] **Step 2: Add measurable acceptance columns**

Track:
- cache status: hit/miss
- first token latency
- first product card latency
- model name
- primary product id
- `focus_product_id`
- cart item count
- crash/error notes

### Task 7.2: Full Verification Run

**Files:**
- Read: `docs/16_DEMO_AND_EVAL_CHECKLIST.md`
- Write: `docs/rag-cache-pilot-report.md`

- [ ] **Step 1: Run all automated tests**

Run:

```bat
python -m unittest server.tests.test_data_pipeline
gradlew.bat :app:testDebugUnitTest
gradlew.bat :app:assembleDebug
```

Expected: Houlong-owned data governance tests, Android unit tests, and Android build all pass. RAG owner provides separate evidence for RAG/cache internals.

- [ ] **Step 2: Install and launch app**

Run on an available emulator/device:

```bat
adb install -r app\build\outputs\apk\debug\app-debug.apk
adb shell monkey -p com.example.shopguideagent 1
```

Expected: app launches, ChatScreen displays, no crash.

- [ ] **Step 3: Manual Android acceptance**

Verify:
- no network/backend error shows a friendly message
- `text_delta` streams without UI jitter
- skeletons appear before product cards
- primary product is visually dominant
- image failure fallback appears
- bottom sheet opens and closes
- focused follow-up carries `focus_product_id`
- replacement product appears inside the focused flow
- cart badge count is correct
- checkout produces order result
- voice input releases SpeechRecognizer
- read-aloud stop/release does not crash
- WebSocket close does not crash

- [ ] **Step 4: Joint sign-off**

Record in `docs/rag-cache-pilot-report.md`:

```text
Backend owner:
Android owner:
Date:
Known issues:
Decision: pass / pass with issues / fail
```

---

## Risk Controls

- Android must not decide which product to recommend in production mode. Backend streamed product events are the source of truth.
- RAG owner cache metadata must include model/index versions so stale answers do not survive data refresh.
- Review filtering must preserve evidence. Do not delete all negative reviews; keep product-relevant negative reviews as risk signals, and only exclude irrelevant logistics/customer-service-only reviews, malicious attacks, unsafe content, and low-signal noise from RAG chunks.
- Generated product tags must be evidence-backed. Do not display tags that come only from generic category names or unsupported model guesses.
- Product follow-up must include `focus_product_id`; otherwise context pollution invalidates the demo.
- Audio failure must never block text/product rendering.
- The existing docs show encoding corruption in some reads; rewrite touched docs as clean UTF-8 when editing them.

---

## Definition Of Done

- `python -m unittest server.tests.test_data_pipeline` passes for Houlong-owned data governance work.
- `gradlew.bat :app:testDebugUnitTest` passes.
- `gradlew.bat :app:assembleDebug` passes.
- RAG owner provides endpoint/trace evidence for cache status, model name, and latency fields.
- Data pipeline classifies malicious/irrelevant reviews with auditable reasons and excludes them from RAG chunks while preserving product-relevant negative reviews.
- Data pipeline generates accurate product-specific tags from product details, description, and usable review evidence.
- Android product cards display generated tags below the product content, with fallback to existing tags only when generated tags are unavailable.
- Demo checklist seven queries are recorded in `docs/rag-cache-pilot-report.md`.
- Android displays only backend-returned products in production mode.
- `product_followup` requests include `focus_product_id`.
- No-network, WebSocket disconnect, image failure, and audio failure paths show non-crashing UI.
- Cart count and checkout result are correct.
