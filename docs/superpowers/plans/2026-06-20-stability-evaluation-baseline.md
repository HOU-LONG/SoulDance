# SoulDance Stability Evaluation Baseline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 SQLite + FastAPI + Android 客户端基线上补齐实时协议可追踪性、超时降级、轻量观测和固定 RAG/Agent 评测集。

**Architecture:** 本阶段不改数据库方向，不引入 PostgreSQL、pgvector、Redis、Docker 或图片理解。服务端增加一个轻量 realtime envelope 层统一补 `ack/seq/trace_id/timestamp`，增加 timeout/degradation/observability 小模块包住现有 Agent 链路，并新增 eval runner 使用固定 JSON 场景评测当前 SQLite RAG 与交易闭环。Android 只做协议兼容：能解析 `ack` 和忽略 envelope 元数据，不改变现有聊天、购物车、精灵业务状态。

**Tech Stack:** Python 3.12 + FastAPI + SQLite + SQLAlchemy + pytest + TestClient；Android Kotlin + Jetpack Compose + StateFlow + OkHttp WebSocket + Gradle/JBR。

---

## Scope

This plan implements Milestone C from `docs/superpowers/specs/2026-06-20-shopguide-gap-fill-design.md`, adjusted to the actual current baseline.

Already completed and not repeated here:

- SQLite ORM/data baseline and dependency baseline.
- Android token-confirmed order flow.
- SQLite `product_chunks`, fine-grained chunking, BM25 + JSON embedding + RRF retrieval.
- Existing `/health`, `/api/products`, `/api/cart/*`, `/api/order/*`, `/api/stt`, `/ws/chat`.

Explicitly out of scope:

- PostgreSQL, pgvector, Redis, Docker, container deployment.
- Image upload / visual understanding.
- A/B experimentation and conversion analytics.
- Cross-encoder reranker unless future eval evidence justifies it.
- Breaking changes to existing WebSocket event types.

## Current Baseline Facts

- Remote branch: `feat/postgres-baseline`.
- Latest implemented commits:
  - `09fc7e0 feat(rag): add SQLite product chunk table`
  - `25a0ba5 feat(android): add token-confirmed order flow`
  - `2916757 feat(rag): seed fine-grained SQLite product chunks`
  - `b6c04b1 feat(rag): add SQLite hybrid retrieval with RRF`
  - `ce39df2 test: cover confirmed order flow`
- Backend verification after Milestone B: `259 passed`.
- Android verification after Milestone B: `:app:testDebugUnitTest :app:assembleDebug` passed with:
  - `JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr`
  - `ANDROID_HOME=/home/huadabioa/houlong/android-sdk`
- Current seed smoke: 100 products, 2078 product chunks, chunk types `description/faq/feature/marketing/review/specification`.

## Compatibility Rules

- Keep existing event types compatible: `text_delta`, `product_item`, `products_start`, `products_done`, `cart_update`, `quick_actions`, `done`, `error`, audio/focus/bundle events.
- Additive envelope fields are allowed: `seq`, `trace_id`, `timestamp`, `session_id`.
- New `ack` event is additive and must not block old clients.
- Android must tolerate unknown metadata fields and should not treat `ack` as assistant text.
- Existing `RealtimeEvent.Unknown` fallback must remain.
- Timeout/degradation must return structured events rather than leaving the client waiting.

## File Structure

### Create

| File | Responsibility |
|------|----------------|
| `server/backend/app/realtime_envelope.py` | Per-message event wrapper that emits `ack`, monotonic `seq`, `trace_id`, `timestamp`, and preserves existing payload fields. |
| `server/backend/app/timeout_policy.py` | Named timeout budgets and async helpers for intent, LLM streaming, TTS/STT, and WebSocket request handling. |
| `server/backend/app/degradation.py` | Fixed fallback text/events when LLM, retrieval, or TTS paths fail or time out. |
| `server/backend/app/observability.py` | In-memory counters/timers for local debugging and `/health`/debug output. No Prometheus dependency in this milestone. |
| `server/backend/app/eval/__init__.py` | Eval package exports. |
| `server/backend/app/eval/models.py` | Pydantic models for scenario files and eval results. |
| `server/backend/app/eval/metrics.py` | Recall, hard-constraint violation, product-card presence, and tool-flow metrics. |
| `server/backend/app/eval/runner.py` | Runs fixed scenarios against `create_app(use_fake_llm=True, use_fake_retriever=False)` or a supplied TestClient. |
| `server/scripts/run_eval.py` | CLI entry point for fixed scenario evaluation. |
| `data/eval/shopguide_core_scenarios.json` | Fixed scenario set for RAG + Agent + checkout flow. |
| `server/tests/test_realtime_envelope.py` | Unit tests for envelope metadata and sequence behavior. |
| `server/tests/test_websocket_protocol_envelope.py` | WebSocket integration tests for `ack`, `seq`, `trace_id`, and compatibility. |
| `server/tests/test_timeout_degradation.py` | Timeout and fallback tests with slow/failing fake LLM/TTS/retriever. |
| `server/tests/test_observability.py` | In-memory metrics tests and `/health` integration. |
| `server/tests/test_eval_models.py` | Eval scenario schema tests. |
| `server/tests/test_eval_runner.py` | Eval runner tests using a tiny scenario fixture. |

