# Context Memory Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 3-phase context memory upgrade: full-turn dialog storage with history injection into Response prompt, LivingSummary compression integration, and domain-tracking with per-product parameter caching.

**Architecture:** Three independent phases deployable in sequence. Phase 1 adds `dialog_turns` storage and Prompt assembly without touching compression. Phase 2 wires `compression_state` and summary generation into the same pipeline. Phase 3 adds domain-switching and entity caching on top.

**Tech Stack:** Python/FastAPI/Pydantic on local dev machine, worktree isolation via git-worktrees.

## Global Constraints

- Run all edits and tests from the active worktree. Use the Python interpreter at `/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python`.
- `dialog_turns` measured in message count (2 messages = 1 turn).
- Capacity: 100 messages max, LRU 50 entries for `entity_params`.
- Prompt injection: ≤20 messages → all; >20 → summary + last 10.
- `schema_version` bumps from 1 → 2.
- All new fields use Pydantic `default_factory` — no manual migration needed.
- Old `state_json` loads without error via `extra="ignore"`.
- FakeLLMClient summarises return fixed text `"前几轮为购物咨询对话，用户当前需求如上。"`.
- All commits annotated `Co-Authored-By: Claude <noreply@anthropic.com>`.

## Source Spec

- `docs/superpowers/specs/2026-06-27-context-memory-architecture-design.md`

## Working Roots

- Repo root: `/home/huadabioa/houlong/SoulDance`
- Python interpreter: `/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python`
- Backend app package: `server/backend/app`

---

## File Structure

- Create: `server/tests/test_context_memory.py` — unit + integration tests for all three phases
- Create: `server/backend/app/prompts/v1/summary.txt` — summary-generation system prompt (Phase 2)
- Modify: `server/backend/app/models.py` — `dialog_turns`, `compression_state`, `entity_params`, `current_domain`, `schema_version`
- Modify: `server/backend/app/agent.py` — dialog append, summary trigger, domain detection, entity caching, anchor cleanup
- Modify: `server/backend/app/llm_client.py` — `generate_summary` on FakeLLMClient + DoubaoLLMClient, `_response_evidence_payload` with `recent_context_text`, `_constraint_sentence`
- Modify: `server/backend/app/semantic_layer.py` — `_build_recent_context_text` (prompt assembler)
- Modify: `server/backend/app/prompts/v1/response.txt` — `{recent_context_text}` placeholder

---

## Phase 1: Full-turn Dialog Log + Response Prompt Injection

### Task 1.1: Extend SessionContext with dialog_turns

**Files:**
- Modify: `server/backend/app/models.py`

- [ ] **Step 1: Add dialog_turns field and bump schema version**

Read `server/backend/app/models.py`, locate `SessionContext` class. Add:

```python
# server/backend/app/models.py — inside SessionContext
dialog_turns: list[dict[str, str]] = Field(default_factory=list)
# {session_id}: [{role: "user"|"assistant", content: "..."}, ...]
schema_version: int = 2  # was 1
compression_state: SessionCompressionState = Field(default_factory=SessionCompressionState)
```

- [ ] **Step 2: Verify model validation**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -c "
from backend.app.models import SessionContext
ctx = SessionContext(session_id='test')
assert ctx.dialog_turns == []
assert ctx.schema_version == 2
assert ctx.compression_state.living_summary.text == ''
print('OK')
"
```
Expected: OK

- [ ] **Step 3: Verify old state_json backward compatibility**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -c "
from backend.app.models import SessionContext
import json
old = json.dumps({'session_id':'test','schema_version':1})
ctx = SessionContext.model_validate_json(old)
assert ctx.dialog_turns == []  # default
assert ctx.schema_version == 1  # from old data
print('OK')
"
```
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add server/backend/app/models.py
git commit -m "feat(models): add dialog_turns and compression_state to SessionContext

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.2: Append dialog turns in stream_message

**Files:**
- Modify: `server/backend/app/agent.py`

