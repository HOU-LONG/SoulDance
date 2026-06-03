# ShopGuide Interaction Protocol

This document records the backend events that make the shopping conversation feel responsive and low-pressure.

## Event Order

For a normal recommendation, the WebSocket response should follow this order:

```text
assistant_state
text_delta              # deterministic understanding sentence
assistant_state         # optional selection status
text_delta              # grounded explanation
products_start
product_item...
products_done
quick_actions
done
```

This puts useful text on screen before cards arrive, runs LLM product selection over backend candidates, streams the grounded explanation, and then emits final product cards. The grounded explanation is LLM-written from final evidence: it presents one primary recommendation and briefly distinguishes alternatives when present.

## Optional Events

- `assistant_state`: lightweight phase marker for UI status text or telemetry.
- `assistant_state.intent`, `assistant_state.retrieval_mode`, and `assistant_state.llm_mode` are optional debug fields for verification UIs.
- `assistant_state.selection_mode`, `assistant_state.candidate_count`, and `assistant_state.selected_count` are optional fields showing LLM product-card selection status.
- `assistant_state.context_action` is an optional field showing whether the turn is a `new_task`, `clarification_answer`, `followup`, or normal same-task turn.
- `assistant_state.memory_mode` is an optional field showing recommendation memory state: `miss`, `exact_hit`, `semantic_hit`, or rank-cache related diagnostics.
- `small_talk` responses do not use a dedicated event; clients receive `assistant_state`, `text_delta`, and `done`.
- `quick_actions`: low-cost refinement actions such as `更便宜`, `不要 Apple`, `更适合户外`. Brand actions name the current primary product brand instead of using the ambiguous `这个品牌`.
- `clarification_request`: used only when recommending immediately would be unreliable.
- `comparison_result`: compares products from `SessionContext.last_product_ids`.
- `filter_recovery_options`: gives safe relaxation choices when no product satisfies hard constraints.
- `bundle_start`, `bundle_item`, `bundle_done`: streams scenario bundle recommendations by group.

Existing clients can ignore unknown events and continue to consume `text_delta`, `product_item`, `replacement_product`, `cart_update`, and `done`. Plain chat follow-up replacements emit standard `product_item` cards; `replacement_product` is kept for product-detail compatibility.

## Product Card Admission

Product cards are not emitted directly after retrieval. The backend only sends `product_item` after:

```text
LLM semantic intent
backend shopping admission
taxonomy and hard filters
ranker/reranker candidate pool
LLM selection_decision
backend final validation
grounded explanation text
```

The LLM can only select product IDs from the candidate pool. The backend discards IDs outside the pool and re-checks hard constraints before streaming cards. The final count is dynamic, with a demo cap of 4 cards; the response evidence payload also includes up to 4 final allowed products.

## Natural Language Cart

The backend resolves natural commands against recent session state:

- `把刚才那款加到购物车` -> add current focus product.
- `就这个来两件` -> add the current primary product with quantity 2.
- `要这个` / `就它了` -> add the current primary product with quantity 1.
- `数量改成2` -> update the most recent cart product.
- `删掉第二个` -> remove the second recent recommendation when available.
- `下单吧` -> simulate checkout.
