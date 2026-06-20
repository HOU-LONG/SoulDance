# API Contract

This document records the current Stage 0/01 backend surface. It does not introduce breaking protocol changes.

## Base URLs

Remote device debugging uses the Cloudflare tunnel configured in Android `AppConfig.kt`.

```text
HTTP:  https://<cloudflare-domain>/
WS:    wss://<cloudflare-domain>/ws/chat
Local: http://127.0.0.1:8000/
```

## Health

```http
GET /health
```

Response includes backend status, product count, LLM label, retriever label, memory-cache stats, and persisted-session count.

## Products

```http
GET /api/products?limit=20
GET /api/products/{product_id}
```

Product objects are backend-owned commerce facts. Android may display them but must not fabricate or mutate recommendation facts locally.

## Cart

```http
GET  /api/cart
POST /api/cart/add
POST /api/cart/clear
POST /api/cart/checkout
```

Cart write operations are deterministic backend operations. Agent text must not claim a cart mutation succeeded unless the corresponding tool/API path succeeded.

## STT

```http
POST /api/stt
```

Current request shape is multipart audio upload. STT provider credentials and external provider URLs stay on the server.

## WebSocket Chat

```text
WS /ws/chat
```

Request types:

```text
user_message
product_followup
cart_action
```

`product_followup` is product-scoped and must include `focus_product_id`.

Minimal request examples:

```json
{"type":"user_message","session_id":"demo","message":"recommend a gentle cleanser","input_type":"text","tts_enabled":false}
```

```json
{"type":"product_followup","session_id":"demo","message":"is it good for sensitive skin?","focus_product_id":"product_001","input_type":"text"}
```

```json
{"type":"cart_action","session_id":"demo","action":"add_to_cart","product_id":"product_001","quantity":1}
```

## Compatibility Rules

- Keep `/health` and `/ws/chat` stable.
- Keep `user_message`, `product_followup`, and `cart_action` request types stable.
- Never put LLM, ASR, or TTS provider keys in the Android client.
- New write operations must be idempotent or explicitly protected before real ordering is enabled.