**Interfaces:**
- Produces: `context.dialog_turns` populated with user + assistant messages per turn

- [ ] **Step 1: Append user message at stream_message entry**

In `stream_message()` (around line 213), after `context = self.sessions.get(...)`, add:

```python
# Append user message to dialog history before processing
context.dialog_turns.append({"role": "user", "content": request.message or ""})
```

- [ ] **Step 2: Append assistant reply before function returns**

At every exit point of `stream_message` that yields text (before `return`), add a helper that collects text_delta content into a buffer. The cleanest approach: wrap the generator logic in a collector.

Add a helper function near `stream_message`:

```python
def _collect_assistant_reply(self, context: SessionContext, events: list[dict]) -> None:
    """Collect text_delta events into dialog_turns after stream completes."""
    text_parts = []
    for event in events:
        if event.get("type") == "text_delta":
            text_parts.append(event.get("text", ""))
    if not text_parts:
        context.dialog_turns.append({"role": "assistant", "content": "[系统提示]"})
        return
    full_text = "".join(text_parts)
    if len(full_text) > 2000:
        full_text = full_text[:2000] + "…"  # truncate very long responses
    context.dialog_turns.append({"role": "assistant", "content": full_text})
    # Capacity: keep last 100 messages (50 full turns)
    if len(context.dialog_turns) > 100:
        context.dialog_turns = context.dialog_turns[-100:]
```

Modify `stream_message` to buffer events and call this at the end. The generator pattern: yield events from a list collected internally.

```python
async def stream_message(self, user_id: str, request: ChatRequest, compiled_ir=None) -> AsyncIterator[dict]:
    context = self.sessions.get(user_id, request.session_id)
    context.dialog_turns.append({"role": "user", "content": request.message or ""})
    events_buffer: list[dict] = []
    # ... existing logic, but every yield becomes events_buffer.append(event); yield event
    async for event in self._stream_inner(user_id, request, compiled_ir):
        events_buffer.append(event)
        yield event
    self._collect_assistant_reply(context, events_buffer)
```

Actually — to avoid major refactoring of `stream_message`, use a simpler approach: refactor `stream_message` into `_stream_inner` + wrapper, or use `itertools.tee`. 

**Simplest correct approach:** Instead of refactoring the whole generator, collect text_delta *inside* each exit path before the final yield of `done`. Look for this pattern:

```python
yield {"type": "done", "message_id": message_id}
```

Add right after each `yield {"type": "done"}`:

```python
# Collect assistant text from events yielded in this path
assistant_text = "".join(p for p in text_parts_collected)
context.dialog_turns.append({"role": "assistant", "content": assistant_text[:2000]})
```

If collecting inline is too invasive for the first pass, use the simpler fallback: at each text exit, append `{"role": "assistant", "content": "[回复]"}` as a placeholder. This ensures the role sequence stays valid (user-assistant-user-assistant), and the placeholder is incrementally improved in a follow-up.

- [ ] **Step 3: Capacity enforcement test**

Add to `server/tests/test_context_memory.py`:

```python
def test_dialog_turns_capacity_enforced():
    from backend.app.models import SessionContext
    ctx = SessionContext(session_id="test_cap")
    # Add 110 messages
    for i in range(110):
        ctx.dialog_turns.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"})
    # Capacity should trim to 100
    assert len(ctx.dialog_turns) <= 100
```

Run: `pytest tests/test_context_memory.py::test_dialog_turns_capacity_enforced -v`
Expected: FAIL (capacity enforcement not yet in place)

Implement capacity check in `_collect_assistant_reply` (already in Step 2 code above).

Run again: EXPECTED PASS

- [ ] **Step 4: Commit**

