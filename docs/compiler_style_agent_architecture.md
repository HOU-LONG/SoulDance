# ShopGuide Compiler-Style Agent Backend

## Goal

ShopGuide backend now follows a compiler-style agent architecture:

```text
Client Request
-> SessionState load
-> IntentCompiler: LLM semantic parse into ShoppingIntentIR
-> Schema validation + rule guard
-> StateReducer: deterministic dialogue state update
-> QueryBuilder: deterministic RetrievalPlan
-> RAG / Cart / Compare / Bundle executor
-> Evidence-grounded ResponseWriter
-> Streaming Event Renderer
```

The important boundary is simple:

- The same LLM client is used in three controlled roles: parse intent, choose product IDs from backend candidates, and write final natural-language explanation.
- Backend deterministically executes session state updates, retrieval, hard filtering, ranking, reference resolution, cart mutation, final product validation, and event rendering.
- LLM never mutates cart state, bypasses hard filters, invents usable product IDs, or controls product card event order.

## Core Modules

```text
backend/app/intent_compiler.py      Single semantic parse boundary.
backend/app/state_reducer.py        Applies constraint edits to SessionState.
backend/app/query_builder.py        Builds RetrievalPlan from IR + SessionState.
backend/app/reference_resolver.py   Binds "刚才/第二款/最便宜" to real product_id.
backend/app/agent.py                Orchestrates streaming execution.
backend/app/ranker.py               Hard filter + deterministic scoring.
backend/app/cart.py                 Cart state machine.
```

The legacy LLM planner has been removed. `planner_agent.py` remains only for compatibility rule helpers used by guards and debug planning; it does not call the LLM.

## ShoppingIntentIR

`SemanticFrame` now evolves into `ShoppingIntentIR`. It describes what the user means, not what products to return.

Key fields:

```json
{
  "intent": "recommend_product",
  "constraint_edits": {
    "add": {
      "category": "美妆护肤",
      "sub_category": "防晒",
      "price_max": 100,
      "exclude_terms": ["酒精"],
      "soft_preferences": {"texture": "清爽"}
    },
    "remove": {},
    "relax": []
  },
  "cart_operation": null,
  "references": [],
  "query_intent": {
    "category": "美妆护肤",
    "sub_category": "防晒",
    "soft_preferences": {"texture": "清爽"},
    "query_terms": ["防晒", "清爽", "户外"]
  },
  "response_goal": "recommend_primary_with_alternatives"
}
```

`query_intent` is not the final retrieval query. `QueryBuilder` combines it with current session constraints and taxonomy/rule guards to produce `RetrievalPlan`.

## SessionState

`SessionContext` keeps old fields for backward compatibility, but the authoritative state is now `context.state`:

```text
SessionState
- user_profile
- dialog_state
- active_focus
- recommendation_memory
- pending_clarification
- current_task
- cart_memory
- constraint_state
- trace
```

Important rules:

- `constraint_state.hard` is the current source of truth for hard constraints.
- `pending_clarification` records the category/sub-category and question for the next preference-only clarification answer.
- `current_task` marks the active shopping task; explicit new taxonomy requests reset conflicting task constraints.
- Task switching uses a task-object resolver before pending clarification inheritance. Specific objects such as `跑鞋` bind to real sub-categories; generic objects such as `鞋` bind only to a broad task category and trigger clarification instead of forcing a fake sub-category.
- `recommendation_memory.items` is the source for "第一款 / 第二款 / 最便宜".
- `active_focus.product_id` is the source for product BottomSheet followup.
- `cart_memory.recent_product_id` tracks recent cart target.
- `trace.last_ir` and `trace.last_execution_plan` are for debug and evaluation only.

## Execution Flows

### Recommend

```text
user_message
-> IntentCompiler
-> StateReducer applies constraint_edits
-> QueryBuilder builds RetrievalPlan
-> retriever topK
-> hard_filter
-> ranker / future custom reranker hook
-> LLM selection_decision
-> backend final validation
-> stream: assistant_state -> text_delta -> assistant_state(selection) -> explanation -> product_item -> quick_actions -> done
```

### Followup

```text
product_followup
-> bind focus_product_id into active_focus
-> IntentCompiler
-> StateReducer edits existing constraint_state
-> QueryBuilder rebuilds RetrievalPlan from updated state
-> retrieve/filter/rank
-> replacement_product or filter_recovery_options
```

Example: "酒精可以接受，但要100以内" removes `exclude_terms=["酒精"]` and adds `price_max=100`, while inheriting the previous category.

### Natural Language Cart

```text
user_message
-> IntentCompiler produces cart_operation
-> ReferenceResolver binds target to real product_id
-> CartService executes action
-> cart_update -> done
```

If the LLM returns a hallucinated `product_id`, `ReferenceResolver` ignores it unless it exists in the catalog and current session scope.

### Explicit Cart Action

```text
cart_action
-> bypass LLM
-> agent deterministic cart executor
-> CartService
-> cart_update -> done
```

The explicit path also updates `SessionState.cart_memory`, so later "数量改成2" can refer to the same item.

### Compare

Compare still uses deterministic product IDs from recent recommendation memory. The output is a structured `comparison_result`; LLM is not needed for product choice.

### Bundle

Bundle still decomposes the scenario into deterministic slots, retrieves each slot independently, and streams `bundle_*` events.

## Response Writer Boundary

LLM response writing receives a constrained payload shaped like:

```json
{
  "allowed_products": [
    {
      "product_id": "p_beauty_001",
      "reason": "short backend reason",
      "review_summary": {
        "positive_summary": "相关评论摘要",
        "negative_summary": "风险摘要",
        "review_relevance": "high"
      }
    }
  ],
  "selected_primary": "p_beauty_001",
  "hard_constraints_applied": {},
  "forbidden_claims": ["疗效承诺", "未给出的商品属性"]
}
```

Its output only becomes `text_delta`. It should lead with the conclusion, summarize relevant reviews, and briefly distinguish alternatives when multiple `allowed_products` are present. Raw evidence remains internal and is not returned in `product_item`; `review_summary` is produced from the filtered evidence/ranker layer, not by an extra planner or product-card LLM call. It cannot modify:

- `product_item`
- prices
- cart totals
- product order
- hard filter results
- event types

## Future Hooks

Custom reranker should be inserted after hard filter and before final topK selection:

```text
retrieve topK
-> hard_filter
-> feature_builder
-> custom_reranker
-> deterministic final selection
```

TTS should stay after event rendering:

```text
assistant text segments
-> TTSAdapter
-> audio_chunk / audio_url events
```

TTS must not participate in intent parsing, retrieval, cart mutation, or ranking.

## Verification

Run:

```bash
env/venv_shopguide_backend/bin/python -m pytest -q
```

Key regression tests cover:

- no legacy LLM planner or `llm.plan()` path remains;
- followup edits update `SessionState.constraint_state`;
- hallucinated cart `product_id` is ignored;
- explicit and natural-language cart actions share deterministic cart execution;
- streaming keeps LLM explanation before product cards.
