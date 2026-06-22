# Realtime Protocol

The Android client uses OkHttp WebSocket to send typed requests and render streaming backend events.

## Endpoint

```text
/ws/chat
```

## Client Requests

### user_message

General user turn.

Required fields:

- `type`: `user_message`
- `session_id`
- `message`

Optional fields:

- `input_type`: `text` or `voice`; defaults to `text`
- `tts_enabled`
- `voice`

### product_followup

A follow-up bound to the currently focused product.

Required fields:

- `type`: `product_followup`
- `session_id`
- `message`
- `focus_product_id`

The client must not send a product follow-up without `focus_product_id`; otherwise the backend cannot keep product context isolated.

### cart_action

Deterministic cart mutation.

Required fields:

- `type`: `cart_action`
- `session_id`
- `action`
- `product_id` when the action targets a product
- `quantity` when relevant

Optional fields:

- `idempotency_key` for write actions that may be retried by the client

Natural-language cart operations are allowed only when the backend can resolve a concrete cart target from session context, current cart contents, or a unique product name. Checkout/order creation remains protected by the REST order confirmation state machine; Agent text must not claim an order was completed unless the confirmation API/tool succeeded.

## Envelope Metadata

Every server event produced in response to one client message carries an envelope with the following additive fields:

- `seq`: monotonically increasing integer starting at `0` for the `ack` event.
- `trace_id`: stable UUID-like identifier shared by the `ack` and all subsequent events from the same client message.
- `timestamp`: ISO 8601 UTC timestamp.
- `session_id`: the session id from the client request.
- `message_id`: grouping id for UI messages; preserved from the client when present.

The first event the backend sends after receiving a valid client message is:

```json
{
  "type": "ack",
  "session_id": "demo",
  "message_id": "msg_xxx",
  "trace_id": "trace_xxx",
  "seq": 0,
  "timestamp": "2026-06-20T14:00:00Z",
  "payload": {"state": "received"}
}
```

Existing outgoing event types keep their current top-level fields and additionally receive the envelope metadata. Old clients that ignore unknown fields continue to work unchanged. New clients may use `ack` for connection bookkeeping and `trace_id` for end-to-end tracing.

## Compatibility Rules

- Existing event types (`text_delta`, `product_item`, `products_start`, `products_done`, `cart_update`, `quick_actions`, `done`, `error`, audio/focus/bundle events) remain unchanged except for additive envelope fields.
- The `ack` event is additive and must not block old clients.
- Android tolerates unknown metadata fields and does not treat `ack` as assistant text.

## Server Events

The current client handles these event families:

```text
ack                     receipt confirmation with envelope metadata
text_delta              incremental assistant text
product_item            product card payload
recommendations_ready   recommendation set is complete
cart_update             cart mutation/result state
audio_delta             streaming TTS audio chunk
audio_done              TTS stream finished
done                    turn finished
error                   recoverable backend error
```

## Rendering Rules

- Text deltas render as assistant Markdown text.
- Product cards render only from structured product events.
- Product detail follow-up input binds to the card product ID.
- Cart count and cart contents update only from backend cart events or cart REST responses.
- Repeated idempotent write responses must be rendered as the same completed action, not as a second mutation.
- WebSocket disconnects must surface as recoverable UI errors and must not crash the app.

## Non-Goals For Stage 0/01

- No binary image or audio payloads over WebSocket.
- No database-backed order state machine.
- No Android-side fallback recommendation logic.