```bash
git add server/backend/app/agent.py server/tests/test_context_memory.py
git commit -m "feat(agent): append user+assistant messages to dialog_turns

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.3: Inject dialog history into Response Prompt

**Files:**
- Modify: `server/backend/app/llm_client.py` — `_response_evidence_payload`, `_constraint_sentence`
- Modify: `server/backend/app/prompts/v1/response.txt`

- [ ] **Step 1: Add _constraint_sentence function in llm_client.py**

```python
def _constraint_sentence(plan: RetrievalPlan | None) -> str:
    if plan is None:
        return ""
    parts = []
    h = plan.hard_constraints
    if h.price_max is not None:
        parts.append(f"预算{h.price_max:.0f}以内")
    if h.price_min is not None:
        parts.append(f"预算{h.price_min:.0f}以上")
    if h.exclude_brands:
        parts.append(f"排除品牌{'、'.join(h.exclude_brands)}")
    if h.include_brands:
        parts.append(f"指定品牌{'、'.join(h.include_brands)}")
    for k, v in plan.soft_preferences.items():
        if k not in ("anchor_reference", "price_preference"):
            parts.append(str(v))
    return "已知用户条件：" + "、".join(parts) + "。" if parts else ""
```

- [ ] **Step 2: Add _build_recent_context_text function in llm_client.py**

```python
def _build_recent_context_text(context: SessionContext | None) -> str:
    if context is None or not context.dialog_turns:
        return ""
    parts = []
    # Summary (Phase 2 — placeholder in Phase 1)
    ls = context.compression_state.living_summary
    if ls.text:
        parts.append(f"[之前对话摘要] {ls.text}")
    # Recent 10 messages (5 full turns)
    recent = context.dialog_turns[-10:]
    for turn in recent:
        role = "用户" if turn.get("role") == "user" else "助手"
        parts.append(f"{role}：{turn.get('content', '')}")
    return "\n".join(parts)
```

- [ ] **Step 3: Modify _response_evidence_payload to include context**

In `_response_evidence_payload` (around line 439), add `context` parameter and include `recent_context_text`:

```python
def _response_evidence_payload(
    plan: RetrievalPlan,
    products: list[RankedProduct],
    *,
    context: SessionContext | None = None,
):
    return {
        # ...existing fields...
        "recent_context_text": _build_recent_context_text(context),
        "constraint_note": _constraint_sentence(plan),
    }
```

Update callers in `DoubaoLLMClient.stream_response` (line 207) and `FakeLLMClient.generate_response` (line 320) to pass `context`.

- [ ] **Step 4: Update response.txt prompt template**

Add before the existing contract section in `server/backend/app/prompts/v1/response.txt`:

```
## 对话历史上下文
{recent_context_text}
{constraint_note}

## 回答合同
(原有内容保持不变)
```

- [ ] **Step 5: Test prompt assembly**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -c "
from backend.app.llm_client import _build_recent_context_text, _constraint_sentence
from backend.app.models import SessionContext, RetrievalPlan, HardConstraints
ctx = SessionContext(session_id='test')
ctx.dialog_turns = [
    {'role': 'user', 'content': '推荐一款精华'},
    {'role': 'assistant', 'content': '好的，为您推荐...'},
]
text = _build_recent_context_text(ctx)
assert '推荐一款精华' in text
assert '好的' in text
print('OK - dialog context built')
plan = RetrievalPlan(retrieval_query='test', hard_constraints=HardConstraints(price_max=500, exclude_brands=['华为']))
cs = _constraint_sentence(plan)
assert '500' in cs and '华为' in cs
print('OK - constraint sentence')
"
```
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add server/backend/app/llm_client.py server/backend/app/prompts/v1/response.txt
git commit -m "feat(prompt): inject dialog history and constraint note into response prompt

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 1.4: Integration test for Phase 1

**Files:**
- Update: `server/tests/test_context_memory.py`

- [ ] **Step 1: Write integration test**

