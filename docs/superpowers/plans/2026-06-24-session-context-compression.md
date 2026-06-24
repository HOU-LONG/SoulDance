# Session Context Compression Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add progressive, tenant-isolated context compression for long-running ShopGuide Agent sessions without changing Android/WebSocket event payload shapes.

**Architecture:** Introduce a backend-only compression layer around `SessionContext` and LLM prompt construction. The first phase records provider token usage and maintains a deterministic compression ledger; later phases add living incremental summaries only after cheaper compaction actions are exhausted.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Pydantic, OpenAI-compatible chat completions, existing pytest backend suite.

---

## File Structure

- Create: `server/backend/app/context_compression.py`
  - Owns watermark policy, protected-window decisions, stable part ids, deterministic compaction, call-kind-specific context assembly, incremental-summary merge payloads, and emergency fallback assembly.
- Create: `server/backend/app/llm_usage.py`
  - Normalizes provider usage into `prompt_tokens`, `completion_tokens`, `total_tokens`, `source`, and `call_kind`.
- Modify: `server/backend/app/config.py`
  - Add `llm_context_limit` and optional model-name mapping support. Production code must not hard-code `128000`.
- Modify: `server/backend/app/models.py`
  - Add Pydantic models for `SessionCompressionState`, `CompressionPartDecision`, `LivingSummary`, and optional `user_id` on request models with a safe default for current clients.
- Modify: `server/backend/app/db/models.py`
  - Add `user_id` to `SessionState`, remove the old `session_id` unique constraint, add `UniqueConstraint(user_id, session_id)`, and add a new `SessionCompressionStateRow` table indexed by `(user_id, session_id)`.
- Modify: `server/backend/app/repositories/session_repository.py`
  - Enforce dual-key reads/writes where user id is available; keep a migration-compatible legacy default of `anonymous` for current clients.
- Modify: `server/backend/app/session_store.py`
  - Accept `user_id` in get/save helpers and route compression state through the repository/file path layer.
- Create: `server/scripts/migrate_session_tenant_keys.py`
  - One-time SQLite/Postgres-safe migration helper for deployments with an existing `session_states` table and no Alembic directory.
- Modify: `server/backend/app/llm_client.py`
  - Record real usage from non-streaming completions, attempt final usage capture for streaming completions, expose usage metadata, and add an optional summarization method.
- Modify: `server/backend/app/agent.py`
  - Use a per-session mutation lock, call compression preflight before LLM calls, and save compression state after each turn.
- Modify: `server/backend/app/main.py`
  - Pass `user_id` through request/session access while keeping existing Android clients compatible.
- Test: `server/tests/test_context_compression.py`
  - Unit tests for watermarks, protected windows, stable stubs, user-message privilege, call-kind context shapes, emergency fallback, and incremental summary merge windows.
- Test: `server/tests/test_llm_usage.py`
  - Unit tests for usage extraction across OpenAI-compatible response shapes, streaming final-usage chunks, and missing usage fallback.
- Test: `server/tests/test_session_tenant_isolation.py`
  - Repository and store tests proving `(user_id, session_id)` isolation and same-session-id multi-user behavior.
- Update: `server/tests/test_agent_core.py`, `server/tests/test_db_stores.py`, `server/tests/test_websocket_protocol_envelope.py`, `server/tests/test_session_ttl.py`
  - Focused integration tests that compression does not alter event protocol, product grounding, or TTL behavior.

## Watermark Contract

`model_context_limit` comes from `Settings.llm_context_limit`, optionally selected by model name. Tests may use `128000`, but production code must pass the configured value into compression policy helpers.

- Level 0, `maintain`: below 50 percent of model budget.
  - Record usage and stable part ids only.
- Level 1, `cheap_deterministic`: 50 to 70 percent.
  - Drop duplicate trace entries, compact old non-user tool payloads, replace old product cards with stable product id/title placeholders.
  - Must not call the LLM summarizer.
- Level 2, `structured_compaction`: 70 to 85 percent.
  - Keep recent protected window untouched; compact eligible `context_events` payloads into typed facts and product id references.
  - Must not call the LLM summarizer.
- Level 3, `incremental_summary`: 85 to 95 percent.
  - Merge newly eligible old events into living summary using at most one LLM summarizer call.
- Level 4, `emergency_fit`: above 95 percent or preflight over model limit.
  - Use living summary + protected recent turns + current user message + mandatory product evidence only. Never truncate current user text.
  - If the current user message alone cannot fit, return a split-input request instead of calling the LLM with a truncated prompt.

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