### Modify

| File | Responsibility |
|------|----------------|
| `server/backend/app/main.py` | Wrap `/ws/chat` outgoing events with envelope; send immediate `ack`; expose metrics in `/health` and optional `/api/debug/metrics`. |
| `server/backend/app/agent.py` | Use degradation helpers around LLM text generation and retrieval boundaries where failures currently bubble into raw websocket errors. |
| `server/backend/app/adaptive_retriever.py` | Record retrieval degradation path and keep fallback behavior explicit. |
| `server/backend/app/llm_client.py` | Keep provider timeout use; do not add API keys; optionally surface timeout class names cleanly. |
| `client/app/src/main/java/com/example/shopguideagent/data/model/RealtimeEvent.kt` | Add `Ack` event and optional metadata container if needed. |
| `client/app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt` | Parse `ack`; ignore `seq/trace_id/timestamp` on existing events. |
| `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt` | Ignore `Ack` safely and leave UI state unchanged except optional connection/status bookkeeping. |
| `client/app/src/test/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClientTest.java` | Cover `ack` parsing and metadata compatibility. |
| `client/app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java` | Cover `Ack` ignored without corrupting assistant message state. |
| `docs/realtime-protocol.md` | Document `ack`, `seq`, `trace_id`, `timestamp`, compatibility rules. |
| `docs/acceptance-tests.md` | Add eval runner and Milestone C acceptance commands. |
| `docs/runbook.md` | Add remote JBR/Android SDK env vars for Gradle verification and eval commands. |

---

## Task C1: Realtime Envelope, Ack, Seq, Trace ID

**Files:**
- Create: `server/backend/app/realtime_envelope.py`
- Modify: `server/backend/app/main.py`
- Create: `server/tests/test_realtime_envelope.py`
- Create: `server/tests/test_websocket_protocol_envelope.py`

**Interface:**

```json
{
  "type": "ack",
  "session_id": "demo",
  "message_id": "msg_xxx",
  "trace_id": "trace_xxx",
  "seq": 0,
  "timestamp": "2026-06-20T14:00:00Z",
  "payload": {"state": "received"}
}
```

Existing outgoing events keep their current top-level fields and additionally receive:

```json
{
  "seq": 1,
  "trace_id": "trace_xxx",
  "timestamp": "2026-06-20T14:00:00Z",
  "session_id": "demo"
}
```

- [ ] **Step 1: Write failing unit test for envelope sequencing**

Create `server/tests/test_realtime_envelope.py`:

```python
from backend.app.realtime_envelope import RealtimeEnvelope


def test_realtime_envelope_adds_ack_and_monotonic_seq():
    envelope = RealtimeEnvelope(session_id="s1", trace_id="trace_test", message_id="m1")

    ack = envelope.ack()
    event = envelope.wrap({"type": "text_delta", "message_id": "m1", "text": "hi"})
    done = envelope.wrap({"type": "done", "message_id": "m1"})

    assert ack["type"] == "ack"
    assert ack["seq"] == 0
    assert event["seq"] == 1
    assert done["seq"] == 2
    assert event["trace_id"] == "trace_test"
    assert event["session_id"] == "s1"
    assert "timestamp" in event
```

- [ ] **Step 2: Run failing test**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_realtime_envelope.py -q
```

Expected: FAIL because `backend.app.realtime_envelope` does not exist.

- [ ] **Step 3: Implement `RealtimeEnvelope`**

Create `server/backend/app/realtime_envelope.py`:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex[:16]}"


def new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:12]}"


@dataclass
class RealtimeEnvelope:
    session_id: str
    trace_id: str = field(default_factory=new_trace_id)
    message_id: str = field(default_factory=new_message_id)
    seq: int = 0

    def ack(self) -> dict[str, Any]:
        return self._with_meta(
            {
                "type": "ack",
                "message_id": self.message_id,
                "payload": {"state": "received"},
            }
        )

    def wrap(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("message_id", self.message_id)
        return self._with_meta(payload)

    def _with_meta(self, event: dict[str, Any]) -> dict[str, Any]:
        event.setdefault("trace_id", self.trace_id)
        event.setdefault("session_id", self.session_id)
        event.setdefault("timestamp", utc_now_iso())
        event["seq"] = self.seq
        self.seq += 1
        return event
```

