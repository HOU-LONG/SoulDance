# Session Context Compression Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add progressive, tenant-isolated context compression for long-running ShopGuide Agent sessions without changing Android/WebSocket event payload shapes.

**Architecture:** Introduce a backend-only compression layer around `SessionContext` and LLM prompt construction. The first phase records real usage and maintains a deterministic compression ledger; later phases add living incremental summaries only after cheaper compaction actions are exhausted.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Pydantic, OpenAI-compatible chat completions, existing pytest backend suite.

---

## File Structure

- Create: `server/backend/app/context_compression.py`
  - Owns watermark policy, protected-window decisions, stable part ids, deterministic compaction, incremental-summary merge payloads, and prompt-context assembly helpers.
- Create: `server/backend/app/llm_usage.py`
  - Normalizes provider usage into `prompt_tokens`, `completion_tokens`, `total_tokens`, `source`, and `call_kind`.
- Modify: `server/backend/app/models.py`
  - Add Pydantic models for `SessionCompressionState`, `CompressionPartDecision`, `LivingSummary`, and optional `user_id` on `ChatRequest` with a safe default for current clients.
- Modify: `server/backend/app/db/models.py`
  - Add `user_id` to `SessionState` and a new `SessionCompressionState` table, both indexed by `(user_id, session_id)`.
- Modify: `server/backend/app/repositories/session_repository.py`
  - Enforce dual-key reads/writes where user id is available; keep a migration-compatible legacy path only for tests/current clients.
- Modify: `server/backend/app/session_store.py`
  - Accept `user_id` in get/save helpers and route compression state through the repository/file path layer.
- Modify: `server/backend/app/llm_client.py`
  - Record real usage from non-streaming completions and expose post-call usage metadata. Add an optional summarization method for incremental summary merges.
- Modify: `server/backend/app/agent.py`
  - Call compression preflight before semantic parsing, selection, response generation, and chitchat. Save compression state after each turn.
- Modify: `server/backend/app/main.py`
  - Pass `user_id` through request/session access while keeping existing Android clients compatible.
- Test: `server/tests/test_context_compression.py`
  - Unit tests for watermarks, protected windows, stable stubs, user-message privilege, and incremental summary merge windows.
- Test: `server/tests/test_llm_usage.py`
  - Unit tests for usage extraction across OpenAI-compatible response shapes and missing usage fallback.
- Test: `server/tests/test_session_tenant_isolation.py`
  - Repository and store tests proving `(user_id, session_id)` isolation.
- Update: `server/tests/test_agent_core.py`, `server/tests/test_db_stores.py`, `server/tests/test_websocket_protocol_envelope.py`
  - Focused integration tests that compression does not alter event protocol or product grounding.

## Watermark Contract

- Level 0, maintain: below 50 percent of model budget.
  - Record usage and stable part ids only.
- Level 1, cheap deterministic: 50 to 70 percent.
  - Drop duplicate trace entries, compact old non-user tool payloads, replace old product cards with product id/title placeholders.
- Level 2, structured compaction: 70 to 85 percent.
  - Keep recent protected window untouched; compact eligible `context_events` payloads into typed facts and product id references.
- Level 3, incremental summary: 85 to 95 percent.
  - Merge newly eligible old events into living summary using LLM summarizer.
- Level 4, emergency fit: above 95 percent or preflight over model limit.
  - Use living summary + protected recent turns + current user message + mandatory product evidence only. Never truncate current user text.

## Task 1: Add Compression Data Models

**Files:**
- Modify: `server/backend/app/models.py`
- Create: `server/tests/test_context_compression.py`

- [ ] **Step 1: Write failing model tests**

```python
def test_compression_state_defaults_are_session_scoped():
    state = SessionCompressionState(user_id="u1", session_id="s1")
    assert state.user_id == "u1"
    assert state.session_id == "s1"
    assert state.living_summary.text == ""
    assert state.decisions == {}
```

- [ ] **Step 2: Run the targeted test**

Run: `cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_context_compression.py`

Expected: FAIL because `SessionCompressionState` does not exist.

- [ ] **Step 3: Implement Pydantic models**

Add:

```python
class CompressionPartDecision(BaseModel):
    part_id: str
    action: str
    replacement_text: str
    original_token_count: int | None = None
    compressed_token_count: int | None = None
    created_turn: int = 0

class LivingSummary(BaseModel):
    text: str = ""
    covered_part_ids: list[str] = Field(default_factory=list)
    updated_turn: int = 0
    source_token_count: int = 0

class SessionCompressionState(BaseModel):
    user_id: str = "anonymous"
    session_id: str
    model_context_limit: int = 128000
    last_total_tokens: int | None = None
    watermark_level: str = "maintain"
    decisions: dict[str, CompressionPartDecision] = Field(default_factory=dict)
    living_summary: LivingSummary = Field(default_factory=LivingSummary)
```