def test_compression_state_json_roundtrip_preserves_decisions():
    state = SessionCompressionState(user_id="u1", session_id="s1")
    state.decisions["s1:1:tool:0"] = CompressionPartDecision(
        part_id="s1:1:tool:0",
        action="placeholder",
        replacement_text="[tool output omitted: s1:1:tool:0]",
        original_token_count=1200,
        compressed_token_count=12,
        created_turn=1,
    )
    restored = SessionCompressionState.model_validate_json(state.model_dump_json())
    assert restored == state
```

- [ ] **Step 2: Run the targeted test**

Run:

```bash
cd /home/huadabioa/houlong/SoulDance/server
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_context_compression.py
```

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
    model_context_limit: int = 0
    last_total_tokens: int | None = None
    watermark_level: str = "maintain"
    decisions: dict[str, CompressionPartDecision] = Field(default_factory=dict)
    living_summary: LivingSummary = Field(default_factory=LivingSummary)
```

`model_context_limit` is populated from settings at runtime. Do not rely on a production default in the model.

- [ ] **Step 4: Verify targeted test passes**

Run the same pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/backend/app/models.py server/tests/test_context_compression.py
git commit -m "feat: add session compression models"
```

## Task 2: Add Watermark Policy, Configured Limits, And Stable Part Decisions

**Files:**
- Create: `server/backend/app/context_compression.py`
- Modify: `server/backend/app/config.py`
- Modify: `server/tests/test_context_compression.py`

- [ ] **Step 1: Write failing policy tests**

Cover:
- `choose_watermark_level(total_tokens=60000, limit=128000) == "maintain"`
- `choose_watermark_level(total_tokens=70000, limit=128000) == "cheap_deterministic"`
- `choose_watermark_level(total_tokens=110000, limit=128000) == "incremental_summary"`
- recent protected parts are not eligible even when one recent part is larger than 8000 approximate tokens
- user text parts are never truncated
- an existing stub decision is reused byte-for-byte
- runtime `model_context_limit` is read from settings rather than from the Pydantic model default

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
pytest -q tests/test_context_compression.py
```

- [ ] **Step 3: Add config source for context limit**

Add to `Settings`:

```python
llm_context_limit: int = 128000
```

Load from env:

```python
llm_context_limit=int(os.getenv("LLM_CONTEXT_LIMIT", "128000"))
```

If model-name mapping is added later, it must still resolve into this single runtime value before compression policy is called.

- [ ] **Step 4: Implement policy helpers**

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


def is_protected_part(part) -> bool:
    return bool(part.is_current_user_message or part.is_recent)


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

The protected-window builder decides which parts are recent using latest 8000 approximate tokens or latest 3 complete turns, whichever protects more context. `is_protected_part()` should not re-filter large recent messages.

- [ ] **Step 5: Verify tests pass**

Run:

```bash
pytest -q tests/test_context_compression.py
```

- [ ] **Step 6: Commit**

```bash
git add server/backend/app/context_compression.py server/backend/app/config.py server/tests/test_context_compression.py
git commit -m "feat: add progressive context compression policy"
```

## Task 3: Capture Real LLM Usage Including Streaming Reconciliation

**Files:**
- Create: `server/backend/app/llm_usage.py`
- Modify: `server/backend/app/llm_client.py`
- Create: `server/tests/test_llm_usage.py`

- [ ] **Step 1: Write usage extraction tests**

Cover OpenAI-style `response.usage.total_tokens`, camelCase `totalTokens`, missing usage, streaming final chunk usage, and preflight-only fallback when streaming usage is unavailable.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
pytest -q tests/test_llm_usage.py
```

- [ ] **Step 3: Implement usage normalization**

```python
class LLMUsage(BaseModel):
    call_kind: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    source: str = "provider"
    is_authoritative: bool = True