- [ ] **Step 4: Run unit test**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_realtime_envelope.py -q
```

Expected: PASS.

- [ ] **Step 5: Write failing WebSocket integration test**

Create `server/tests/test_websocket_protocol_envelope.py`:

```python
from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_websocket_sends_ack_before_stream_events_with_trace_and_seq():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": "demo_ws_envelope",
                "message": "推荐防晒霜",
            }
        )
        ack = websocket.receive_json()
        first = websocket.receive_json()

    assert ack["type"] == "ack"
    assert ack["seq"] == 0
    assert first["seq"] == 1
    assert first["trace_id"] == ack["trace_id"]
    assert first["session_id"] == "demo_ws_envelope"
```

- [ ] **Step 6: Run failing WebSocket test**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_websocket_protocol_envelope.py -q
```

Expected: FAIL because `/ws/chat` does not emit `ack`.

- [ ] **Step 7: Integrate envelope in `main.py`**

In `server/backend/app/main.py`, inside `chat_ws`, after validating `ChatRequest`, create envelope and send ack:

```python
from .realtime_envelope import RealtimeEnvelope
```

Inside the receive loop:

```python
payload = await websocket.receive_json()
request = ChatRequest.model_validate(payload)
envelope = RealtimeEnvelope(session_id=request.session_id)
await websocket.send_json(envelope.ack())
```

Wrap every outbound event in that request scope:

```python
await websocket.send_json(envelope.wrap({"type": "cart_update", **event}))
await websocket.send_json(envelope.wrap({"type": "done"}))
```

and:

```python
async for event in agent.stream_message(request, compiled_ir):
    await websocket.send_json(envelope.wrap(event))
```

In the exception handler, if no envelope exists yet, create one from fallback session id when possible, otherwise send legacy error.

- [ ] **Step 8: Run realtime tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_realtime_envelope.py tests/test_websocket_protocol_envelope.py tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add server/backend/app/realtime_envelope.py server/backend/app/main.py \
        server/tests/test_realtime_envelope.py server/tests/test_websocket_protocol_envelope.py
git commit -m "feat(realtime): add ack sequence and trace envelope"
```

---

## Task C2: Android Ack Compatibility

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/model/RealtimeEvent.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
- Modify: `client/app/src/test/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClientTest.java`
- Modify: `client/app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java`

**Interface:**

Add:

```kotlin
data class Ack(
    val messageId: String?,
    val traceId: String?,
    val seq: Int,
) : RealtimeEvent()
```

- [ ] **Step 1: Write failing parser test**

In `RealtimeChatWebSocketClientTest.java`, add:

```java
@Test
public void parseAckEventWithTraceMetadata() throws Exception {
    RealtimeChatWebSocketClient client = new RealtimeChatWebSocketClient();
    Method parseEvent = RealtimeChatWebSocketClient.class.getDeclaredMethod("parseEvent", String.class);
    parseEvent.setAccessible(true);

    RealtimeEvent event = (RealtimeEvent) parseEvent.invoke(
        client,
        "{\"type\":\"ack\",\"message_id\":\"m1\",\"trace_id\":\"trace_1\",\"seq\":0,\"payload\":{\"state\":\"received\"}}"
    );

    assertTrue(event instanceof RealtimeEvent.Ack);
    RealtimeEvent.Ack ack = (RealtimeEvent.Ack) event;
    assertEquals("m1", ack.getMessageId());
    assertEquals("trace_1", ack.getTraceId());
    assertEquals(0, ack.getSeq());
}
```

- [ ] **Step 2: Run failing parser test**

```bash
cd /home/huadabioa/houlong/SoulDance/client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export ANDROID_SDK_ROOT=/home/huadabioa/houlong/android-sdk
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
./gradlew :app:testDebugUnitTest --tests '*RealtimeChatWebSocketClientTest*' --no-daemon
```

Expected: FAIL because `RealtimeEvent.Ack` does not exist.

- [ ] **Step 3: Add `Ack` to `RealtimeEvent.kt`**

```kotlin
data class Ack(
    val messageId: String?,
    val traceId: String?,
    val seq: Int,
) : RealtimeEvent()
```

- [ ] **Step 4: Parse `ack` in WebSocket client**

In `parseEvent()`:

```kotlin
"ack" -> RealtimeEvent.Ack(
    messageId = messageId.takeIf { it.isNotBlank() },
    traceId = json.optString("trace_id").takeIf { it.isNotBlank() },
    seq = json.optInt("seq", 0),
)
```

- [ ] **Step 5: Ignore Ack in ChatViewModel**

In `ChatViewModel.handleRealtimeEvent()`:

```kotlin
is RealtimeEvent.Ack -> Unit
```

- [ ] **Step 6: Add ViewModel regression test**

In `ChatViewModelTest.java`, call private `handleRealtimeEvent` with `Ack` and assert no assistant message is added and no error phase is set.

- [ ] **Step 7: Run Android targeted tests**

```bash
cd /home/huadabioa/houlong/SoulDance/client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export ANDROID_SDK_ROOT=/home/huadabioa/houlong/android-sdk
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
./gradlew :app:testDebugUnitTest --tests '*RealtimeChatWebSocketClientTest*' --tests '*ChatViewModelTest*' --no-daemon
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add client/app/src/main/java/com/example/shopguideagent/data/model/RealtimeEvent.kt \
        client/app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt \
        client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt \
        client/app/src/test/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClientTest.java \
        client/app/src/test/java/com/example/shopguideagent/vm/ChatViewModelTest.java