- [ ] **Step 4: Verify targeted test passes**

Run the same pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/backend/app/models.py server/tests/test_context_compression.py
git commit -m "feat: add session compression models"
```

## Task 2: Add Watermark Policy And Stable Part Decisions

**Files:**
- Create: `server/backend/app/context_compression.py`
- Modify: `server/tests/test_context_compression.py`

- [ ] **Step 1: Write failing policy tests**

Cover:
- `choose_watermark_level(total_tokens=60000, limit=128000) == "cheap_deterministic"`
- recent 8000-token protected parts are not eligible
- user text parts are never truncated
- an existing stub decision is reused byte-for-byte

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest -q tests/test_context_compression.py`

- [ ] **Step 3: Implement policy helpers**

Create deterministic helpers:

```python
def choose_watermark_level(total_tokens: int, model_context_limit: int) -> str:
    ratio = total_tokens / max(model_context_limit, 1)
    if ratio >= 0.95:
        return "emergency_fit"
    if ratio >= 0.85:
        return "incremental_summary"
    if ratio >= 0.70:
        return "structured_compaction"
    if ratio >= 0.50:
        return "cheap_deterministic"
    return "maintain"


def stable_part_id(session_id: str, turn_index: int, role: str, ordinal: int) -> str:
    return f"{session_id}:{turn_index}:{role}:{ordinal}"


def is_protected_part(part, protected_recent_tokens: int = 8000) -> bool:
    return bool(part.is_current_user_message or part.is_recent and part.token_count <= protected_recent_tokens)


def apply_or_reuse_decision(state, part, replacement_factory):
    existing = state.decisions.get(part.part_id)
    if existing is not None:
        return existing.replacement_text
    replacement_text = replacement_factory(part)
    state.decisions[part.part_id] = CompressionPartDecision(
        part_id=part.part_id,
        action="placeholder",
        replacement_text=replacement_text,
        original_token_count=part.token_count,
        compressed_token_count=max(1, len(replacement_text) // 3),
        created_turn=part.turn_index,
    )
    return replacement_text
```

Use approximate token counts only for ordering and protected-window accounting.

- [ ] **Step 4: Verify tests pass**

Run: `pytest -q tests/test_context_compression.py`.

- [ ] **Step 5: Commit**

```bash
git add server/backend/app/context_compression.py server/tests/test_context_compression.py
git commit -m "feat: add progressive context compression policy"
```

## Task 3: Capture Real LLM Usage

**Files:**
- Create: `server/backend/app/llm_usage.py`
- Modify: `server/backend/app/llm_client.py`
- Create: `server/tests/test_llm_usage.py`

- [ ] **Step 1: Write usage extraction tests**

Cover OpenAI-style `response.usage.total_tokens`, camelCase `totalTokens`, missing usage, and streaming missing-usage behavior.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest -q tests/test_llm_usage.py`.

- [ ] **Step 3: Implement usage normalization**

```python
class LLMUsage(BaseModel):
    call_kind: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    source: str = "provider"
```

Add `extract_usage(response, call_kind)` and a `last_usage_by_call_kind` field on `DoubaoLLMClient`.

- [ ] **Step 4: Wire non-streaming calls**

Record usage in `_json_completion()`, `generate_response()`, and `select_products()`.

- [ ] **Step 5: Verify no behavior change**

Run:

```bash
pytest -q tests/test_llm_usage.py tests/test_agent_core.py::test_response_prompt_requires_short_paragraphs_or_bullets
```

- [ ] **Step 6: Commit**

```bash
git add server/backend/app/llm_usage.py server/backend/app/llm_client.py server/tests/test_llm_usage.py
git commit -m "feat: record provider token usage"
```

## Task 4: Add Tenant-Isolated Compression Persistence

**Files:**
- Modify: `server/backend/app/db/models.py`
- Modify: `server/backend/app/repositories/session_repository.py`
- Modify: `server/backend/app/session_store.py`
- Create: `server/tests/test_session_tenant_isolation.py`
- Modify: `server/tests/test_db_stores.py`

- [ ] **Step 1: Write failing isolation tests**

Create two users with the same `session_id`; verify state and compression state do not leak between users.

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest -q tests/test_session_tenant_isolation.py tests/test_db_stores.py`.