```

Add `extract_usage(response_or_chunk, call_kind)` and a `last_usage_by_call_kind` field on `DoubaoLLMClient`.

- [ ] **Step 4: Wire non-streaming calls**

Record usage in `_json_completion()`, `generate_response()`, and `select_products()`.

- [ ] **Step 5: Wire streaming calls**

For `stream_response()` and `stream_chitchat_response()`:

- request provider-supported streaming usage when available, for example OpenAI-compatible `stream_options={"include_usage": True}` if accepted by the endpoint
- inspect the final stream chunk for usage metadata
- write final usage to `last_usage_by_call_kind`
- when usage is missing, record a preflight-only `LLMUsage(source="preflight", is_authoritative=False)` and do not use it as the sole trigger for expensive compression

- [ ] **Step 6: Verify no behavior change**

Run:

```bash
pytest -q tests/test_llm_usage.py tests/test_agent_core.py::test_response_prompt_requires_short_paragraphs_or_bullets
```

- [ ] **Step 7: Commit**

```bash
git add server/backend/app/llm_usage.py server/backend/app/llm_client.py server/tests/test_llm_usage.py
git commit -m "feat: record provider token usage"
```

## Task 4: Add Tenant-Isolated Compression Persistence And Migration

> **Prerequisite:** `docs/superpowers/plans/2026-06-24-user-switching-and-tenant-isolation.md` Tasks 1-5 have shipped. `SessionRepository` is already keyed by `(user_id, session_id)`. This task now only adds the new `SessionCompressionStateRow` table and its dual-key methods; do NOT re-derive the identity layer.

**Files:**
- Modify: `server/backend/app/db/models.py`
- Modify: `server/backend/app/repositories/session_repository.py`
- Modify: `server/backend/app/session_store.py`
- Create: `server/scripts/migrate_session_tenant_keys.py`
- Create: `server/tests/test_session_tenant_isolation.py`
- Modify: `server/tests/test_db_stores.py`
- Modify: `server/tests/test_session_ttl.py`

- [ ] **Step 1: Write failing isolation tests**

Create two users with the same `session_id`; verify state and compression state do not leak between users and do not raise `IntegrityError`.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
pytest -q tests/test_session_tenant_isolation.py tests/test_db_stores.py
```

- [ ] **Step 3: Confirm migration mode**

The repo currently has SQLAlchemy models but no Alembic migration directory. Implement a one-time migration script instead of assuming `create_all()` changes existing tables.

Required migration SQL shape:

```sql
ALTER TABLE session_states ADD COLUMN user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous';
DROP INDEX IF EXISTS ix_session_states_session_id;
CREATE INDEX IF NOT EXISTS ix_session_states_session_id ON session_states (session_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_session_states_user_session ON session_states (user_id, session_id);
```

For SQLite, if the old unique constraint is implemented as an autoindex that cannot be dropped, rebuild the table in the migration script: create a new table, copy old rows with `user_id='anonymous'`, drop the old table, and rename the new table.

- [ ] **Step 4: Update SQLAlchemy table definitions**

- Change `SessionState.session_id` from `unique=True` to a non-unique indexed column.
- Add `user_id` as indexed, non-null, default `anonymous`.
- Add `UniqueConstraint("user_id", "session_id", name="uq_session_state_user_session")`.
- Add table `SessionCompressionStateRow` with `user_id`, `session_id`, `state_json`, `schema_version`, timestamps, and `UniqueConstraint("user_id", "session_id")`.

- [ ] **Step 5: Enforce dual-key repository methods**

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

- [ ] **Step 6: Update file persistence paths**

Use: `user_sessions/{safe_user_id}/sessions/{safe_session_id}/_internal/session.json` and `compression.json` for file-backed mode. Include path-sanitization tests.

- [ ] **Step 7: Verify targeted tests pass**

Run:

```bash
pytest -q tests/test_session_tenant_isolation.py tests/test_db_stores.py tests/test_session_ttl.py
```

- [ ] **Step 8: Commit**

```bash
git add server/backend/app/db/models.py server/backend/app/repositories/session_repository.py server/backend/app/session_store.py server/scripts/migrate_session_tenant_keys.py server/tests/test_session_tenant_isolation.py server/tests/test_db_stores.py server/tests/test_session_ttl.py
git commit -m "feat: isolate session compression by user and session"
```

## Task 5: Compose Compressed LLM Contexts Per Call Kind

**Files:**
- Modify: `server/backend/app/context_compression.py`
- Modify: `server/backend/app/semantic_layer.py`
- Modify: `server/backend/app/llm_client.py`
- Modify: `server/tests/test_context_compression.py`
- Modify: `server/tests/test_agent_core.py`

- [ ] **Step 1: Inspect current call sites and prompt fixtures**

Run:

```bash
grep -R -n "semantic_context_payload\\|parse_semantic_frame\\|classify_contextual_followup\\|select_products\\|generate_response\\|stream_response\\|stream_chitchat_response" server/backend/app server/tests
find server/backend/app/prompts -maxdepth 3 -type f -print
```

Record whether any tests assert exact prompt JSON shape. Do not add new keys to strict fixtures without updating tests in the same task.

- [ ] **Step 2: Write failing assembly tests**