git commit -m "feat(android): handle realtime ack events"
```

---

## Task C3: Timeout and Degradation Helpers

**Files:**
- Create: `server/backend/app/timeout_policy.py`
- Create: `server/backend/app/degradation.py`
- Modify: `server/backend/app/agent.py`
- Modify: `server/backend/app/adaptive_retriever.py`
- Create: `server/tests/test_timeout_degradation.py`

**Design:**

Keep this milestone small. Do not attempt broad async cancellation of every sync operation. Start with clear boundaries:

- Intent compile timeout returns a clarification/fallback event.
- LLM response stream timeout returns a fixed text fallback after product cards, not a raw error.
- Retrieval exceptions continue to fallback to existing `rank_products(self.products, ...)`.
- TTS failures already return `audio_error`; keep compatible.

- [ ] **Step 1: Write failing timeout unit tests**

Create `server/tests/test_timeout_degradation.py`:

```python
import asyncio

from backend.app.degradation import fallback_text_for_failure
from backend.app.models import HardConstraints, RetrievalPlan
from backend.app.timeout_policy import TimeoutBudget, run_with_timeout


async def _slow():
    await asyncio.sleep(0.2)
    return "done"


def test_run_with_timeout_returns_fallback_on_timeout():
    result = asyncio.run(
        run_with_timeout(_slow(), timeout_seconds=0.01, fallback="fallback")
    )
    assert result == "fallback"


def test_fallback_text_mentions_degraded_state_without_claiming_fake_success():
    plan = RetrievalPlan(
        retrieval_query="防晒",
        hard_constraints=HardConstraints(category="beauty"),
    )
    text = fallback_text_for_failure("llm_timeout", plan)
    assert "暂时" in text
    assert "已下单" not in text
    assert "已加购" not in text
```

- [ ] **Step 2: Run failing tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_timeout_degradation.py -q
```

Expected: FAIL because helper modules do not exist.

- [ ] **Step 3: Implement `timeout_policy.py`**

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class TimeoutBudget:
    intent_seconds: float = 3.0
    retrieval_seconds: float = 2.0
    selection_seconds: float = 4.0
    response_first_chunk_seconds: float = 12.0
    tts_seconds: float = 10.0


async def run_with_timeout(
    awaitable: Awaitable[T],
    timeout_seconds: float,
    fallback: T,
) -> T:
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return fallback
```

- [ ] **Step 4: Implement `degradation.py`**

```python
from __future__ import annotations

from .models import RetrievalPlan


def fallback_text_for_failure(reason: str, plan: RetrievalPlan | None = None) -> str:
    if reason == "llm_timeout":
        return "我已经找到候选商品，但生成详细解释暂时超时了。你可以先查看商品卡片，或者稍后让我继续解释。"
    if reason == "retrieval_error":
        return "检索服务暂时不稳定，我先按当前商品库的基础信息给出保守结果。"
    return "当前服务暂时不稳定，我没有执行任何购物车或订单写操作。请稍后重试。"
```

- [ ] **Step 5: Run helper tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_timeout_degradation.py -q
```

Expected: PASS.

- [ ] **Step 6: Write failing Agent degradation test**

Add to `server/tests/test_timeout_degradation.py`:

```python
from backend.app.agent import ShopGuideAgent
from backend.app.data_loader import load_products
from backend.app.llm_client import FakeLLMClient
from backend.app.models import ChatRequest


class TimeoutStreamLLM(FakeLLMClient):
    async def stream_response(self, user_message, plan, ranked_products, focus_product=None):
        await asyncio.sleep(0.2)
        yield "too late"


def test_agent_stream_returns_fallback_text_when_llm_stream_times_out(monkeypatch):
    products = load_products("ecommerce_agent_dataset")
    agent = ShopGuideAgent(products, TimeoutStreamLLM())
    monkeypatch.setattr("backend.app.agent.DEFAULT_RESPONSE_FIRST_CHUNK_TIMEOUT_SECONDS", 0.01, raising=False)

    events = asyncio.run(
        agent.handle_message(ChatRequest(type="user_message", session_id="timeout_demo", message="推荐防晒霜"))
    )

    texts = [event.get("text", "") for event in events if event.get("type") == "text_delta"]
    assert any("超时" in text or "暂时" in text for text in texts)
    assert events[-1]["type"] in {"done", "audio_done"}
```

Expected before implementation: FAIL or raw timeout/error.

- [ ] **Step 7: Integrate response stream timeout in `agent.py`**

