# ShopGuide Interaction Protocol

This document records the backend events that make the shopping conversation feel responsive and low-pressure.

## Event Order

For a normal recommendation, the WebSocket response should follow this order:

```text
assistant_state
text_delta              # deterministic understanding sentence
assistant_state         # optional selection status
products_start
product_item...
products_done
text_delta              # grounded explanation
quick_actions
done
```

This puts a useful sentence on screen before cards arrive, runs LLM product selection over backend candidates, then gives the user one-tap ways to refine the result.

## Optional Events

- `assistant_state`: lightweight phase marker for UI status text or telemetry.
- `assistant_state.intent`, `assistant_state.retrieval_mode`, and `assistant_state.llm_mode` are optional debug fields for verification UIs.
- `assistant_state.selection_mode`, `assistant_state.candidate_count`, and `assistant_state.selected_count` are optional fields showing LLM product-card selection status.
- `small_talk` responses do not use a dedicated event; clients receive `assistant_state`, `text_delta`, and `done`.
- `quick_actions`: low-cost refinement actions such as `更便宜`, `不要这个品牌`, `更适合户外`.
- `clarification_request`: used only when recommending immediately would be unreliable.
- `comparison_result`: compares products from `SessionContext.last_product_ids`.
- `filter_recovery_options`: gives safe relaxation choices when no product satisfies hard constraints.
- `bundle_start`, `bundle_item`, `bundle_done`: streams scenario bundle recommendations by group.

Existing clients can ignore unknown events and continue to consume `text_delta`, `product_item`, `replacement_product`, `cart_update`, and `done`.

## Product Card Admission

Product cards are not emitted directly after retrieval. The backend only sends `product_item` after:

```text
LLM semantic intent
backend shopping admission
taxonomy and hard filters
ranker/reranker candidate pool
LLM selection_decision
backend final validation
```

The LLM can only select product IDs from the candidate pool. The backend discards IDs outside the pool and re-checks hard constraints before streaming cards. The final count is dynamic, with a demo cap of 4 cards.

## Natural Language Cart

The backend resolves natural commands against recent session state:

- `把刚才那款加到购物车` -> add current focus product.
- `就这个来两件` -> add the current primary product with quantity 2.
- `要这个` / `就它了` -> add the current primary product with quantity 1.
- `数量改成2` -> update the most recent cart product.
- `删掉第二个` -> remove the second recent recommendation when available.
- `下单吧` -> simulate checkout.
