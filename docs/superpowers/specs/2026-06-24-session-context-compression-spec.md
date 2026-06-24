# Session Context Compression Spec

## Goal

Add a session-context compression system for the ShopGuide Agent so long-running conversations can keep using LLM APIs safely without exceeding model context limits, while preserving user instructions, recent turns, product grounding, and tenant isolation.

Quantified target:

- Below 70 percent of the configured model context limit, compression must add zero extra LLM calls.
- Below 95 percent of the configured model context limit, one turn must be able to fit after deterministic compaction or at most one incremental-summary call.
- Compression preflight and deterministic assembly should add no more than 30 ms p95 local overhead on a synthetic 100-turn session, excluding network LLM latency.
- Level 4 emergency prompts must be assembled under 95 percent of `model_context_limit` unless the current user message alone exceeds that budget.

## Existing Baseline

- The backend does not send a raw full chat transcript to current LLM calls. It sends bounded, task-specific JSON payloads.
- Semantic parsing uses `message`, `request_type`, `semantic_context_payload(context)`, and `contextual_intent_task`. That payload includes `last_plan`, focus product fields, `last_product_ids`, `last_recommendations`, `recent_cart_product_id`, `global_profile`, current task, pending clarification/recovery, and a compact `recent_context`.
- Contextual follow-up classification uses the same compact context payload plus the current message.
- Product selection uses `message`, the current `RetrievalPlan`, and candidate product summaries from `_selection_candidates_payload()`.
- Recommendation response generation uses `message` and `_response_evidence_payload()`, which includes top returned products, `selected_primary`, response contract, applied hard constraints, optional focus product, and forbidden-claim boundaries.
- Chitchat streaming currently uses only `message` and `intent`.
- `SessionContext.state.context_events` is already bounded to the latest 12 events in `agent.py`; `semantic_context_payload()` further exposes only the last few recent user turns, recommendation sets, and events. This hard cap is the current baseline to preserve until compression state makes older context auditable.
- Task 3 of the implementation must record p50/p95 prompt token usage per LLM call kind before enabling higher compression levels, so acceptance comparisons are based on provider usage rather than character estimates.
- `SessionState` in the database is currently keyed only by `session_id`; compression state must not be introduced without a `(user_id, session_id)` isolation contract.

## Required Principles

1. Layered and progressive, not one-size-fits-all.
   - Define multiple watermarks.
   - The closer the request is to the model context limit, the more aggressive the compression action may be.
   - The system should maintain context continuously in small increments rather than waiting for a cliff-edge failure.

2. Strictly increasing cost.
   - Cheap actions run first: deterministic trimming, placeholder replacement, and structured state compaction.
   - Expensive actions run last: LLM-based incremental summary.
   - Zero-cost token release must be exhausted before paying for summarization.

3. Incremental summary over full summary.
   - Maintain a living summary per `(user_id, session_id)`.
   - Merge only newly compressible events into the living summary.
   - Do not repeatedly summarize the same old history.
   - The merge prompt may update stale facts when newer events supersede older facts.

4. Use real token usage for trigger decisions.
   - Trigger decisions must use provider-reported usage when available.
   - Approximate token counts are allowed only for internal ordering, for example deciding which old tool output to compact first.
   - Streaming calls must use conservative preflight accounting before the call and post-call reconciliation when the provider exposes final usage.

5. User messages have privilege.
   - User instructions, questions, and code snippets are the task source.
   - User pure text must not be truncated for compression.
   - Current and protected-window user messages remain verbatim in the prompt.
   - Older user messages may move into immutable transcript references or the living summary when needed for budget, but their raw stored text remains intact and auditable. They are never partially truncated inside the online prompt.

6. Protect the near end.
   - Recent turns are not eligible for compression.
   - Default protected window: latest 8000 effective tokens or at least the latest 3 complete user-assistant turns, whichever is larger.
   - A recent part remains protected even if that part alone is larger than 8000 approximate tokens; the token threshold defines the protected window, not a filter that drops large recent messages.
   - Product focus, pending clarification, current cart intent, and the current user message are never compressed before the current LLM call.

7. Monotonic boundaries; no sliding-window re-stubbing.
   - Once a part is replaced by a placeholder/stub, that decision becomes stable.
   - The same part id must produce the same placeholder bytes in later turns.
   - Store decisions by `part_id` in session compression state or use provider cache/context-management APIs when available.

8. Tenant isolation is non-negotiable.
   - Compression state is keyed by `(user_id, session_id)`.
   - Database writes use `WHERE user_id = ? AND session_id = ?` for updates.
   - File paths use `user_sessions/{user_id}/sessions/{session_id}/_internal/compression.json` or equivalent safe partitioning.
   - Any SSE/WebSocket compression notification is filtered by `session_id` and, when available, `user_id`.
   - This phase tenants `SessionState` and compression state first. `Cart`, `Order`, and `FeedbackEvent` remain session-keyed in this phase and require a follow-up tenant-migration spec. The new schema must not block that later migration.

9. Per-session concurrency must be deterministic.
   - At most one turn may mutate a session's compression state at a time.
   - Implement this with a session-level async lock or a database row lock where supported.
   - Concurrent turns must not overwrite living summaries, part decisions, or token ledgers from another turn.

## Failure Semantics

- Deterministic compaction failures fall back to the previous saved compression state and the current bounded `SessionContext` payload. They must not corrupt stored decisions.
- Incremental LLM summary failures do not block the main assistant reply. The system reuses the last successful living summary, records the failure metric, and falls back to Level 4 emergency context assembly when needed.
- If Level 4 still cannot fit because the current user message alone exceeds the configured prompt budget, the agent returns a short clarification/error asking the user to split the input. It must not silently truncate the current user message.
- Product facts are never recovered from a stale summary when retrieval/product evidence is available; summaries can carry user goals and prior decisions, not authoritative product catalog facts.

## Non-Goals For The First Implementation

- Do not change Android UI rendering.
- Do not expose raw compression internals to the client protocol by default.
- Do not require JSON response mode for assistant copy.
- Do not introduce a vector store or external memory service just for compression.
- Do not summarize product catalog facts; product evidence remains owned by retrieval and product chunks.
- Do not tenant-migrate `Cart`, `Order`, or `FeedbackEvent` in this phase; document the compatibility boundary so a later migration can add `user_id` safely.

## Acceptance Criteria

- Long sessions keep producing valid `ack`, `text_delta`, `product_item`, and `done` event shapes.
- Recent turns remain verbatim in the composed LLM context.
- User raw text remains stored and auditable.
- Older user messages are either referenced verbatim by immutable id or summarized as whole messages; they are never partially truncated in prompt text.
- Compression decisions are stable across repeated turns.
- Incremental summary updates only consume newly eligible events.
- No compression row can be read or updated by `session_id` alone once `user_id` support is enabled.
- Level 1 compression performs no LLM summary call.
- Level 3 and Level 4 are the only levels allowed to call the LLM summarizer.
- Level 4 prompt assembly keeps prompt tokens under 95 percent of `model_context_limit`, except when the current user message alone exceeds that budget and the agent returns a split-input request.
- Streaming response/chitchat calls reconcile final provider usage when available; missing usage is marked as preflight-only and cannot be treated as authoritative.
- Tests cover maintain, cheap deterministic, structured compaction, incremental summary, and emergency watermarks.