Find `_stream_generate_text_events()` in `server/backend/app/agent.py`. Wrap first chunk retrieval or whole stream with timeout budget. Keep behavior simple:

- If LLM stream starts normally, preserve current streaming behavior.
- If timeout/error happens before any text chunk, emit fallback text from `fallback_text_for_failure("llm_timeout", plan)`.
- Do not fake cart/order success.

- [ ] **Step 8: Make retrieval fallback explicit**

In `AdaptiveRetriever.search()`, when HybridRetriever raises, optionally record an internal reason string but preserve old fallback. Add a small test if there is no current coverage:

```python
def test_hybrid_failure_falls_back_to_base_retriever(...):
    ...
```

- [ ] **Step 9: Run regression tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_timeout_degradation.py tests/test_agent_core.py tests/test_hybrid_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add server/backend/app/timeout_policy.py server/backend/app/degradation.py \
        server/backend/app/agent.py server/backend/app/adaptive_retriever.py \
        server/tests/test_timeout_degradation.py
git commit -m "feat(stability): add timeout degradation fallbacks"
```

---

## Task C4: Lightweight Observability

**Files:**
- Create: `server/backend/app/observability.py`
- Modify: `server/backend/app/main.py`
- Modify: `server/backend/app/realtime_envelope.py`
- Modify: `server/backend/app/adaptive_retriever.py`
- Create: `server/tests/test_observability.py`

**Design:**

Use in-memory counters and timers only. This keeps the milestone deployable in the current vLLM/conda/SQLite remote environment.

Expose in `/health`:

```json
{
  "observability": {
    "counters": {
      "ws.messages.received": 3,
      "ws.events.sent": 25,
      "retrieval.hybrid.success": 2,
      "retrieval.fallback.used": 1
    }
  }
}
```

- [ ] **Step 1: Write failing metrics tests**

Create `server/tests/test_observability.py`:

```python
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.observability import InMemoryMetrics


def test_in_memory_metrics_counts_and_snapshot_are_copy_safe():
    metrics = InMemoryMetrics()
    metrics.increment("ws.messages.received")
    snapshot = metrics.snapshot()
    snapshot["counters"]["ws.messages.received"] = 999

    assert metrics.snapshot()["counters"]["ws.messages.received"] == 1


def test_health_includes_observability_section():
    app = create_app(use_fake_llm=True, use_fake_retriever=True)
    client = TestClient(app)

    body = client.get("/health").json()

    assert "observability" in body
    assert "counters" in body["observability"]
```

- [ ] **Step 2: Run failing tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_observability.py -q
```

Expected: FAIL because module/health section does not exist.

- [ ] **Step 3: Implement `observability.py`**

```python
from __future__ import annotations

from collections import defaultdict
from threading import Lock


class InMemoryMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, int] = defaultdict(int)

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict:
        with self._lock:
            return {"counters": dict(self._counters)}
```

- [ ] **Step 4: Wire metrics into `main.py`**

In `create_app()`:

```python
from .observability import InMemoryMetrics
metrics = InMemoryMetrics()
app.state.metrics = metrics
```

In `/health` response:

```python
"observability": metrics.snapshot(),
```

In websocket receive/send paths:

```python
metrics.increment("ws.messages.received")
metrics.increment("ws.events.sent")
```

- [ ] **Step 5: Add retrieval counters**

In `AdaptiveRetriever.search()`:

- Increment `retrieval.hybrid.success` when hybrid returns results.
- Increment `retrieval.fallback.used` when hybrid fails or returns empty and old logic proceeds.

Pass metrics optionally into `AdaptiveRetriever` only if this does not require broad constructor churn. If constructor churn is too wide, defer retrieval counters and keep WebSocket metrics for this task.

- [ ] **Step 6: Run tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_observability.py tests/test_api.py tests/test_hybrid_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add server/backend/app/observability.py server/backend/app/main.py \
        server/backend/app/realtime_envelope.py server/backend/app/adaptive_retriever.py \
        server/tests/test_observability.py
git commit -m "feat(observability): expose lightweight runtime metrics"
```

---

## Task C5: Fixed Scenario Dataset and Eval Models

**Files:**
- Create: `data/eval/shopguide_core_scenarios.json`
- Create: `server/backend/app/eval/__init__.py`
- Create: `server/backend/app/eval/models.py`
- Create: `server/backend/app/eval/metrics.py`
- Create: `server/tests/test_eval_models.py`
- Create: `server/tests/test_eval_runner.py`

**Scenario schema:**

```json
{
  "id": "clear_budget_sunscreen",
  "message": "推荐一款100元以内的防晒霜，不要含酒精",
  "session_id": "eval_clear_budget_sunscreen",
  "expect": {
    "min_product_items": 1,
    "forbid_terms": ["酒精", "alcohol"],
    "price_max": 100,
    "event_types": ["ack", "assistant_state", "products_start", "product_item", "done"]
  }
}
```

- [ ] **Step 1: Write failing schema tests**

Create `server/tests/test_eval_models.py`:

```python
from backend.app.eval.models import EvalExpectation, EvalScenario


