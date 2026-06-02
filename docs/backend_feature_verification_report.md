# SoulDance ShopGuide Backend Feature Verification Report

Date: 2026-06-01

Purpose: this report is for teammates to verify the current backend implementation. It focuses only on backend capabilities, API behavior, RAG/Agent correctness, and known acceptance criteria.

## 1. Version Under Test

Remote project:

```text
/home/huadabioa/houlong/SoulDance
```

Expected branch:

```text
codex/rag-memory-reranker
```

Expected latest commits:

```text
8a0e14c feat: add restrained active clarification policy
c7e0355 fix: enforce dataset taxonomy constraints
c058416 docs: add backend feature verification report
a0f7a73 docs: document rag memory reranker implementation
8093630 feat: add rag memory cache and evidence reranker
```

Backend environment:

```text
env/venv_shopguide_backend
```

Recommended quick-check mode:

```bash
USE_EMBEDDING=0 HOST=127.0.0.1 PORT=18080 bash scripts/start_backend.sh
```

Real LLM mode needs runtime environment variables:

```bash
export ARK_API_KEY="runtime key, do not write into source"
export ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3/"
export ARK_MODEL="ep-20260514111645-lmgt2"
```

Optional structured cache persistence:

```bash
export SHOPGUIDE_MEMORY_CACHE_PATH="cache/shopguide_memory.jsonl"
```

## 2. Current Backend Capabilities

| Area | Implemented capability | Verification status |
|---|---|---|
| Product data | Loads 100 products from `ecommerce_agent_dataset` | To verify |
| Taxonomy resolver | Reads real `category/sub_category` values from dataset and validates aliases against that taxonomy | To verify |
| RAG retrieval | BM25 plus optional embedding retrieval | To verify |
| Hard filters | Budget, category, sub-category, excluded terms, excluded brand region, excluded brand | To verify |
| LLM semantic layer | LLM parses intent; backend rule guards preserve hard constraints | To verify |
| Compiler-style executor | Backend deterministically performs retrieval, filtering, ranking, cart mutation, event rendering | To verify |
| Streaming API | WebSocket emits ordered assistant/product/cart events | To verify |
| Active clarification | Emits one-question `clarification_request` for high-uncertainty requests such as generic phone, laptop, gift, or skincare needs | To verify |
| Product cards | Emits structured `product_item` cards with price, brand, reason, evidence | To verify |
| Multi-turn followup | Maintains session constraints and product focus | To verify |
| Comparison | Compares products from recent recommendation memory | To verify |
| Scenario bundle | Streams grouped bundle recommendation items | To verify |
| Cart flow | Supports add/update/remove/clear/checkout plus natural-language cart operations | To verify |
| Memory cache | Reuses structured recommendation results without crossing hard constraints | To verify |
| Evidence reranker | Filters noisy review evidence and preserves sensitive-skin risk evidence | To verify |
| Documentation | Backend environment, protocol, architecture, and RAG/reranker docs exist | To verify |

## 3. Automated Verification

Run from remote project root:

```bash
cd /home/huadabioa/houlong/SoulDance
env/venv_shopguide_backend/bin/python -m pytest tests/test_agent_core.py tests/test_api.py -q
```

Expected result:

```text
41 passed, 1 warning
```

The warning is currently from `jieba` / `pkg_resources` and is not expected to block the demo.

Acceptance:

- [ ] Test command exits with code 0.
- [ ] All 41 tests pass.
- [ ] No API key appears in test output.

## 4. Service Startup Verification

Start backend:

```bash
cd /home/huadabioa/houlong/SoulDance
USE_EMBEDDING=0 HOST=127.0.0.1 PORT=18080 ARK_API_KEY="$ARK_API_KEY" bash scripts/start_backend.sh
```

In another terminal:

```bash
curl -sS http://127.0.0.1:18080/health
```

Expected fields:

```json
{
  "status": "ok",
  "product_count": 100,
  "llm": "doubao",
  "retriever": "bm25",
  "memory_cache": {
    "hits": 0,
    "misses": 0,
    "writes": 0,
    "size": 0
  }
}
```

Notes:

- `retriever` may be `embedding` if embedding is enabled and loaded.
- `llm` is `fake` if `ARK_API_KEY` is not set.

Acceptance:

- [ ] `/health` returns HTTP 200.
- [ ] `product_count` is 100.
- [ ] `memory_cache` stats are present.
- [ ] `llm` is `doubao` for real LLM verification.

## 5. Product API Verification

Command:

```bash
curl -sS "http://127.0.0.1:18080/api/products?limit=2"
```

Expected:

- Response contains `products`.
- Each product has `product_id`, `title`, `brand`, `category`, `sub_category`, `price`, `image_path`.

Acceptance:

- [ ] HTTP 200.
- [ ] At least 2 products returned.
- [ ] Product IDs are non-empty.
- [ ] Prices are numeric.

## 6. WebSocket Recommendation Verification

Use a WebSocket client to connect:

```text
ws://127.0.0.1:18080/ws/chat
```

Send:

```json
{
  "type": "user_message",
  "session_id": "verify_recommend_001",
  "message": "推荐防晒霜，但不要含酒精的，也不要日系品牌",
  "input_type": "text",
  "tts_enabled": false
}
```

Expected event order:

```text
assistant_state
text_delta
products_start
product_item...
products_done
text_delta
quick_actions
done
```

Acceptance:

- [ ] Event order matches expected order.
- [ ] At least one `product_item` is returned.
- [ ] Returned product `sub_category` is `防晒`.
- [ ] Returned product brand region is not `日本`.
- [ ] Evidence does not claim unsupported attributes.

## 7. Hard Constraint Verification

### 7.1 Budget

Send:

```json
{
  "type": "user_message",
  "session_id": "verify_budget_001",
  "message": "推荐精华，预算100以内"
}
```

Acceptance:

- [ ] Product cards, if any, have `price <= 100`.
- [ ] Product cards, if any, have `sub_category=精华`.
- [ ] If no product matches, backend returns `filter_recovery_options`.

### 7.2 Excluded Brand

Send:

```json
{
  "type": "user_message",
  "session_id": "verify_no_apple_001",
  "message": "我想给大学生买一台轻薄笔记本，预算6000以内，不要苹果"
}
```

Acceptance:

- [ ] No `product_item.product.brand` contains `Apple` or `苹果`.
- [ ] Product cards, if any, have `sub_category=笔记本电脑`.
- [ ] Text response must not say one thing while card violates it.

### 7.3 Excluded Ingredient / Region

Send:

```json
{
  "type": "user_message",
  "session_id": "verify_no_alcohol_japan_001",
  "message": "推荐防晒霜，但不要含酒精的，也不要日系品牌"
}
```

Acceptance:

- [ ] No Japanese-brand product is returned.
- [ ] Product evidence should not contradict the no-alcohol requirement.

### 7.4 Unknown Taxonomy Request

Send:

```json
{
  "type": "user_message",
  "session_id": "verify_unknown_taxonomy_001",
  "message": "推荐毛巾"
}
```

Acceptance:

- [ ] Backend does not return unrelated food, beauty, apparel, or digital product cards to fill the result.
- [ ] Response includes no-match recovery guidance or clarification-style text.
- [ ] No product card is emitted unless the dataset actually contains a matching towel taxonomy entry.

## 8. Active Clarification Verification

### 8.1 Ambiguous Phone

Send:

```json
{
  "type": "user_message",
  "session_id": "verify_clarify_phone_001",
  "message": "推荐一款手机"
}
```

Acceptance:

- [ ] Response includes `clarification_request`.
- [ ] Response does not include `product_item`.
- [ ] Question asks about photo, battery life, or value-for-money priority.

### 8.2 Clarification Answer

Using the same session, send:

```json
{
  "type": "user_message",
  "session_id": "verify_clarify_phone_001",
  "message": "拍照优先，预算4000"
}
```

Acceptance:

- [ ] Response does not include `clarification_request`.
- [ ] Product cards, if any, have `sub_category=智能手机`.
- [ ] Product cards, if any, have `price <= 4000`.

### 8.3 Ambiguous Gift / Skincare

Send separately:

```json
{
  "type": "user_message",
  "session_id": "verify_clarify_gift_001",
  "message": "送女朋友礼物"
}
```

```json
{
  "type": "user_message",
  "session_id": "verify_clarify_skincare_001",
  "message": "推荐护肤品"
}
```

Acceptance:

- [ ] Each response includes one `clarification_request`.
- [ ] Neither response emits unrelated product cards just to fill a result.
- [ ] Specific requests such as `推荐精华，预算100以内` still recommend directly.

## 9. Multi-Turn Followup Verification

Step 1: send normal recommendation:

```json
{
  "type": "user_message",
  "session_id": "verify_followup_001",
  "message": "推荐防晒霜，但不要含酒精的，也不要日系品牌"
}
```

Record the first `product_item.product.product_id`.

Step 2: send followup:

```json
{
  "type": "product_followup",
  "session_id": "verify_followup_001",
  "focus_product_id": "<first_product_id>",
  "message": "这个有点贵，有没有100以内的？"
}
```

Acceptance:

- [ ] Backend keeps original category and excluded constraints.
- [ ] If no product matches 100以内 + original exclusions, response includes `filter_recovery_options`.
- [ ] Backend must not emit an out-of-budget `replacement_product`.

## 10. Comparison Verification

Step 1:

```json
{
  "type": "user_message",
  "session_id": "verify_compare_001",
  "message": "推荐防晒霜"
}
```

Step 2:

```json
{
  "type": "user_message",
  "session_id": "verify_compare_001",
  "message": "第一款和第二款哪个更适合油皮？"
}
```

Acceptance:

- [ ] Response includes `comparison_result`.
- [ ] Compared product IDs are from the previous recommendation.
- [ ] Backend does not invent product IDs.

Negative case:

```json
{
  "type": "user_message",
  "session_id": "verify_compare_negative_001",
  "message": "想找一款猫粮，家里猫肠胃比较敏感，预算300左右，优先看口碑好的"
}
```