Assert:
- current user message is present verbatim
- latest protected events are present verbatim
- old product cards become stable product placeholders
- living summary is included before protected recent context only for call kinds that need it
- `selection` context excludes living summary unless the test explicitly enables it
- `response` context keeps product evidence authoritative and does not use summary product facts

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
pytest -q tests/test_context_compression.py tests/test_agent_core.py
```

- [ ] **Step 4: Implement context assembly**

Add `build_llm_context_payload(context, compression_state, request, call_kind)`.

Call-kind defaults:

```python
CALL_KIND_CONTEXT_POLICY = {
    "semantic_parse": {"include_living_summary": True, "include_recent_context": True, "include_product_evidence": False},
    "contextual_followup": {"include_living_summary": True, "include_recent_context": True, "include_product_evidence": False},
    "selection": {"include_living_summary": False, "include_recent_context": False, "include_product_evidence": True},
    "response": {"include_living_summary": False, "include_recent_context": False, "include_product_evidence": True},
    "chitchat": {"include_living_summary": True, "include_recent_context": True, "include_product_evidence": False},
}
```

Output shape:

```python
{
    "living_summary": state.living_summary.text if policy["include_living_summary"] else "",
    "stable_placeholders": [decision.model_dump(mode="json") for decision in reused_decisions],
    "protected_recent_context": recent_context_payload if policy["include_recent_context"] else {},
    "current_user_message": request.message,
    "current_focus": focus_payload,
}
```

- [ ] **Step 5: Wire semantic/followup context payloads**

Keep existing `semantic_context_payload()` fields but add `compression` under a new key only after the grep from Step 1 confirms no strict consumer will reject it.

- [ ] **Step 6: Verify tests pass**

Run:

```bash
pytest -q tests/test_context_compression.py tests/test_agent_core.py
```

- [ ] **Step 7: Commit**

```bash
git add server/backend/app/context_compression.py server/backend/app/semantic_layer.py server/backend/app/llm_client.py server/tests/test_context_compression.py server/tests/test_agent_core.py
git commit -m "feat: compose compressed llm session context"
```

## Task 6: Add Incremental Summary Merge

**Files:**
- Modify: `server/backend/app/context_compression.py`
- Modify: `server/backend/app/llm_client.py`
- Create: `server/backend/app/prompts/v1/context_summary.txt`
- Modify: `server/backend/app/prompt_registry.py` only if prompt registration requires it
- Modify: `server/tests/test_context_compression.py`

- [ ] **Step 1: Confirm prompt registry convention**

Run:

```bash
find server/backend/app/prompts -maxdepth 3 -type f -print | sort
sed -n '1,220p' server/backend/app/prompt_registry.py
```

If `prompts/v1/*.txt` is the existing convention, add `context_summary.txt` there. If the registry requires explicit registration, update `prompt_registry.py` in this task.

- [ ] **Step 2: Write failing incremental summary tests**

Assert that:
- only not-yet-covered eligible part ids are summarized
- covered part ids are persisted
- newer facts supersede stale old facts
- protected recent parts are excluded
- summarizer failure reuses the previous living summary and marks the update as failed without blocking the main response

- [ ] **Step 3: Add context summary prompt**

Prompt contract:
- input is living summary + new events only
- output is plain Markdown or text summary, not JSON
- preserve user goals, constraints, product ids, rejected options, pending tasks
- do not invent product facts
- prefer replacing stale facts over accumulating contradictions

- [ ] **Step 4: Implement summarizer method**

Add `merge_context_summary(existing_summary, new_parts)` to `DoubaoLLMClient`; `FakeLLMClient` returns deterministic merged text for tests.

- [ ] **Step 5: Implement merge orchestration**

`maybe_update_living_summary(context, compression_state, usage, llm_client)` triggers only at Level 3+ and at most once per user turn.

- [ ] **Step 6: Verify targeted tests pass**

Run:

```bash
pytest -q tests/test_context_compression.py tests/test_llm_usage.py
```

- [ ] **Step 7: Commit**

```bash
git add server/backend/app/context_compression.py server/backend/app/llm_client.py server/backend/app/prompts/v1/context_summary.txt server/backend/app/prompt_registry.py server/tests/test_context_compression.py
git commit -m "feat: add incremental session context summary"
```

## Task 7: Integrate Per-Session Locking With Agent Turn Lifecycle

**Files:**
- Modify: `server/backend/app/agent.py`
- Modify: `server/backend/app/main.py`
- Modify: `server/backend/app/models.py`
- Modify: `server/backend/app/context_compression.py`
- Modify: `server/tests/test_websocket_protocol_envelope.py`
- Modify: `server/tests/test_agent_core.py`

- [ ] **Step 1: Write integration and concurrency tests**

Cover:
- a long synthetic session triggers deterministic compaction
- protocol event types and payload shapes are unchanged
- product followup still carries focus product context
- cart action does not invoke LLM summary
- two concurrent turns for the same `(user_id, session_id)` serialize compression-state mutation and do not overwrite decisions or living summary

- [ ] **Step 2: Add `user_id` compatibility field**

Add optional `user_id: str = "anonymous"` to `ChatRequest`, `CartActionRequest`, feedback request models where needed. Existing Android clients keep working because field is optional.

- [ ] **Step 3: Add session-level lock registry**

Use an in-process `asyncio.Lock` keyed by `(user_id, session_id)` for the current single-worker backend. Keep the lock scope around compression state load/mutate/save. If multi-worker deployment is introduced, replace this with database row locks or advisory locks.

- [ ] **Step 4: Add preflight/postflight hooks**

In `stream_message()`:
- load compression state by `(user_id, session_id)`
- build compression-aware context payload before LLM calls
- after turn, update usage and possibly merge summary
- save session and compression state together while holding the session lock

- [ ] **Step 5: Verify integration tests pass**

Run:

```bash
pytest -q tests/test_agent_core.py tests/test_websocket_protocol_envelope.py tests/test_session_tenant_isolation.py
```

- [ ] **Step 6: Commit**

```bash
git add server/backend/app/agent.py server/backend/app/main.py server/backend/app/models.py server/backend/app/context_compression.py server/tests/test_agent_core.py server/tests/test_websocket_protocol_envelope.py
git commit -m "feat: integrate context compression lifecycle"
```

## Task 8: Add Observability And Performance Acceptance

**Files:**
- Modify: `server/backend/app/observability.py` only if existing `InMemoryMetrics` cannot record the needed counters
- Modify: `server/backend/app/main.py`
- Modify: `server/tests/test_observability.py`
- Modify: `server/tests/test_context_compression.py`

- [ ] **Step 1: Inspect existing metrics sink**

Run:

```bash
sed -n '1,220p' server/backend/app/observability.py
grep -R -n "context_compression\\|metrics.increment\\|metrics.snapshot" server/backend/app server/tests
```

If `InMemoryMetrics` supports named counters, use it. Do not create a new metrics framework in this feature.

- [ ] **Step 2: Add observability tests**

Assert counters exist for:
- `context_compression.watermark_level.maintain`
- `context_compression.watermark_level.cheap_deterministic`
- `context_compression.tokens_released`
- `context_compression.summary_updates`
- `context_compression.summary_failures`

- [ ] **Step 3: Add synthetic performance test or script**

Add a lightweight test/helper that builds a 100-turn synthetic session and measures local compression assembly overhead without network LLM calls. Target: p95 below 30 ms on the backend test environment. Mark the test deterministic and avoid relying on external APIs.

- [ ] **Step 4: Verify focused tests pass**

Run:

```bash
pytest -q tests/test_observability.py tests/test_context_compression.py
```

- [ ] **Step 5: Commit**

```bash
git add server/backend/app/observability.py server/backend/app/main.py server/tests/test_observability.py server/tests/test_context_compression.py
git commit -m "test: cover context compression observability"
```

## Task 9: Regression And Acceptance

**Files:**
- Update docs only if behavior flags or env vars are added.

- [ ] **Step 1: Run focused backend tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q \
  tests/test_context_compression.py \
  tests/test_llm_usage.py \
  tests/test_session_tenant_isolation.py \
  tests/test_agent_core.py \
  tests/test_websocket_protocol_envelope.py \
  tests/test_db_stores.py \
  tests/test_session_ttl.py \
  tests/test_observability.py
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
git commit -m "docs: refine session context compression plan"
```

## Implementation Notes

- The first production-safe milestone is Tasks 1-4: data model, usage ledger, and tenant isolation. Do not ship LLM summarization before this foundation exists.
- The current codebase already keeps only a bounded `context_events[-12:]`; the new design should preserve that simplicity while adding auditable compression state for future long sessions.
- Avoid using `text.length / 3` for trigger decisions. Use it only to rank candidate parts when provider usage is unavailable for streaming preflight.
- Product facts must continue to come from retrieval/product chunks, not from session summaries.
- Compression is backend-internal; Android should not need UI changes.
- `Cart`, `Order`, and `FeedbackEvent` tenant migration is explicitly out of scope for this phase but must not be made harder by this schema work.