def test_eval_scenario_model_accepts_core_fields():
    scenario = EvalScenario(
        id="budget",
        message="推荐100以内防晒",
        session_id="eval_budget",
        expect=EvalExpectation(min_product_items=1, price_max=100),
    )

    assert scenario.id == "budget"
    assert scenario.expect.price_max == 100
```

- [ ] **Step 2: Run failing schema tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_eval_models.py -q
```

Expected: FAIL because `backend.app.eval` does not exist.

- [ ] **Step 3: Implement eval models**

Create `server/backend/app/eval/models.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class EvalExpectation(BaseModel):
    min_product_items: int = 0
    expected_product_ids: list[str] = Field(default_factory=list)
    forbidden_product_ids: list[str] = Field(default_factory=list)
    forbid_terms: list[str] = Field(default_factory=list)
    price_max: float | None = None
    event_types: list[str] = Field(default_factory=list)
    require_cart_success: bool = False
    require_order_completed: bool = False


class EvalScenario(BaseModel):
    id: str
    message: str
    session_id: str
    type: str = "user_message"
    expect: EvalExpectation = Field(default_factory=EvalExpectation)


class EvalScenarioResult(BaseModel):
    id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    event_count: int = 0
    product_ids: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    total: int
    passed: int
    failed: int
    results: list[EvalScenarioResult]
```

- [ ] **Step 4: Implement metrics helpers**

Create `server/backend/app/eval/metrics.py`:

```python
from __future__ import annotations

from .models import EvalScenario, EvalScenarioResult


def evaluate_events(scenario: EvalScenario, events: list[dict]) -> EvalScenarioResult:
    failures: list[str] = []
    event_types = [event.get("type") for event in events]
    product_events = [event for event in events if event.get("type") == "product_item"]
    product_ids = [
        event.get("product", {}).get("product_id", "")
        for event in product_events
        if isinstance(event.get("product"), dict)
    ]
    if len(product_events) < scenario.expect.min_product_items:
        failures.append(f"expected at least {scenario.expect.min_product_items} product_item events")
    for required in scenario.expect.event_types:
        if required not in event_types:
            failures.append(f"missing event type: {required}")
    for expected_product_id in scenario.expect.expected_product_ids:
        if expected_product_id not in product_ids:
            failures.append(f"missing expected product: {expected_product_id}")
    for forbidden_product_id in scenario.expect.forbidden_product_ids:
        if forbidden_product_id in product_ids:
            failures.append(f"forbidden product returned: {forbidden_product_id}")
    return EvalScenarioResult(
        id=scenario.id,
        passed=not failures,
        failures=failures,
        event_count=len(events),
        product_ids=product_ids,
    )
```

- [ ] **Step 5: Write metrics tests**

Add to `server/tests/test_eval_runner.py`:

```python
from backend.app.eval.metrics import evaluate_events
from backend.app.eval.models import EvalExpectation, EvalScenario


def test_evaluate_events_detects_missing_product_items():
    scenario = EvalScenario(
        id="missing",
        message="推荐防晒",
        session_id="eval_missing",
        expect=EvalExpectation(min_product_items=1, event_types=["ack", "done"]),
    )

    result = evaluate_events(scenario, [{"type": "ack"}, {"type": "done"}])

    assert not result.passed
    assert any("product_item" in failure for failure in result.failures)
```

- [ ] **Step 6: Create fixed scenario dataset**

Create `data/eval/shopguide_core_scenarios.json` with at least these initial cases:

```json
[
  {
    "id": "clear_sunscreen",
    "message": "推荐一款防晒霜",
    "session_id": "eval_clear_sunscreen",
    "expect": {"min_product_items": 1, "event_types": ["ack", "products_start", "product_item", "done"]}
  },
  {
    "id": "budget_under_100",
    "message": "推荐100元以内的防晒霜",
    "session_id": "eval_budget_under_100",
    "expect": {"min_product_items": 1, "price_max": 100}
  },
  {
    "id": "exclude_alcohol",
    "message": "推荐敏感肌可以用的护肤品，不要含酒精",
    "session_id": "eval_exclude_alcohol",
    "expect": {"min_product_items": 1, "forbid_terms": ["酒精", "alcohol"]}
  },
  {
    "id": "cart_add_ui_action",
    "message": "cart_action:add_first_product",
    "session_id": "eval_cart_add",
    "type": "cart_action",
    "expect": {"require_cart_success": true, "event_types": ["ack", "cart_update", "done"]}
  },
  {
    "id": "order_confirm_flow",
    "message": "order_flow:first_product",
    "session_id": "eval_order_flow",
    "type": "order_flow",
    "expect": {"require_order_completed": true}
  }
]
```