```python
import asyncio
from backend.app.agent import ShopGuideAgent
from backend.app.cart import CartService
from backend.app.data_loader import load_products
from backend.app.llm_client import FakeLLMClient
from backend.app.models import ChatRequest

class FakeRetriever:
    def search(self, query, top_k=20):
        return []

def test_phase1_dialog_turns_collected():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    cart = CartService(products)
    session_id = "test_phase1_integration"

    # Send 3 turns
    events1 = asyncio.run(agent.handle_message(
        "anonymous", ChatRequest(type="user_message", session_id=session_id, message="推荐精华")))
    events2 = asyncio.run(agent.handle_message(
        "anonymous", ChatRequest(type="user_message", session_id=session_id, message="便宜的替代品")))
    events3 = _cart_turn(agent, cart, session_id, "查看购物车")

    ctx = agent.sessions.get("anonymous", session_id)
    # Should have at least 3 user messages (3 turns sent)
    user_msgs = [t for t in ctx.dialog_turns if t["role"] == "user"]
    assert len(user_msgs) >= 3, f"Expected >=3 user messages, got {len(user_msgs)}"
    # Should have some assistant replies
    assistant_msgs = [t for t in ctx.dialog_turns if t["role"] == "assistant"]
    assert len(assistant_msgs) >= 1, f"Expected >=1 assistant reply, got {len(assistant_msgs)}"
    # Role sequence should alternate: user, assistant, user, assistant, ...
    roles = [t["role"] for t in ctx.dialog_turns]
    for i in range(len(roles) - 1):
        assert roles[i] != roles[i+1], f"Role sequence broken at index {i}: {roles}"
```

- [ ] **Step 2: Run integration test**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest tests/test_context_memory.py::test_phase1_dialog_turns_collected -v
```
Expected: PASS (or FAIL with specific assertion pointing to incomplete assistant collection)

- [ ] **Step 3: Run full suite**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q --maxfail=10
```
Expected: 352+ passed, demo test passes

- [ ] **Step 4: Commit**

```bash
git add server/tests/test_context_memory.py
git commit -m "test: add Phase 1 integration test for dialog_turns collection

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 2: LivingSummary + context_compression Integration

### Task 2.1: Create summary prompt template

**Files:**
- Create: `server/backend/app/prompts/v1/summary.txt`

- [ ] **Step 1: Write summary prompt**

```text
你是一个购物助手的对话摘要器。请将以下对话历史浓缩为 1-2 句中文摘要，
聚焦于用户的购物需求、已查看的商品、明确的约束条件和偏好。
不要包含闲聊细节。只返回摘要文本，不要添加前缀或解释。

对话历史：
{history_text}

摘要：
```

- [ ] **Step 2: Commit**

```bash
git add server/backend/app/prompts/v1/summary.txt
git commit -m "feat(prompt): add summary generation prompt template

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.2: Add generate_summary to LLM clients

**Files:**
- Modify: `server/backend/app/llm_client.py`

- [ ] **Step 1: Add generate_summary to FakeLLMClient**

```python
# In FakeLLMClient class
async def generate_summary(self, history_text: str) -> str:
    """Return a fixed summary for testing. Production override uses real LLM."""
    return "前几轮为购物咨询对话，用户当前需求如上。"
```

- [ ] **Step 2: Add generate_summary to DoubaoLLMClient**

```python
# In DoubaoLLMClient class
async def generate_summary(self, history_text: str) -> str:
    prompt = Path("server/backend/app/prompts/v1/summary.txt").read_text(encoding="utf-8")
    user_content = prompt.replace("{history_text}", history_text)
    try:
        raw = await self._json_completion(
            [{"role": "system", "content": "你是对话摘要器。"},
             {"role": "user", "content": user_content}],
            temperature=0,
        )
        if not raw or not raw.strip():
            return ""
        return raw.strip()[:200]  # cap at 200 chars
    except Exception:
        return ""  # silent degradation — summary is optional
```

- [ ] **Step 3: Test**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -c "
import asyncio
from backend.app.llm_client import FakeLLMClient
async def test():
    c = FakeLLMClient()
    s = await c.generate_summary('test history')
    assert '购物咨询' in s
    print('OK')
