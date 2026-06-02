# Active Clarification Client Test Report

Date: 2026-06-02

Purpose: this report helps client teammates build a small UI to manually verify the ShopGuide active clarification feature. It focuses on what the client should send, render, and assert.

## 1. Feature Summary

Active clarification makes the backend ask one key question before recommending when the user's request is too vague for a reliable shopping decision.

Current implementation is intentionally restrained:

- Generic phone request asks about photo, battery life, or value-for-money.
- Generic laptop request asks about portability, performance, or value-for-money.
- Generic gift request asks about budget/object/preference direction.
- Generic skincare request asks about skin type or effect.
- Specific requests with enough constraints still recommend directly.
- No-match catalog requests still use `filter_recovery_options`, not clarification.

Client principle:

```text
Backend decides whether to clarify.
Client only renders clarification_request and sends the selected option back as the next user message.
```

## 2. Version Under Test

Remote project:

```text
/home/huadabioa/houlong/SoulDance
```

Expected branch:

```text
codex/rag-memory-reranker
```

Expected commits:

```text
8d2e20e docs: record active clarification verification
8a0e14c feat: add restrained active clarification policy
```

Expected automated backend result:

```text
41 passed, 1 warning
```

The warning is from `jieba/pkg_resources` and is non-blocking.

## 3. Minimal Client UI

Build one simple chat screen with:

- Health panel for `llm`, `retriever`, and `product_count`.
- Intent panel for the current turn's `intent`, `retrieval_mode`, and event count.
- Message input.
- Send button.
- AI text bubble area for `text_delta`.
- Product card list area for `product_item`.
- Clarification area for `clarification_request`.
- Optional raw event log panel for debugging.

Clarification card should display:

- `question` as the main text.
- Three option buttons from `options`.
- On click, send the option's `message` as a new `user_message` using the same `session_id`.

Important: `llm=fake` means the backend is using rule fallback. Use `llm=doubao` when verifying real LLM/Semantic Agent intent recognition.

Recommended event handling:

| Event | Client behavior |
|---|---|
| `assistant_state` | Show lightweight loading/status text |
| `text_delta` | Append text to current AI bubble |
| `clarification_request` | Show question and option buttons |
| `product_item` | Render product card |
| `products_start` / `products_done` | Start/stop product list loading |
| `quick_actions` | Render optional refinement buttons |
| `filter_recovery_options` | Render no-match recovery choices |
| `done` | Mark current turn complete |

The client should not render product skeletons forever if a clarification turn has no `products_start`.

The browser can render streaming normally. The backend sends each LLM chunk as a separate `text_delta`; the test client logs event sequence numbers and receive timestamps so teammates can see whether chunks arrive progressively.

## 4. WebSocket Contract

Connect:

```text
ws://127.0.0.1:18080/ws/chat
```

Send:

```json
{
  "type": "user_message",
  "session_id": "client_clarify_001",
  "message": "推荐一款手机",
  "input_type": "text",
  "tts_enabled": false
}
```

Expected clarification event:

```json
{
  "type": "clarification_request",
  "message_id": "assistant_xxx",
  "question": "选手机我需要先知道你更看重拍照、续航还是性价比？也可以直接告诉我预算。",
  "options": [
    {
      "label": "拍照优先",
      "message": "拍照优先，预算4000以内"
    },
    {
      "label": "续航优先",
      "message": "续航优先，预算4000以内"
    },
    {
      "label": "性价比",
      "message": "性价比优先，预算3000以内"
    }
  ]
}
```

Then send the clicked option back:

```json
{
  "type": "user_message",
  "session_id": "client_clarify_001",
  "message": "拍照优先，预算4000以内",
  "input_type": "text",
  "tts_enabled": false
}
```

Expected second turn:

- No `clarification_request`.
- One or more `product_item`.
- Product cards have `sub_category=智能手机`.
- Product prices are `<= 4000`.

## 5. Manual Test Scenarios

### 5.1 Ambiguous Phone

User message:

```text
推荐一款手机
```

Expected:

- Shows one clarification card.
- Does not show product cards in this turn.
- Options include photo, battery, and value-for-money directions.

### 5.2 Clarification Answer Continues Recommendation

Same session, user clicks:

```text
拍照优先，预算4000以内
```

Expected:

- Recommends phone products.
- Does not ask the same clarification again.
- Product card category remains phone.

### 5.3 Specific Phone Request Skips Clarification

User message:

```text
推荐一款手机，预算4000，拍照优先
```

Expected:

- Directly returns product cards.
- No clarification card.

### 5.4 Ambiguous Laptop

User message:

```text
推荐一台笔记本
```

Expected:

- Shows one clarification card.
- Options include portability, performance, and value-for-money directions.
- No product cards in the clarification turn.

### 5.5 Generic Gift

User message:

```text
送女朋友礼物
```

Expected:

- Shows one clarification card.
- Does not emit unrelated product cards just to fill a result.
- Option click can continue the conversation in the same session.

### 5.6 Generic Skincare

User message:

```text
推荐护肤品
```

Expected:

- Shows one clarification card.
- Options include oily skin, sensitive skin, or moisturizing/repair.
- No product cards in the clarification turn.

### 5.7 Specific Skincare Still Recommends

User message:

```text
推荐精华，预算100以内
```

Expected:

- No clarification card.
- Product cards have `sub_category=精华`.
- Product prices are `<= 100`.

### 5.8 Unknown Catalog Request Still Uses Recovery

User message:

```text
推荐毛巾
```

Expected:

- Does not show unrelated product cards.
- Uses no-match recovery or clarification-style text.
- This is not the same as active clarification for vague but known categories.

## 6. Acceptance Checklist

- [ ] Client can render `clarification_request.question`.
- [ ] Client can render all `clarification_request.options`.
- [ ] Clicking an option sends `option.message` to `/ws/chat` with the same `session_id`.
- [ ] Clarification turns do not leave product loading UI stuck.
- [ ] Follow-up after option click can render normal product cards.
- [ ] Specific requests are not slowed down by unnecessary clarification.
- [ ] Unknown category requests do not show unrelated product cards.
- [ ] Raw event log confirms one `done` event per turn.

## 7. Notes for Demo

Best demo flow:

```text
推荐一款手机
-> click 拍照优先
-> backend recommends phone products under budget
```

This is the cleanest way to show the competition requirement: the agent identifies missing information, asks one useful question, then continues recommendation after the user clarifies.