Do not overfit expected product ids until the current dataset is inspected and stable. Initial acceptance should focus on event shape and hard-condition violations.

- [ ] **Step 7: Run eval model tests**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_eval_models.py tests/test_eval_runner.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add data/eval/shopguide_core_scenarios.json \
        server/backend/app/eval/__init__.py server/backend/app/eval/models.py \
        server/backend/app/eval/metrics.py \
        server/tests/test_eval_models.py server/tests/test_eval_runner.py
git commit -m "feat(eval): add fixed scenario model and metrics"
```

---

## Task C6: Eval Runner CLI and End-to-End Checks

**Files:**
- Create: `server/backend/app/eval/runner.py`
- Create: `server/scripts/run_eval.py`
- Modify: `server/tests/test_eval_runner.py`

**Design:**

Run scenarios against an in-process FastAPI app. This avoids network flakiness and keeps the eval deterministic for CI/local remote use.

- [ ] **Step 1: Write failing runner test**

Add to `server/tests/test_eval_runner.py`:

```python
from pathlib import Path

from backend.app.eval.runner import load_scenarios, run_scenarios
from backend.app.main import create_app


def test_eval_runner_executes_minimal_websocket_scenario(tmp_path: Path):
    scenario_path = tmp_path / "scenarios.json"
    scenario_path.write_text(
        """
        [
          {
            "id": "smoke",
            "message": "推荐防晒霜",
            "session_id": "eval_smoke",
            "expect": {"min_product_items": 1, "event_types": ["ack", "done"]}
          }
        ]
        """,
        encoding="utf-8",
    )
    app = create_app(use_fake_llm=True, use_fake_retriever=True)

    scenarios = load_scenarios(scenario_path)
    report = run_scenarios(app, scenarios)

    assert report.total == 1
    assert report.passed == 1
```

- [ ] **Step 2: Run failing runner test**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_eval_runner.py -q
```

Expected: FAIL because `runner.py` does not exist.

- [ ] **Step 3: Implement `runner.py`**

Create `server/backend/app/eval/runner.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from .metrics import evaluate_events
from .models import EvalReport, EvalScenario


def load_scenarios(path: str | Path) -> list[EvalScenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalScenario.model_validate(item) for item in data]


def run_scenarios(app: FastAPI, scenarios: list[EvalScenario]) -> EvalReport:
    client = TestClient(app)
    results = []
    for scenario in scenarios:
        if scenario.type == "user_message":
            events = _run_user_message(client, scenario)
            results.append(evaluate_events(scenario, events))
        elif scenario.type == "cart_action":
            events = _run_cart_action(client, scenario)
            results.append(evaluate_events(scenario, events))
        elif scenario.type == "order_flow":
            events = _run_order_flow(client, scenario)
            results.append(evaluate_events(scenario, events))
        else:
            results.append(
                evaluate_events(scenario, [{"type": "error", "message": f"unknown scenario type {scenario.type}"}])
            )
    passed = sum(1 for result in results if result.passed)
    return EvalReport(total=len(results), passed=passed, failed=len(results) - passed, results=results)


def _run_user_message(client: TestClient, scenario: EvalScenario) -> list[dict]:
    events: list[dict] = []
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "user_message",
                "session_id": scenario.session_id,
                "message": scenario.message,
            }
        )
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event.get("type") == "done":
                break
    return events


def _run_cart_action(client: TestClient, scenario: EvalScenario) -> list[dict]:
    product_id = client.get("/api/products").json()["products"][0]["product_id"]
    events: list[dict] = []
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json(
            {
                "type": "cart_action",
                "session_id": scenario.session_id,
                "action": "add_to_cart",
                "product_id": product_id,
                "quantity": 1,
            }
        )
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event.get("type") == "done":
                break
    return events


def _run_order_flow(client: TestClient, scenario: EvalScenario) -> list[dict]:
    product_id = client.get("/api/products").json()["products"][0]["product_id"]
    client.post("/api/cart/clear", json={"session_id": scenario.session_id})
    client.post("/api/cart/add", json={"session_id": scenario.session_id, "product_id": product_id, "quantity": 1})
    initiated = client.post("/api/order/initiate", json={"session_id": scenario.session_id}).json()
    address_id = client.get("/api/order/addresses").json()["addresses"][0]["address_id"]
    selected = client.post(
        "/api/order/select_address",
        json={"order_id": initiated["order_id"], "address_id": address_id},
    ).json()
    confirmed = client.post(
        "/api/order/confirm",
        json={
            "order_id": initiated["order_id"],
            "confirmation_token": selected["confirmation_token"],
            "idempotency_key": f"eval_{scenario.id}",
        },
    ).json()
    return [{"type": "order_flow", "status": confirmed.get("status"), "order_id": confirmed.get("order_id")}]
```

- [ ] **Step 4: Extend `metrics.py` for order/cart expectations**

If `require_order_completed` is true, require an `order_flow` event with `status == "completed"`.