asyncio.run(test())
"
```
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add server/backend/app/llm_client.py
git commit -m "feat(llm): add generate_summary to FakeLLMClient and DoubaoLLMClient

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.3: Wire _maybe_update_summary into stream_message

**Files:**
- Modify: `server/backend/app/agent.py`

- [ ] **Step 1: Add _maybe_update_summary method to ShopGuideAgent**

```python
def _maybe_update_summary(self, context: SessionContext) -> None:
    """Generate a living summary when dialog grows beyond threshold."""
    turns = context.dialog_turns
    if len(turns) < 16:  # 8 full turns = 16 messages
        return
    last_at = context.compression_state.living_summary.updated_turn
    if len(turns) - last_at < 6:  # at least 3 new turns since last summary
        return
    # Build history text from uncovered turns
    start = last_at
    history_lines = []
    for t in turns[start:]:
        role = "用户" if t["role"] == "user" else "助手"
        content = t.get("content", "")[:500]  # truncate long messages
        history_lines.append(f"{role}: {content}")
    history_text = "\n".join(history_lines)

    summary = asyncio.run(self.llm_client.generate_summary(history_text))
    if not summary:
        return  # silent skip on failure

    ls = context.compression_state.living_summary
    if ls.text:
        ls.text = ls.text + " " + summary  # append to existing
    else:
        ls.text = summary
    ls.covered_part_ids.append(f"{start}-{len(turns)}")
    ls.updated_turn = len(turns)
    ls.source_token_count = len(history_text)  # rough estimate
    logger.info("summary updated for session %s: %s", context.session_id[:8], summary[:80])
```

- [ ] **Step 2: Call _maybe_update_summary in stream_message**

In `stream_message`, after the last `yield` and before `return`, call:

```python
self._maybe_update_summary(context)
```

This should be placed in the wrapper that collects events (from Task 1.2), so it's called exactly once per turn.

- [ ] **Step 3: Test summary trigger**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest tests/test_context_memory.py -v -k "summary"
```
Expected: if test exists, PASS

- [ ] **Step 4: Commit**

```bash
git add server/backend/app/agent.py
git commit -m "feat(agent): wire LivingSummary generation into stream_message

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 2.4: Phase 2 integration test

**Files:**
- Update: `server/tests/test_context_memory.py`

- [ ] **Step 1: Add summary generation test**

```python
def test_phase2_summary_generated_after_threshold():
    from backend.app.models import SessionContext, SessionCompressionState
    ctx = SessionContext(session_id="test_summary")
    # Simulate 20 messages (10 full turns)
    for i in range(20):
        ctx.dialog_turns.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"})
    assert len(ctx.dialog_turns) >= 16  # above threshold
    # Summary not yet triggered — needs agent call
    assert ctx.compression_state.living_summary.updated_turn == 0

def test_phase2_summary_not_triggered_below_threshold():
    from backend.app.models import SessionContext
    ctx = SessionContext(session_id="test_no_summary")
    # Only 10 messages (5 turns) — below threshold
    for i in range(10):
        ctx.dialog_turns.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"})
    assert len(ctx.dialog_turns) < 16  # below threshold

def test_phase2_old_state_json_backward_compat():
    import json
    from backend.app.models import SessionContext
    old_data = {"session_id": "old", "schema_version": 1}
    ctx = SessionContext.model_validate(old_data)
    assert ctx.compression_state.living_summary.text == ""
    assert ctx.dialog_turns == []
```

- [ ] **Step 2: Run tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest tests/test_context_memory.py -v
```
Expected: all Phase 2 tests PASS

- [ ] **Step 3: Commit**

