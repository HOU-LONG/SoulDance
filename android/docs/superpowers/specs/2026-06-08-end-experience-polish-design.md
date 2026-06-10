# End-Side Experience Polish Design

Date: 2026-06-08
Scope: Chat, product detail BottomSheet, cart journey

## Goal

Polish the Android native Compose experience so the shopping guide feels like a commercial product: AI-assistant-like conversation, refined lightweight motion, skeleton loading, rich product-card interaction, and stable cart feedback.

This work is experience polish only. It must not move recommendation logic into the client, replace native Compose with WebView, or add TTS/LLM keys to the app.

The client only renders product order, primary/alternative role, and recommendation content provided by backend or approved local mock data. The client may animate and present these roles, but must not rank products or invent recommendation conclusions.

## Experience Direction

Conversation should feel like an AI shopping assistant: calm, guided, and context-aware. Motion should feel refined and light-luxury: short, soft, useful, and never distracting.

The main journey is:

1. User sends a need in chat.
2. Assistant shows a thinking/recommendation loading state.
3. Text explanation appears before product recommendations.
4. Primary product appears first, with alternatives revealed after it. These roles come from backend/mock response data, not client ranking.
5. User opens product detail in a BottomSheet without leaving chat.
6. User asks follow-up questions bound to the focused product.
7. User favorites or adds to cart with clear feedback.
8. User checks cart, adjusts quantity, removes items, and can undo removal.

## Chat Experience

`ChatScreen` should control conversation rhythm and scroll behavior.

- After sending, the input enters a lightweight pending state to prevent accidental duplicate sends.
- Assistant response starts with a low-pressure thinking/loading state, such as "understanding" then "organizing recommendation".
- Text appears before product cards to preserve the consultant-style explanation.
- Primary product card enters first with subtle fade and vertical motion, based on the response-provided product role/order.
- Alternative products appear slightly later and should not compete visually with the primary recommendation. The client must not recalculate which product is primary.
- Auto-scroll should happen at message block or product block boundaries, not on every token.
- Error states should appear inside the chat flow without blank screens or crashes.

## Product Card Experience

Product cards should communicate hierarchy, confidence, and action readiness.

- Primary cards show image, price, recommendation reason, tags, favorite, and add-to-cart.
- Alternative cards are more compact and secondary.
- Primary versus alternative card treatment must follow backend/mock product role fields or response order.
- Horizontal product scrolling should use Compose-native smooth behavior with restrained resistance.
- Card press uses a small scale or elevation response.
- Favorite feedback uses a small scale/morph animation.
- Add-to-cart temporarily changes button state, then triggers cart badge feedback.
- Product image loading uses skeleton or branded placeholder.
- Image failure uses a consistent fallback, never broken or empty UI.

## Product Detail BottomSheet

Product detail remains part of the chat flow.

- Tapping a product opens `ProductDetailBottomSheet`; it must not navigate to an external page as the primary experience.
- The sheet shows product image, title, price, tags, recommendation reason, and risk/fit details when available.
- The bottom area keeps a product follow-up input.
- Product follow-up must carry `focus_product_id`.
- The generated `product_followup` payload must be testable and include the active `focus_product_id`.
- Favorite and cart state must stay synchronized between cards and detail.
- Closing the sheet returns to the same chat context.

## Cart Experience

Cart should feel stable and reversible.

- Add-to-cart should not force navigation; it should update badge and show lightweight confirmation.
- Opening cart shows item list with subtle entry motion.
- Quantity changes animate the changed number and update summary smoothly.
- Removing an item exposes a short undo state.
- Empty cart should route the user back to chat instead of ending the journey.
- Cart count must remain correct across chat card, detail sheet, badge, and cart screen.

## Component Changes

Enhance existing Compose components instead of rewriting pages:

- `ChatScreen`: chat rhythm, block reveal, scroll policy.
- `TypingIndicator`: two-stage assistant loading state.
- `ProductSkeletonCard`: shared product loading skeleton.
- `ProductImage`: loading, placeholder, image failure fallback.
- `ProductCard`, `HeroProductCard`, `AlternativeProductCard`: press, favorite, add-to-cart, entry animation.
- `ProductDetailBottomSheet`: detail interaction and focused follow-up.
- `CartBadge`: count-change animation.
- `CartScreen`, `CartItemCard`, `CartSummaryBar`: item entry, quantity feedback, remove undo, summary update.

## State Model

Use explicit UI states so animation and error handling are predictable.

Chat state:

- `idle`
- `userSending`
- `assistantThinking`
- `recommendationLoading`
- `recommendationReady`
- `error`

Product card state:

- `imageLoading`
- `imageLoaded`
- `imageFailed`
- `isFavorited`
- `isAddingToCart`
- `addedToCart`

Cart state:

- `lastRemovedItem` for undo.
- count-change event for badge animation.
- summary price derived from cart items.

Detail state:

- current `focusedProductId`.
- current product favorite/cart state.

Recommendation role state:

- product role/order is read from backend/mock data.
- UI animation may delay reveal, but must preserve source order and role.
- no client-side recommendation ranking is introduced in this polish pass.

## Error And Weak-Network Behavior

- No network or WebSocket disconnect should not crash the app.
- Chat should show a low-interruption error message with a retry action when the request can be retried.
- Recommendation skeletons must not remain forever; after timeout or disconnect, show an inline error/retry state.
- Partial streamed responses should keep already received text visible and mark the interrupted state.
- WebSocket reconnect should be explicit and bounded, not an infinite hidden loop.
- Product loading should show skeletons instead of only spinners.
- Image failure should use the shared fallback.
- Add-to-cart failure should restore the button and show a short message.

## Implementation Constraints

- Keep Android native Kotlin + Jetpack Compose.
- Prefer Compose native animation APIs.
- Do not introduce a heavy animation library for this polish pass.
- Do not hard-code recommendation logic on the client.
- Do not store TTS or LLM API keys in the app.
- Do not force large scroll jumps on every streamed token.

## Acceptance Criteria

- Sending a chat message visibly enters an assistant thinking/loading state.
- Recommendation text appears before product cards.
- Primary product is visually prioritized over alternatives.
- Product cards show skeleton/placeholder while images load.
- Image failures show fallback UI.
- Product card tap opens and closes BottomSheet without losing chat context.
- Product follow-up carries `focus_product_id`.
- A unit test or payload-level check verifies `product_followup` includes the active `focus_product_id`.
- Favorite and add-to-cart interactions provide refined feedback.
- Cart badge count updates correctly after add-to-cart.
- Cart quantity changes update item quantity and summary price.
- Removing a cart item supports undo.
- Empty cart has a route back to chat.
- WebSocket disconnect, no network, and image failure do not crash the app.
- WebSocket timeout/disconnect exits loading skeleton state and exposes retry.
- SpeechRecognizer, AudioTrack, and WebSocket cleanup remain intact on page destruction.

## Verification

Run at minimum:

```bat
gradlew.bat :app:testDebugUnitTest
gradlew.bat :app:assembleDebug
```

Manual QA should cover:

- chat send to recommendation flow
- product card loading and failure fallback
- product detail BottomSheet
- focused product follow-up, including payload inspection for `focus_product_id`
- favorite and add-to-cart feedback
- cart quantity, remove, undo, and summary update