Acceptance:

- [ ] Backend must not respond with `我还没有足够的最近推荐商品可以对比`.
- [ ] This fresh recommendation must not be misrouted into compare mode.

## 11. Cart Flow Verification

Step 1:

```json
{
  "type": "user_message",
  "session_id": "verify_cart_001",
  "message": "推荐适合油皮的洗面奶"
}
```

Step 2:

```json
{
  "type": "user_message",
  "session_id": "verify_cart_001",
  "message": "把刚才那款加到购物车"
}
```

Step 3:

```json
{
  "type": "user_message",
  "session_id": "verify_cart_001",
  "message": "数量改成2"
}
```

Step 4:

```json
{
  "type": "user_message",
  "session_id": "verify_cart_001",
  "message": "下单吧"
}
```

Acceptance:

- [ ] Step 2 emits `cart_update` with `action=add_to_cart`.
- [ ] Step 3 updates quantity to 2.
- [ ] Step 4 returns checkout status `ok`.
- [ ] Cart product ID is from previous backend recommendation.

## 12. Structured Memory Cache Verification

Start backend with optional persistent cache:

```bash
export SHOPGUIDE_MEMORY_CACHE_PATH="cache/verify_memory.jsonl"
USE_EMBEDDING=0 HOST=127.0.0.1 PORT=18080 ARK_API_KEY="$ARK_API_KEY" bash scripts/start_backend.sh
```

Send the same request twice with different session IDs:

```json
{
  "type": "user_message",
  "session_id": "verify_cache_001",
  "message": "推荐防晒霜"
}
```

```json
{
  "type": "user_message",
  "session_id": "verify_cache_002",
  "message": "推荐防晒霜"
}
```

Check:

```bash
curl -sS http://127.0.0.1:18080/health
```

Acceptance:

- [ ] First request increments cache `misses` and `writes`.
- [ ] Second equivalent request increments cache `hits`.
- [ ] Returned product IDs remain the same.
- [ ] A different hard constraint, such as `推荐防晒霜，预算1元以内`, must not reuse the old cached product cards.

## 13. Evidence Reranker Verification

Automated tests cover this directly:

```bash
env/venv_shopguide_backend/bin/python -m pytest tests/test_agent_core.py::test_noise_review_is_filtered_from_product_evidence tests/test_agent_core.py::test_sensitive_skin_conflict_review_is_kept_as_risk_evidence -q
```

Expected:

```text
2 passed
```

Acceptance:

- [ ] Towel-style product evidence does not include `好吃` / `入口` style food review.
- [ ] Sensitive-skin negative risk review remains available when the query mentions sensitive skin.

## 14. Scenario Bundle Verification

Send:

```json
{
  "type": "user_message",
  "session_id": "verify_bundle_001",
  "message": "下周去三亚度假，帮我搭配一套从防晒到穿搭的方案"
}
```

Acceptance:

- [ ] Response includes `bundle_start`.
- [ ] Response includes at least one `bundle_item`.
- [ ] Response includes `bundle_done`.
- [ ] Bundle item products are real catalog product IDs.
- [ ] Treat this as a fixed demo scenario with known slots, not as proof of a generic scene planner.

## 15. Known Non-Goals for This Backend Verification

Do not fail backend verification for these unless the current task explicitly expands scope:

- Native Android/iOS UI is not in this backend repo.
- Photo search / VLM is not implemented in this backend pass.
- Qwen3-TTS service exists separately; full speech playback is not the core backend acceptance path here.
- Production Redis/cache invalidation is not part of the first memory-cache version.
- Generic scene planning is not implemented in this pass; the current Sanya bundle is a fixed demo-slot flow.

## 16. Issue Reporting Format

When a verifier finds a problem, report with:

```text
Case ID:
Backend branch/commit:
Request payload:
Expected:
Actual:
Relevant event sequence:
Product IDs returned:
Screenshots/logs if available:
Severity: blocker / major / minor
```

Suggested severity:

- `blocker`: backend crashes, cannot start, WebSocket unusable, product cards violate hard constraints.
- `major`: wrong intent route, no cart state update, hallucinated product ID, cache crosses constraints.
- `minor`: wording awkward, quick actions not ideal, evidence order debatable.

## 17. Final Acceptance Checklist

- [ ] Backend starts successfully.
- [ ] `/health` returns healthy status and product count 100.
- [ ] Full test suite returns `41 passed`.
- [ ] Normal recommendation streams text and product cards.
- [ ] Hard constraints are enforced by product cards, not only by text.
- [ ] Dataset taxonomy constraints are enforced for explicit sub-category requests and unknown product requests.
- [ ] Active clarification triggers only for high-uncertainty requests and does not block specific requests.
- [ ] Multi-turn followup preserves previous constraints.
- [ ] Comparison uses recent recommendation memory.
- [ ] Natural-language cart operations work.
- [ ] Structured cache hits repeated equivalent requests.
- [ ] Evidence reranker filters obvious noisy comments.
- [ ] No API key is committed or printed in logs.
