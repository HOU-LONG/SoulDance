# Session Context Compression Spec

## Goal

Add a session-context compression system for the ShopGuide Agent so long-running conversations can keep using LLM APIs safely without exceeding model context limits, while preserving user instructions, recent turns, product grounding, and tenant isolation.

## Existing Baseline

- The backend already avoids sending full chat transcripts to most LLM calls.
- `SessionContext` stores structured state: last plan, focus product, last product ids, last recommendations, pending clarification/recovery, constraint state, trace, and up to 12 `context_events`.
- LLM calls currently exist in `server/backend/app/llm_client.py`: semantic parsing, contextual follow-up classification, product selection, recommendation response, and chitchat streaming.
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
   - Streaming calls may need a conservative preflight estimate and then post-call usage reconciliation when the provider exposes usage.

5. User messages have privilege.
   - User instructions, questions, and code snippets are the task source.
   - User pure text must not be truncated for compression.
   - If a call must fit a strict prompt budget, older user messages move into immutable transcript references or the living summary; their raw stored text remains intact.

6. Protect the near end.
   - Recent turns are not eligible for compression.
   - Default protected window: latest 8000 effective tokens or at least the latest 3 complete user-assistant turns, whichever is larger.
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

## Non-Goals For The First Implementation

- Do not change Android UI rendering.
- Do not expose raw compression internals to the client protocol by default.
- Do not require JSON response mode for assistant copy.
- Do not introduce a vector store or external memory service just for compression.
- Do not summarize product catalog facts; product evidence remains owned by retrieval and product chunks.

## Acceptance Criteria

- Long sessions keep producing valid `ack`, `text_delta`, `product_item`, and `done` event shapes.
- Recent turns remain verbatim in the composed LLM context.
- User raw text remains stored and auditable.
- Compression decisions are stable across repeated turns.
- Incremental summary updates only consume newly eligible events.
- No compression row can be read or updated by `session_id` alone once `user_id` support is enabled.
- Tests cover low, medium, high, and emergency watermarks.