- [ ] **Step 3: Add DB fields and table**

- Add `user_id` to `SessionState`, defaulting to `anonymous` for migration compatibility.
- Add table `session_compression_states` with unique constraint `(user_id, session_id)`.
- Add indexes for `(user_id, session_id)` and `updated_at`.

- [ ] **Step 4: Enforce dual-key repository methods**

Add:

```python
def get(self, session_id: str, user_id: str = "anonymous") -> SessionContext | None:
    row = self.db.query(SessionState).filter_by(user_id=user_id, session_id=session_id).first()
    return SessionContext.model_validate(row.state_json) if row else None


def save(self, context: SessionContext, user_id: str = "anonymous") -> None:
    row = self.db.query(SessionState).filter_by(user_id=user_id, session_id=context.session_id).first()
    if row is None:
        row = SessionState(user_id=user_id, session_id=context.session_id)
        self.db.add(row)
    row.state_json = context.model_dump(mode="json")
    self.db.flush()


def get_compression_state(self, user_id: str, session_id: str) -> SessionCompressionState | None:
    row = self.db.query(SessionCompressionStateRow).filter_by(user_id=user_id, session_id=session_id).first()
    return SessionCompressionState.model_validate(row.state_json) if row else None


def save_compression_state(self, state: SessionCompressionState) -> None:
    row = self.db.query(SessionCompressionStateRow).filter_by(
        user_id=state.user_id,
        session_id=state.session_id,
    ).first()
    if row is None:
        row = SessionCompressionStateRow(user_id=state.user_id, session_id=state.session_id)
        self.db.add(row)
    row.state_json = state.model_dump(mode="json")
    self.db.flush()
```

Never update compression state by `session_id` alone.

- [ ] **Step 5: Update file persistence paths**

Use: `user_sessions/{safe_user_id}/sessions/{safe_session_id}/_internal/session.json` and `compression.json` for file-backed mode.

- [ ] **Step 6: Verify targeted tests pass**

Run: `pytest -q tests/test_session_tenant_isolation.py tests/test_db_stores.py tests/test_session_ttl.py`.

- [ ] **Step 7: Commit**

```bash
git add server/backend/app/db/models.py server/backend/app/repositories/session_repository.py server/backend/app/session_store.py server/tests/test_session_tenant_isolation.py server/tests/test_db_stores.py server/tests/test_session_ttl.py
git commit -m "feat: isolate session compression by user and session"
```

## Task 5: Compose Compressed LLM Contexts

**Files:**
- Modify: `server/backend/app/context_compression.py`
- Modify: `server/backend/app/semantic_layer.py`
- Modify: `server/backend/app/llm_client.py`
- Modify: `server/tests/test_context_compression.py`
- Modify: `server/tests/test_agent_core.py`

- [ ] **Step 1: Write failing assembly tests**

Assert:
- current user message is present verbatim
- latest protected events are present verbatim
- old product cards become stable product placeholders
- living summary is included before protected recent context

- [ ] **Step 2: Run tests and confirm failure**

Run: `pytest -q tests/test_context_compression.py tests/test_agent_core.py`.

- [ ] **Step 3: Implement context assembly**

Add `build_llm_context_payload(context, compression_state, request, call_kind)`.

Output shape:

```python
{
    "living_summary": state.living_summary.text,
    "stable_placeholders": [decision.model_dump(mode="json") for decision in reused_decisions],
    "protected_recent_context": recent_context_payload,
    "current_user_message": request.message,
    "current_focus": focus_payload,
}
```

- [ ] **Step 4: Wire semantic/followup context payloads**

Keep existing `semantic_context_payload()` fields but add `compression` under a new key. Do not remove current keys yet.

- [ ] **Step 5: Verify tests pass**

Run: `pytest -q tests/test_context_compression.py tests/test_agent_core.py`.

- [ ] **Step 6: Commit**

```bash
git add server/backend/app/context_compression.py server/backend/app/semantic_layer.py server/backend/app/llm_client.py server/tests/test_context_compression.py server/tests/test_agent_core.py
git commit -m "feat: compose compressed llm session context"
```

## Task 6: Add Incremental Summary Merge

**Files:**
- Modify: `server/backend/app/context_compression.py`
- Modify: `server/backend/app/llm_client.py`
- Modify: `server/backend/app/prompts/v1/context_summary.txt`
- Modify: `server/backend/app/prompt_registry.py` if prompt registration requires it
- Modify: `server/tests/test_context_compression.py`

- [ ] **Step 1: Write failing incremental summary tests**