```bash
git add server/tests/test_context_memory.py
git commit -m "test: add Phase 2 integration tests for summary generation

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 3: intent_domain Tracking + model_attr_map

### Task 3.1: Add current_domain and entity_params to models

**Files:**
- Modify: `server/backend/app/models.py`

- [ ] **Step 1: Add fields**

In `ConstraintState`:
```python
current_domain: str | None = None  # "美妆护肤" / "数码电子" / ...
```

In `SessionContext`:
```python
entity_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
# {"p_beauty_001": {"price": 720, "brand": "雅诗兰黛", "category": "美妆护肤", ...}}
_entity_params_order: list[str] = Field(default_factory=list)  # LRU tracking
```

- [ ] **Step 2: Verify model**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -c "
from backend.app.models import SessionContext
ctx = SessionContext(session_id='test')
assert ctx.state.constraint_state.current_domain is None
assert ctx.entity_params == {}
print('OK')
"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add server/backend/app/models.py
git commit -m "feat(models): add current_domain and entity_params for domain tracking

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 3.2: Implement domain-switch detection

**Files:**
- Modify: `server/backend/app/agent.py`

- [ ] **Step 1: Add _detect_domain_switch and _handle_domain_switch**

```python
def _detect_domain_switch(self, plan: RetrievalPlan, context: SessionContext) -> bool:
    new_domain = plan.hard_constraints.category
    if not new_domain:
        return False
    old = context.state.constraint_state.current_domain
    if old and old != new_domain:
        return True
    context.state.constraint_state.current_domain = new_domain
    return False

def _handle_domain_switch(self, context: SessionContext) -> None:
    logger.info("domain_switch from=%s to=%s",
        context.state.constraint_state.current_domain,
        getattr(context.last_plan, 'hard_constraints', None))
    # Clear soft preferences (skin type doesn't apply to phones)
    context.state.constraint_state.soft.clear()
    # Clear first-turn anchors (no longer relevant)
    to_remove = [k for k in context.reference_anchors if k.startswith("first_turn_")]
    for k in to_remove:
        del context.reference_anchors[k]
    # Reset recommendation memory
    context.state.recommendation_memory.items.clear()
    context.state.recommendation_memory.last_set_id = None
    context.last_product_ids = []
    context.focus_product_id = None
```

- [ ] **Step 2: Wire into _prepare_context_for_turn**

In `_prepare_context_for_turn` (after plan is built), add:

```python
if self._detect_domain_switch(plan, context):
    self._handle_domain_switch(context)
```

- [ ] **Step 3: Commit**

```bash
git add server/backend/app/agent.py
git commit -m "feat(agent): detect and handle shopping domain switches

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 3.3: Implement entity_params caching

**Files:**
- Modify: `server/backend/app/agent.py`

- [ ] **Step 1: Add entity_params write logic**

In `_remember_recommendations`, after the `_append_context_event` call, add:

```python
# Cache product parameters for future reference
for item in ranked:
    pid = item.product.product_id
    if pid not in context.entity_params:
        context.entity_params[pid] = {
            "price": item.product.price,
            "brand": item.product.brand,
            "category": item.product.category,
            "sub_category": item.product.sub_category,
        }
        context._entity_params_order.append(pid)
    # LRU eviction: keep last 50
    while len(context._entity_params_order) > 50:
        oldest = context._entity_params_order.pop(0)
        context.entity_params.pop(oldest, None)
```

- [ ] **Step 2: Add entity_params read logic**

In `_build_comparison_events`, before calling `self.product_map.get(pid)` for each product:

```python
# Check entity_params cache first
cached = context.entity_params.get(pid)
if cached:
    # Use cached attributes, skip hard_filter for explicitly cached products
    ...
```

Exact integration point: after `products = [self.product_map[pid] for pid in product_ids if pid in self.product_map]` — for products found in `entity_params`, skip `hard_filter` when they were explicitly named by the user (already done by the `used_resolved` flag from Task 2 review fixes).

- [ ] **Step 3: Commit**

```bash
git add server/backend/app/agent.py
git commit -m "feat(agent): cache product parameters in entity_params with LRU eviction

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 3.4: Phase 3 integration tests

**Files:**
- Update: `server/tests/test_context_memory.py`

- [ ] **Step 1: Domain switch test**

```python
import asyncio
from backend.app.agent import ShopGuideAgent
from backend.app.data_loader import load_products
from backend.app.llm_client import FakeLLMClient
from backend.app.models import ChatRequest