If `require_cart_success` is true, require a `cart_update` event with `success != false`.

- [ ] **Step 5: Implement CLI script**

Create `server/scripts/run_eval.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.eval.runner import load_scenarios, run_scenarios
from backend.app.main import create_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenarios",
        default="../data/eval/shopguide_core_scenarios.json",
    )
    args = parser.parse_args()
    app = create_app(use_fake_llm=True, use_fake_retriever=False)
    report = run_scenarios(app, load_scenarios(Path(args.scenarios)))
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run runner tests and CLI smoke**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_eval_runner.py -q
../env/venv_shopguide_backend/bin/python scripts/run_eval.py --scenarios ../data/eval/shopguide_core_scenarios.json
```

Expected: tests PASS; CLI prints JSON report. Initial scenario set should pass before merging. If a scenario fails because the dataset lacks matching product facts, fix the scenario expectation rather than weakening production constraints.

- [ ] **Step 7: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add server/backend/app/eval/runner.py server/scripts/run_eval.py \
        server/backend/app/eval/metrics.py server/tests/test_eval_runner.py
git commit -m "feat(eval): add scenario runner CLI"
```

---

## Task C7: Documentation and Full Verification

**Files:**
- Modify: `docs/realtime-protocol.md`
- Modify: `docs/acceptance-tests.md`
- Modify: `docs/runbook.md`

- [ ] **Step 1: Update realtime protocol docs**

Document:

- `ack` event.
- `seq` starts at `0` per received client message.
- `trace_id` is stable for all events produced from one client message.
- `message_id` still groups UI messages.
- Existing event types remain compatible.

- [ ] **Step 2: Update acceptance tests**

Add commands:

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest -q
../env/venv_shopguide_backend/bin/python scripts/run_eval.py --scenarios ../data/eval/shopguide_core_scenarios.json
```

Android:

```bash
cd /home/huadabioa/houlong/SoulDance/client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export ANDROID_SDK_ROOT=/home/huadabioa/houlong/android-sdk
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
./gradlew :app:testDebugUnitTest :app:assembleDebug --no-daemon
```

- [ ] **Step 3: Update runbook**

Add the remote Java/SDK requirement explicitly because default Java is 11 and Gradle requires 17+.

- [ ] **Step 4: Run full backend verification**

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest -q
../env/venv_shopguide_backend/bin/python -m backend.app.db.seed
../env/venv_shopguide_backend/bin/python scripts/run_eval.py --scenarios ../data/eval/shopguide_core_scenarios.json
```

Expected: pytest PASS; seed reports 100 products and chunk count > product count; eval report failed count is 0.

- [ ] **Step 5: Run Android verification**

```bash
cd /home/huadabioa/houlong/SoulDance/client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export ANDROID_SDK_ROOT=/home/huadabioa/houlong/android-sdk
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
./gradlew :app:testDebugUnitTest :app:assembleDebug --no-daemon
```

Expected: BUILD SUCCESSFUL. APK remains:

```text
/home/huadabioa/houlong/SoulDance/client/app/build/outputs/apk/debug/app-debug.apk
```

- [ ] **Step 6: Commit docs**

```bash
cd /home/huadabioa/houlong/SoulDance
git add docs/realtime-protocol.md docs/acceptance-tests.md docs/runbook.md
git commit -m "docs: document stability evaluation baseline"
```

- [ ] **Step 7: Push branch**

```bash
cd /home/huadabioa/houlong/SoulDance
git status -sb
git push origin feat/postgres-baseline
```

---

## Final Acceptance Criteria

- `/ws/chat` sends `ack` immediately after receiving a valid message.
- Every server event emitted for one client message has monotonic `seq`, stable `trace_id`, and `timestamp`.
- Android parses `ack` and ignores it without corrupting chat UI state.
- LLM stream timeout returns a fixed fallback text event instead of leaving the client waiting.
- Retrieval failure still falls back to existing deterministic candidate ranking.
- `/health` includes lightweight in-memory observability counters.
- `data/eval/shopguide_core_scenarios.json` exists and is executable through `server/scripts/run_eval.py`.
- Backend full test suite passes.
- Android unit tests and APK build pass with remote JBR/SDK environment variables.

## Execution Order

1. C1 realtime envelope.
2. C2 Android ack compatibility.
3. C3 timeout/degradation.
4. C4 observability.
5. C5 eval dataset/models.
6. C6 eval runner CLI.
7. C7 docs and full verification.

This order is intentional: eval scenarios should validate the final protocol shape, so `ack/seq/trace_id` must land before the eval runner.

## Notes for Implementers

- Use @superpowers:test-driven-development for each task.
- Use @superpowers:executing-plans if implementing in a single current session.
- Use @superpowers:subagent-driven-development only if the harness/user permits subagents.
- Keep commits small and push only after full verification.
- Do not weaken hard constraints to make eval pass. Fix data/scenario expectations or retrieval logic instead.
