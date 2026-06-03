# ShopGuide Semantic Layer

## Boundary

ShopGuide now separates natural-language understanding from deterministic execution.

The LLM semantic layer parses user language into a structured `SemanticFrame`. It may identify intent, cart operations, product references, and constraint edits. It does not choose final products, mutate carts directly, or bypass hard filters.

The primary path is LLM semantic parsing with session context. Rule logic is reserved for fallback and safety guardrails, not for advertising the main intent capability.

For short contextual messages, the LLM receives the current focus product, recent recommendation summaries, last intent, current task, and pending clarification state. For example, after a phone recommendation:

- `换个更便宜的` should parse as `product_followup` with `response_goal=recommend_cheaper_alternative`.
- `刚刚那个是什么？` should parse as `product_followup` with `response_goal=explain_focus_product`.
- `不要这个品牌` should parse as `product_followup` with `response_goal=exclude_current_brand`.

If no session focus exists, these short messages are not allowed to trigger random retrieval.

The backend executor validates the frame and applies it deterministically:

- `apply_constraint_edits()` turns followup diffs into a new `RetrievalPlan`.
- `resolve_cart_operation()` maps product references to real product IDs from session state.
- `CartService` remains the only cart state machine.
- retrieval, hard filtering, reranking, and event rendering stay deterministic.

## Semantic Frame Examples

Natural language cart:

```json
{
  "intent": "cart_operation",
  "cart_operation": {
    "action": "add_to_cart",
    "quantity": 2,
    "target": {
      "reference": "last_recommendations",
      "selection_strategy": "cheapest"
    }
  }
}
```

Followup constraint edit:

```json
{
  "intent": "product_followup",
  "constraint_edits": {
    "add": {"price_max": 100},
    "remove": {"exclude_terms": ["酒精"]},
    "relax": []
  }
}
```

## Guardrails

Rule guards still run after LLM parsing. Explicit hard constraints such as "不要酒精", "不要日系", and "100以内" are preserved even if the LLM omits them.

If the configured model rejects OpenAI-style JSON mode, the client retries the same prompt without `response_format` and still parses the LLM's JSON text. Minor no-op shape issues such as `constraint_edits.remove: []` are normalized before validation.

If the LLM output is still invalid or missing, the parser falls back to rule-derived semantic frames. This keeps the demo stable while allowing more natural multi-turn language to move out of scattered keyword handlers.