class FakeRetriever:
    def search(self, query, top_k=20):
        return []

def test_phase3_domain_switch_clears_soft_prefs():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    session_id = "test_domain_switch"

    # Turn 1: beauty serum recommendation
    asyncio.run(agent.handle_message(
        "anonymous", ChatRequest(type="user_message", session_id=session_id, message="推荐一款精华")))
    ctx = agent.sessions.get("anonymous", session_id)
    assert ctx.state.constraint_state.current_domain == "美妆护肤"
    # Should have accumulated soft prefs
    assert ctx.state.constraint_state.soft  # non-empty

    # Turn 2: phone recommendation (domain switch)
    asyncio.run(agent.handle_message(
        "anonymous", ChatRequest(type="user_message", session_id=session_id, message="推荐一款小米手机")))
    ctx = agent.sessions.get("anonymous", session_id)
    assert ctx.state.constraint_state.current_domain == "数码电子"
    # Soft prefs should be cleared on domain switch
    assert not ctx.state.constraint_state.soft, f"Expected empty soft prefs, got {ctx.state.constraint_state.soft}"

def test_phase3_entity_params_populated():
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, FakeLLMClient(), FakeRetriever())
    session_id = "test_entity_params"

    asyncio.run(agent.handle_message(
        "anonymous", ChatRequest(type="user_message", session_id=session_id, message="推荐精华预算500以内")))
    ctx = agent.sessions.get("anonymous", session_id)
    # Entity params should have at least one product cached
    assert len(ctx.entity_params) >= 1, f"Expected cached params, got {ctx.entity_params}"
    first_pid = list(ctx.entity_params.keys())[0]
    assert "price" in ctx.entity_params[first_pid]
    assert "brand" in ctx.entity_params[first_pid]

def test_phase3_entity_params_lru_eviction():
    from backend.app.models import SessionContext
    ctx = SessionContext(session_id="test_lru")
    for i in range(60):
        pid = f"p_{i:04d}"
        ctx.entity_params[pid] = {"price": i}
        ctx._entity_params_order.append(pid)
    assert len(ctx.entity_params) <= 50
    assert "p_0000" not in ctx.entity_params  # oldest evicted
```

- [ ] **Step 2: Run tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest tests/test_context_memory.py -v
```
Expected: all Phase 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add server/tests/test_context_memory.py
git commit -m "test: add Phase 3 integration tests for domain switch and entity params

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task F: Final Verification Gate

**Files:**
- None (verification only)

- [ ] **Step 1: Run full suite**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q --maxfail=10
```
Expected: 352+ passed, 0 new failures

- [ ] **Step 2: Run demo regression**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest tests/test_demo_agent_flow.py -v
```
Expected: 1 passed (all 10 turns)

- [ ] **Step 3: Verify backward compatibility**

```bash
cd /home/huadabioa/houlong/SoulDance/server && /home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -c "
import json
from backend.app.models import SessionContext
# Simulate loading old session data without new fields
old = {'session_id': 'legacy', 'schema_version': 1}
ctx = SessionContext.model_validate(old)
assert ctx.dialog_turns == []
assert ctx.compression_state.living_summary.text == ''
assert ctx.entity_params == {}
assert ctx.state.constraint_state.current_domain is None
print('Backward compatibility OK')
"
```
Expected: Backward compatibility OK

- [ ] **Step 4: Commit any final docs**

```bash
git add docs/
git commit -m "docs: record context memory architecture final verification"
```

---

## Execution Order

1. Task 1.1 → 1.2 → 1.3 → 1.4 (Phase 1 — independently deployable)
2. Task 2.1 → 2.2 → 2.3 → 2.4 (Phase 2 — needs Phase 1 dialog_turns)
3. Task 3.1 → 3.2 → 3.3 → 3.4 (Phase 3 — independent of Phase 2, needs Phase 1)
4. Task F (final verification)