Assert that:
- only not-yet-covered eligible part ids are summarized
- covered part ids are persisted
- newer facts supersede stale old facts
- protected recent parts are excluded

- [ ] **Step 2: Add context summary prompt**

Prompt contract:
- input is living summary + new events only
- output is plain Markdown or text summary, not JSON
- preserve user goals, constraints, product ids, rejected options, pending tasks
- do not invent product facts

- [ ] **Step 3: Implement summarizer method**

Add `merge_context_summary(existing_summary, new_parts)` to `DoubaoLLMClient`; `FakeLLMClient` returns deterministic merged text for tests.

- [ ] **Step 4: Implement merge orchestration**

`maybe_update_living_summary(context, compression_state, usage, llm_client)` triggers only at Level 3+.

- [ ] **Step 5: Verify targeted tests pass**

Run: `pytest -q tests/test_context_compression.py tests/test_llm_usage.py`.

- [ ] **Step 6: Commit**

```bash
git add server/backend/app/context_compression.py server/backend/app/llm_client.py server/backend/app/prompts/v1/context_summary.txt server/tests/test_context_compression.py
git commit -m "feat: add incremental session context summary"
```

## Task 7: Integrate With Agent Turn Lifecycle

**Files:**
- Modify: `server/backend/app/agent.py`
- Modify: `server/backend/app/main.py`
- Modify: `server/backend/app/models.py`
- Modify: `server/tests/test_websocket_protocol_envelope.py`
- Modify: `server/tests/test_agent_core.py`

- [ ] **Step 1: Write integration tests**

Cover:
- a long synthetic session triggers deterministic compaction
- protocol event types and payload shapes are unchanged
- product followup still carries focus product context
- cart action does not invoke LLM summary

- [ ] **Step 2: Add `user_id` compatibility field**

Add optional `user_id: str = "anonymous"` to `ChatRequest`, `CartActionRequest`, feedback request models where needed. Existing Android clients keep working because field is optional.

- [ ] **Step 3: Add preflight/postflight hooks**

In `stream_message()`:
- load compression state by `(user_id, session_id)`
- build compression-aware context payload before LLM calls
- after turn, update usage and possibly merge summary
- save session and compression state together

- [ ] **Step 4: Add internal observability events**

Record metrics counters only; do not add new client-visible events by default:
- `context_compression.watermark_level`
- `context_compression.tokens_released`
- `context_compression.summary_updates`

- [ ] **Step 5: Verify integration tests pass**

Run:

```bash
pytest -q tests/test_agent_core.py tests/test_websocket_protocol_envelope.py tests/test_session_tenant_isolation.py
```

- [ ] **Step 6: Commit**

```bash
git add server/backend/app/agent.py server/backend/app/main.py server/backend/app/models.py server/tests/test_agent_core.py server/tests/test_websocket_protocol_envelope.py
git commit -m "feat: integrate context compression lifecycle"
```

## Task 8: Regression And Acceptance

**Files:**
- Update docs only if behavior flags or env vars are added.

- [ ] **Step 1: Run focused backend tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q   tests/test_context_compression.py   tests/test_llm_usage.py   tests/test_session_tenant_isolation.py   tests/test_agent_core.py   tests/test_websocket_protocol_envelope.py   tests/test_db_stores.py   tests/test_session_ttl.py
```

- [ ] **Step 2: Run full backend regression**

```bash
cd /home/huadabioa/houlong/SoulDance/server
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests
```

Expected: PASS.

- [ ] **Step 3: Run protocol smoke check**

Use an existing websocket smoke or add a synthetic test that asserts event types remain unchanged for recommendation, clarification, product followup, and cart action.

- [ ] **Step 4: Inspect git diff**

```bash
git diff --check
git status --short
```

- [ ] **Step 5: Commit final docs or small fixes**

```bash
git add docs/superpowers/specs/2026-06-24-session-context-compression-spec.md docs/superpowers/plans/2026-06-24-session-context-compression.md
git commit -m "docs: plan session context compression"
```

## Implementation Notes

- The first production-safe milestone is Tasks 1-4: data model, usage ledger, and tenant isolation. Do not ship LLM summarization before this foundation exists.
- The current codebase already keeps only a bounded `context_events[-12:]`; the new design should preserve that simplicity while adding auditable compression state for future long sessions.
- Avoid using `text.length / 3` for trigger decisions. Use it only to rank candidate parts when provider usage is unavailable for streaming preflight.
- Product facts must continue to come from retrieval/product chunks, not from session summaries.
- Compression is backend-internal; Android should not need UI changes.
