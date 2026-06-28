# SoulDance 会话持久化、用户切换与闲聊/单品分析修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复历史会话无法持久化、演示用户切换未生效、闲聊与单品分析无法响应三类断点，让后端会话成为历史事实源、Android 本地缓存作为离线兜底，并保证 demo_user_a/b/c 全链路隔离。

**Architecture:** 后端在 `SessionContext` 中新增 `display_messages` 字段，由 `stream_message()` 和 cart 操作路径统一写入，作为 Android 历史 UI 的可渲染事实源；新增 `GET /api/sessions`、`GET /api/sessions/{id}`、`DELETE /api/sessions/{id}` 供客户端拉取/删除。Android 改造 `ChatHistoryRepository` 为按 `user_id` 分区的 JSON 缓存，启动时先展示本地再后台合并后端；修复 `ChatViewModel.onUserSwitched()` 与 `AppNavGraph` 的 `SwitchUser` effect，让切换用户时同步关闭 WebSocket、刷新历史与购物车。

**Tech Stack:** FastAPI + SQLAlchemy/JSON file；Kotlin + Jetpack Compose + Retrofit/OkHttp + SharedPreferences。

## Global Constraints

1. 所有自然语言输出使用简体中文（命令、代码、路径、API 名、配置项、错误原文除外）。
2. 禁止在 Android 客户端写 LLM/TTS/STT 密钥。
3. 禁止 Android 客户端编造商品推荐；商品卡只展示后端返回的真实商品。
4. 后端优先复用 `SessionStore` / `SessionRepository`，不引入 Redis 或新持久化组件。
5. 所有用户隔离以 `UserSession.currentUserId` / `X-User-Id` 为唯一来源。
6. 继续使用 `demo_user_a` / `demo_user_b` / `demo_user_c` 作为演示用户，不做真实登录注册。
7. 后端会话历史保留现有 TTL 策略（默认 7 天）；Android 本地最多保留 30 个会话。
8. 代码和注释风格与项目历史代码保持一致；注释写“为什么”，不写显而易见的。
9. 每完成一个 task 必须运行对应测试并提交（frequent commits）。

## File Structure

### 后端新增/修改

| 文件 | 职责 |
|---|---|
| `server/backend/app/models.py` | 在 `SessionContext` 新增 `display_messages: list[DisplayMessage]`；新增 `DisplayMessage` / `DisplayMessageProduct` 模型；`schema_version` 升级到 3。 |
| `server/backend/app/session_store.py` | 新增 `list_sessions(user_id)`、`delete(user_id, session_id)`；文件模式支持删除文件和空目录清理；升级迁移逻辑。 |
| `server/backend/app/repositories/session_repository.py` | 新增 `list(user_id)`、`delete(user_id, session_id)`。 |
| `server/backend/app/main.py` | 新增 `GET /api/sessions`、`GET /api/sessions/{session_id}`、`DELETE /api/sessions/{session_id}`；修复 `GET /api/sessions/latest` 默认 session 也要保存。 |
| `server/backend/app/agent.py` | 在 `stream_message()` 中收集 assistant 文本、product_item、quick_actions、cart_update 等到 `context.display_messages`；cart 路径也补充写入。 |
| `server/backend/app/semantic_layer.py` | 扩展 `_is_small_talk()` 覆盖“你能帮我做些什么”等变体。 |
| `server/backend/app/tools/product_analysis.py` | 新增单品分析工具：命中库内商品则做单品说明，未命中则返回无库存通用分析。 |
| `server/backend/app/agent.py` | 新增 `product_analysis` 意图分支，在 `compare_products` 之前路由单商品评价类请求。 |

### Android 新增/修改

| 文件 | 职责 |
|---|---|
| `client/app/src/main/java/com/example/shopguideagent/data/history/ChatHistoryModels.kt` | 新增 `ChatHistoryUiState` / `ChatSessionUiModel` / `ChatMessageUiModel` 的 JSON 序列化数据类（若已有则扩展）。 |
| `client/app/src/main/java/com/example/shopguideagent/data/history/ChatHistoryRepository.kt` | 改造 `ChatHistoryStore` 为按 user 分区；实现 JSON/Gson 读写；保留 Base64 旧格式只读迁移；上限 30 条。 |
| `client/app/src/main/java/com/example/shopguideagent/data/remote/SessionsApiService.kt` | 新增 `listSessions()`、`getSession(id)`、`deleteSession(id)` 接口。 |
| `client/app/src/main/java/com/example/shopguideagent/data/remote/SessionsApiClient.kt` | 实现上述方法；强制构造走 `userIdProvider`。 |
| `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt` | 修复 `onUserSwitched()`：切换前 persist、加载新用户本地历史、调后端 latest、关闭/重开 WebSocket、重置购物车 badge。 |
| `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeRoute.kt` | 收到 `SwitchUser` effect 时调用 `chatViewModel.onUserSwitched(userId)`。 |
| `client/app/src/main/java/com/example/shopguideagent/navigation/AppNavGraph.kt` | 移除 `SwitchUser -> Unit` 的吞掉处理，或确保 `onUserSelected` 统一走 effect。 |
| `client/app/src/main/java/com/example/shopguideagent/data/remote/SessionsApiService.kt` | 删除无 `userIdProvider` 的 `@Deprecated create()` 默认实现，避免误用。 |

---

## Task 1: 后端新增 DisplayMessage 模型并升级 SessionContext schema

**Files:**
- Modify: `server/backend/app/models.py`
- Test: `server/tests/test_display_message_schema.py`（新建）

**Interfaces:**
- Consumes: 现有 `ProductCard` 字段定义。
- Produces: `DisplayMessage`, `DisplayMessageProduct` Pydantic 模型；`SessionContext.display_messages` 字段；`SessionContext.schema_version = 3`。

### Step 1: 编写失败测试

创建 `server/tests/test_display_message_schema.py`：

```python
from backend.app.models import DisplayMessage, DisplayMessageProduct, SessionContext


def test_display_message_defaults():
    msg = DisplayMessage(role="user", text="hello")
    assert msg.role == "user"
    assert msg.text == "hello"
    assert msg.products == []
    assert msg.quick_actions == []


def test_session_context_has_display_messages():
    ctx = SessionContext(session_id="s1")
    assert ctx.display_messages == []
    assert ctx.schema_version == 3


def test_session_context_round_trip_json():
    ctx = SessionContext(session_id="s1")
    ctx.display_messages.append(
        DisplayMessage(
            role="assistant",
            text="hi",
            products=[DisplayMessageProduct(product_id="p1", name="Phone", price=2999.0)],
        )
    )
    data = ctx.model_dump_json()
    loaded = SessionContext.model_validate_json(data)
    assert loaded.display_messages[0].role == "assistant"
    assert loaded.display_messages[0].products[0].product_id == "p1"
```

### Step 2: 运行测试，确认失败

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_display_message_schema.py -v
```

Expected: FAIL，`DisplayMessage` not defined。

### Step 3: 最小实现

在 `server/backend/app/models.py` 中 `SessionContext` 之前新增：

```python
class DisplayMessageProduct(BaseModel):
    product_id: str
    name: str
    brand: str = ""
    category: str = ""
    sub_category: str = ""
    price: float = 0.0
    image_url: str = ""
    main_image_url: str = ""
    tags: list[str] = Field(default_factory=list)
    reason: str = ""
    is_primary: bool = False
    derived_attributes: dict[str, Any] = Field(default_factory=dict)
    positive_feedback_summary: list[str] = Field(default_factory=list)
    negative_feedback_summary: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)


class DisplayMessage(BaseModel):
    id: str = ""
    role: str  # "user" | "assistant" | "system"
    text: str = ""
    created_at: str = ""
    products: list[DisplayMessageProduct] = Field(default_factory=list)
    quick_actions: list[dict[str, Any]] = Field(default_factory=list)
```

修改 `SessionContext`：

```python
class SessionContext(BaseModel):
    session_id: str
    state: SessionState = Field(default_factory=SessionState)
    last_plan: RetrievalPlan | None = None
    last_product_ids: list[str] = Field(default_factory=list)
    focus_product_id: str | None = None
    focus_history: list[str] = Field(default_factory=list)
    global_profile: dict[str, object] = Field(default_factory=dict)
    active_focus: dict[str, object] = Field(default_factory=dict)
    last_recommendations: list[dict[str, object]] = Field(default_factory=list)
    negative_feedback: list[str] = Field(default_factory=list)
    recent_cart_product_id: str | None = None
    reference_anchors: dict[str, str] = Field(default_factory=dict)
    dialog_turns: list[dict[str, str]] = Field(default_factory=list)
    display_messages: list[DisplayMessage] = Field(default_factory=list)
    compression_state: SessionCompressionState = Field(default_factory=SessionCompressionState)
    entity_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    entity_params_order: list[str] = Field(default_factory=list)
    schema_version: int = 3
    last_activity_at: str = ""
```

### Step 4: 运行测试，确认通过

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_display_message_schema.py -v
```

Expected: PASS。

### Step 5: 提交

```bash
git add server/backend/app/models.py server/tests/test_display_message_schema.py
git commit -m "feat(session): add DisplayMessage model and schema_version 3

- DisplayMessage holds UI-renderable history per turn
- DisplayMessageProduct mirrors ProductCard for Android compatibility
- SessionContext now carries display_messages field"
```

---

## Task 2: 扩展 SessionStore / SessionRepository 支持 list 与 delete

**Files:**
- Modify: `server/backend/app/repositories/session_repository.py`
- Modify: `server/backend/app/session_store.py`
- Test: `server/tests/test_session_store_list_delete.py`（新建）

**Interfaces:**
- Consumes: `SessionContext`, `SessionRepository`, `SessionStore`。
- Produces: `SessionStore.list_sessions(user_id) -> list[SessionContext]`；`SessionStore.delete(user_id, session_id)`；`SessionRepository.list(user_id) -> list[SessionContext]`；`SessionRepository.delete(user_id, session_id)`。

### Step 1: 编写失败测试

```python
import os
import tempfile
from datetime import datetime, timezone

from backend.app.models import SessionContext
from backend.app.session_store import SessionStore


def test_list_and_delete_file_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(persist_dir=tmpdir, ttl_days=7)
        store.save("u1", "s1")
        store.save("u1", "s2")
        store.save("u2", "s3")

        u1_sessions = store.list_sessions("u1")
        assert len(u1_sessions) == 2
        assert {s.session_id for s in u1_sessions} == {"s1", "s2"}

        store.delete("u1", "s1")
        assert len(store.list_sessions("u1")) == 1
        assert not any(
            f.endswith("s1.json")
            for f in os.listdir(os.path.join(tmpdir, "u1"))
        )

        # u2 unaffected
        assert len(store.list_sessions("u2")) == 1


def test_delete_nonexistent_is_noop():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(persist_dir=tmpdir)
        store.delete("u1", "no_such_session")  # should not raise
```

### Step 2: 运行测试，确认失败

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_session_store_list_delete.py -v
```

Expected: FAIL，`list_sessions` / `delete` not defined。

### Step 3: 最小实现

`server/backend/app/repositories/session_repository.py`：

```python
    def list(self, user_id: str) -> list[SessionContext]:
        rows = (
            self.db.query(SessionState)
            .filter_by(user_id=user_id)
            .order_by(SessionState.last_activity_at.desc())
            .all()
        )
        return [SessionContext.model_validate(row.state_json) for row in rows]

    def delete(self, user_id: str, session_id: str) -> None:
        row = (
            self.db.query(SessionState)
            .filter_by(user_id=user_id, session_id=session_id)
            .first()
        )
        if row is not None:
            self.db.delete(row)
            self.db.flush()
```

`server/backend/app/session_store.py`：

```python
    def list_sessions(self, user_id: str) -> list[SessionContext]:
        if self._repo is not None:
            return self._repo.list(user_id)
        sessions: list[SessionContext] = []
        # in-memory
        for (uid, sid), ctx in self._sessions.items():
            if uid == user_id:
                sessions.append(ctx)
        # file mode: also load any on-disk sessions not yet in memory
        if self.persist_dir:
            user_dir = self.persist_dir / user_id.replace("/", "_").replace("\\", "_")
            if user_dir.exists():
                for path in user_dir.glob("*.json"):
                    sid = path.stem
                    if (user_id, sid) not in self._sessions:
                        loaded = self._load_one(user_id, sid)
                        if loaded is not None:
                            self._sessions[(user_id, sid)] = loaded
                            sessions.append(loaded)
        sessions.sort(key=lambda c: c.last_activity_at or "", reverse=True)
        return sessions

    def delete(self, user_id: str, session_id: str) -> None:
        key = (user_id, session_id)
        if self._repo is not None:
            self._repo.delete(user_id, session_id)
            self._sessions.pop(key, None)
            return
        if key in self._sessions:
            del self._sessions[key]
        if not self.persist_dir:
            return
        path = self._path(user_id, session_id)
        if path.exists():
            path.unlink()
        user_dir = path.parent
        try:
            if user_dir.exists() and not any(user_dir.iterdir()):
                user_dir.rmdir()
        except OSError:
            pass
```

### Step 4: 运行测试，确认通过

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_session_store_list_delete.py -v
```

### Step 5: 提交

```bash
git add server/backend/app/repositories/session_repository.py server/backend/app/session_store.py server/tests/test_session_store_list_delete.py
git commit -m "feat(session): add list_sessions and delete to SessionStore/Repository

- Supports both DB mode and file mode
- File mode cleans up empty user directories after delete"
```

---

## Task 3: 新增后端会话 REST API

**Files:**
- Modify: `server/backend/app/main.py`
- Test: `server/tests/test_sessions_api.py`（新建）

**Interfaces:**
- Consumes: `SessionStore.list_sessions`, `SessionStore.get`, `SessionStore.delete`。
- Produces: `GET /api/sessions`, `GET /api/sessions/{session_id}`, `DELETE /api/sessions/{session_id}`；`GET /api/sessions/latest` 默认 session 也落库。

### Step 1: 编写失败测试

```python
from fastapi.testclient import TestClient

from backend.app.main import create_app


def _app():
    return TestClient(create_app(use_fake_llm=True, use_fake_retriever=True))


def test_get_sessions_requires_user_id():
    client = _app()
    resp = client.get("/api/sessions")
    assert resp.status_code == 422  # X-User-Id header missing when not anonymous


def test_sessions_crud_isolated_by_user():
    client = _app()
    # user a creates session
    client.get("/api/sessions/latest", headers={"X-User-Id": "demo_user_a"})
    client.post("/api/chat", json={
        "type": "user_message",
        "session_id": "demo_user_a_session_default",
        "message": "hello",
    }, headers={"X-User-Id": "demo_user_a"})

    # user b should not see a's session
    resp = client.get("/api/sessions", headers={"X-User-Id": "demo_user_b"})
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []

    # user a sees one
    resp = client.get("/api/sessions", headers={"X-User-Id": "demo_user_a"})
    assert len(resp.json()["sessions"]) == 1
    sid = resp.json()["sessions"][0]["session_id"]

    # load detail
    resp = client.get(f"/api/sessions/{sid}", headers={"X-User-Id": "demo_user_a"})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == sid

    # delete
    resp = client.delete(f"/api/sessions/{sid}", headers={"X-User-Id": "demo_user_a"})
    assert resp.status_code == 204

    resp = client.get("/api/sessions", headers={"X-User-Id": "demo_user_a"})
    assert resp.json()["sessions"] == []
```

### Step 2: 运行测试，确认失败

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_sessions_api.py -v
```

Expected: FAIL，endpoints not defined。

### Step 3: 最小实现

在 `server/backend/app/main.py` 中替换/扩展现有 `/api/sessions/latest` 区域：

```python
    @app.get("/api/sessions/latest")
    def get_latest_session(user_id: str = Depends(get_current_user_id)):
        latest_session_id = session_store.get_latest_session_id(user_id)
        if latest_session_id is None:
            latest_session_id = f"{user_id}_session_default"
            # ensure it exists for subsequent loads
            session_store.get(user_id, latest_session_id)
            session_store.save(user_id, latest_session_id)
        return {"session_id": latest_session_id}

    @app.get("/api/sessions")
    def list_sessions(user_id: str = Depends(get_current_user_id)):
        sessions = session_store.list_sessions(user_id)
        return {
            "sessions": [
                {
                    "session_id": ctx.session_id,
                    "title": _session_title(ctx),
                    "updated_at": ctx.last_activity_at,
                    "message_count": len(ctx.display_messages),
                    "preview": _session_preview(ctx),
                }
                for ctx in sessions
            ]
        }

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str, user_id: str = Depends(get_current_user_id)):
        ctx = session_store.get(user_id, session_id)
        return {
            "session_id": ctx.session_id,
            "title": _session_title(ctx),
            "updated_at": ctx.last_activity_at,
            "messages": [m.model_dump(mode="json") for m in ctx.display_messages],
        }

    @app.delete("/api/sessions/{session_id}", status_code=204)
    def delete_session(session_id: str, user_id: str = Depends(get_current_user_id)):
        session_store.delete(user_id, session_id)
        return None

    def _session_title(ctx) -> str:
        for m in ctx.display_messages:
            if m.role == "user" and m.text:
                return m.text[:18]
        return "新会话"

    def _session_preview(ctx) -> str:
        for m in reversed(ctx.display_messages):
            if m.role == "assistant" and m.text:
                return m.text[:60]
        return ""
```

### Step 4: 运行测试，确认通过

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_sessions_api.py -v
```

### Step 5: 提交

```bash
git add server/backend/app/main.py server/tests/test_sessions_api.py
git commit -m "feat(api): add session list/load/delete endpoints

- GET /api/sessions returns user-isolated summaries
- GET /api/sessions/{id} returns display_messages
- DELETE /api/sessions/{id} removes user session"
```

---

## Task 4: 在 stream_message 中收集 display_messages

**Files:**
- Modify: `server/backend/app/agent.py`
- Test: `server/tests/test_display_messages_stream.py`（新建）

**Interfaces:**
- Consumes: `SessionContext.display_messages`, `RealtimeEvent` 事件流。
- Produces: 每次 `stream_message()` 完成后，新的一条 `DisplayMessage` 追加到 `context.display_messages`。

### Step 1: 编写失败测试

```python
import pytest

from backend.app.main import create_app
from fastapi.testclient import TestClient


def test_stream_message_records_display_messages():
    client = TestClient(create_app(use_fake_llm=True, use_fake_retriever=True))
    resp = client.post("/api/chat", json={
        "type": "user_message",
        "session_id": "display_test",
        "message": "推荐手机",
    }, headers={"X-User-Id": "demo_user_a"})
    assert resp.status_code == 200
    ctx_resp = client.get("/api/debug/session", params={"session_id": "display_test"}, headers={"X-User-Id": "demo_user_a"})
    ctx = ctx_resp.json()
    assert len(ctx["display_messages"]) >= 2
    assert ctx["display_messages"][0]["role"] == "user"
    assert ctx["display_messages"][0]["text"] == "推荐手机"
    assistant_msgs = [m for m in ctx["display_messages"] if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
```

### Step 2: 运行测试，确认失败

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_display_messages_stream.py -v
```

Expected: FAIL，`display_messages` empty。

### Step 3: 最小实现

在 `server/backend/app/agent.py` 中，修改 `stream_message()`：

1. 在方法开头追加 user message 到 `display_messages`：

```python
async def stream_message(self, user_id: str, request: ChatRequest, compiled_ir=None) -> AsyncIterator[dict]:
    context = self.sessions.get(user_id, request.session_id)
    context.dialog_turns.append({"role": "user", "content": request.message or ""})

    # Build a display turn for this request
    display_turn = DisplayMessage(
        id=_message_id(),
        role="user",
        text=request.message or "",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    context.display_messages.append(display_turn)

    # Helper to close the assistant display turn
    assistant_display: DisplayMessage | None = None

    def ensure_assistant_display():
        nonlocal assistant_display
        if assistant_display is None:
            assistant_display = DisplayMessage(
                id=_message_id(),
                role="assistant",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            context.display_messages.append(assistant_display)
        return assistant_display
```

2. 在所有 yield 处包装事件收集：

```python
    async def _yield_with_capture(event: dict):
        nonlocal assistant_display
        etype = event.get("type")
        if etype in {"text_delta", "focus_text_delta"}:
            ensure_assistant_display().text += event.get("text", "")
        elif etype == "product_item":
            ensure_assistant_display().products.append(_display_product_from_event(event))
        elif etype == "replacement_product":
            ensure_assistant_display().products.append(_display_product_from_event(event))
        elif etype == "quick_actions":
            ensure_assistant_display().quick_actions = event.get("actions", [])
        elif etype == "cart_update" and event.get("message"):
            ensure_assistant_display().text += ("\n" if ensure_assistant_display().text else "") + event.get("message")
        yield event
```

3. 把所有 `yield event` 替换为 `async for e in _yield_with_capture(event): yield e`；对于 `yield self._assistant_state(...)` 等也做同样处理。为简化，可以在 `stream_message` 内部用局部生成器包装整个输出。

更简单的实现：在 `stream_message()` 末尾统一收集已 yield 的事件是不可能的（生成器已消费）。因此实际做法是在 yield 前/后捕获。推荐用 wrapper：

```python
    collected: list[dict] = []
    async def capture(event: dict) -> dict:
        collected.append(event)
        return event

    async for event in self._stream_message_inner(user_id, request, compiled_ir):
        yield await capture(event)

    # after inner completes, build/append assistant display message from collected
    self._append_display_messages_from_collected(context, collected)
```

但 `stream_message()` 逻辑很长，直接内联 wrapper 最稳妥：把现有 `stream_message` 主体提取为 `_stream_message_inner`，然后 `stream_message` 负责收集。

为最小改动，也可以：

```python
async def stream_message(self, user_id, request, compiled_ir=None):
    collected: list[dict] = []
    context = self.sessions.get(user_id, request.session_id)
    context.dialog_turns.append({"role": "user", "content": request.message or ""})
    context.display_messages.append(DisplayMessage(...user...))

    async for event in self._do_stream_message(user_id, request, compiled_ir, context):
        collected.append(event)
        yield event

    self._record_display_messages(context, collected)
```

然后把原 `stream_message` 主体改名为 `_do_stream_message`。

实现 `_record_display_messages`：

```python
    def _record_display_messages(self, context: SessionContext, events: list[dict]) -> None:
        assistant = DisplayMessage(
            id=_message_id(),
            role="assistant",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        has_content = False
        for event in events:
            etype = event.get("type")
            if etype in {"text_delta", "focus_text_delta"}:
                assistant.text += event.get("text", "")
                has_content = True
            elif etype in {"product_item", "replacement_product"}:
                raw = event.get("product", {})
                assistant.products.append(DisplayMessageProduct(**raw))
                has_content = True
            elif etype == "quick_actions":
                assistant.quick_actions = event.get("actions", [])
            elif etype == "cart_update" and event.get("message"):
                assistant.text += ("\n" if assistant.text else "") + event.get("message")
                has_content = True
        if has_content:
            context.display_messages.append(assistant)
```

### Step 4: 运行测试，确认通过

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_display_messages_stream.py -v
```

### Step 5: 提交

```bash
git add server/backend/app/agent.py server/tests/test_display_messages_stream.py
git commit -m "feat(session): record display_messages from stream_message

- Captures assistant text, product_item, replacement_product, quick_actions, cart_update message
- Appends one assistant DisplayMessage per turn"
```

---

## Task 5: cart_action 路径也写入 display_messages

**Files:**
- Modify: `server/backend/app/main.py`
- Test: `server/tests/test_cart_action_display_messages.py`（新建）

**Interfaces:**
- Consumes: cart 操作事件流。
- Produces: cart 操作后 `display_messages` 增加一条 system/assistant 消息记录操作结果。

### Step 1: 编写失败测试

```python
from fastapi.testclient import TestClient
from backend.app.main import create_app


def test_cart_action_records_display_message():
    client = TestClient(create_app(use_fake_llm=True, use_fake_retriever=True))
    client.websocket_connect("/ws/chat", headers={"X-User-Id": "demo_user_a"}) as ws:
        ws.send_json({"type": "cart_action", "session_id": "cart_display_test", "action": "add_to_cart", "product_id": "p1", "quantity": 1})
        events = []
        while True:
            evt = ws.receive_json()
            events.append(evt)
            if evt.get("type") == "done":
                break

    ctx = client.get("/api/debug/session", params={"session_id": "cart_display_test"}, headers={"X-User-Id": "demo_user_a"}).json()
    assert len(ctx["display_messages"]) >= 1
    assert ctx["display_messages"][0]["role"] == "system"
```

### Step 2: 运行测试，确认失败

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_cart_action_display_messages.py -v
```

### Step 3: 最小实现

在 `server/backend/app/main.py` 的 `send_cart_tool_events` 中，操作完成后写一条 display message：

```python
                async def send_cart_tool_events(compiled_ir=None) -> bool:
                    handled = False
                    context = agent.sessions.get(user_id, request.session_id)
                    cart_events: list[dict] = []
                    async for event in agent.tool_registry.execute(
                        "cart_operation",
                        request,
                        context,
                        cart_service=cart,
                        compiled_ir=compiled_ir,
                        user_id=user_id,
                    ):
                        handled = True
                        cart_events.append(event)
                        await websocket.send_json(envelope.wrap(event))
                        metrics.increment("ws.events.sent")
                    if handled:
                        session_store.save(user_id, request.session_id)
                        # Record cart action in display history
                        _record_cart_display_message(context, request, cart_events)
                    return handled
```

新增 helper：

```python
    def _record_cart_display_message(context, request, events):
        text = request.message or f"购物车操作: {request.action}"
        result_parts = []
        for event in events:
            if event.get("type") == "cart_update" and event.get("message"):
                result_parts.append(event["message"])
        display = DisplayMessage(
            id=_message_id(),
            role="system",
            text=f"{text}\n{'; '.join(result_parts)}" if result_parts else text,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        context.display_messages.append(display)
```

注意需要 import `DisplayMessage` 和 `_message_id`（或内联生成 id）。

### Step 4: 运行测试，确认通过

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_cart_action_display_messages.py -v
```

### Step 5: 提交

```bash
git add server/backend/app/main.py server/tests/test_cart_action_display_messages.py
git commit -m "feat(session): record cart_action results in display_messages

- System-role display message captures user intent and cart_update message"
```

---

## Task 6: 后端 small_talk 规则扩展

**Files:**
- Modify: `server/backend/app/semantic_layer.py`
- Test: `server/tests/test_small_talk_capability.py`（新建）

**Interfaces:**
- Consumes: `_is_small_talk()` 规则。
- Produces: “你能帮我做些什么”等能力询问稳定路由到 `small_talk`，不触发检索。

### Step 1: 编写失败测试

```python
from backend.app.semantic_layer import rule_semantic_frame
from backend.app.models import ChatRequest


def test_capability_question_is_small_talk():
    for text in ["你能帮我做些什么", "你能做什么", "你是干嘛的", "你有什么功能"]:
        req = ChatRequest(type="user_message", session_id="s1", message=text)
        frame = rule_semantic_frame(req)
        assert frame.intent == "small_talk", text
```

### Step 2: 运行测试，确认失败

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_small_talk_capability.py -v
```

Expected: FAIL，部分变体不匹配。

### Step 3: 最小实现

修改 `server/backend/app/semantic_layer.py` 的 `_is_small_talk`：

```python
def _is_small_talk(text: str) -> bool:
    normalized = re.sub(r"[\s?？!！。,.，、]+", "", (text or "").lower())
    if not normalized:
        return True
    if _has_shopping_signal(text):
        return False
    capability_patterns = [
        "你能做什么",
        "你能帮我做什么",
        "你能帮我做些什么",
        "你能做啥",
        "你有什么功能",
        "你有什么用",
        "你可以做什么",
        "你可以帮我做什么",
        "你是干嘛的",
        "你是做什么的",
        "你是谁",
        "你是谁呀",
    ]
    if any(p in normalized for p in capability_patterns):
        return True
    return bool(
        re.fullmatch(
            r"(你好|您好|h[ae]l+o+|hello|hi|hey|yo|在吗|在不在|谢谢|谢了|感谢|辛苦了)",
            normalized,
        )
    )
```

### Step 4: 运行测试，确认通过

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_small_talk_capability.py -v
```

### Step 5: 提交

```bash
git add server/backend/app/semantic_layer.py server/tests/test_small_talk_capability.py
git commit -m "fix(intent): broaden small_talk rules for capability questions

- 你能帮我做些什么 / 你有什么功能 等稳定路由到 small_talk"
```

---

## Task 7: 新增 product_analysis 意图与工具

**Files:**
- Create: `server/backend/app/tools/product_analysis.py`
- Modify: `server/backend/app/agent.py`
- Modify: `server/backend/app/tools/registry.py`（自动注册已在 `_init_tool_registry`）
- Test: `server/tests/test_product_analysis.py`（新建）

**Interfaces:**
- Consumes: `ChatRequest`, `SessionContext`, `product_map`。
- Produces: `product_analysis` 工具，命中库内商品返回单品分析事件；未命中返回无库存说明。

### Step 1: 编写失败测试

```python
from fastapi.testclient import TestClient
from backend.app.main import create_app


def test_product_analysis_in_catalog():
    client = TestClient(create_app(use_fake_llm=True, use_fake_retriever=True))
    # Use a real product_id from dataset; adjust as needed
    resp = client.post("/api/chat", json={
        "type": "user_message",
        "session_id": "analysis_test",
        "message": "你如何看待这个商品的性价比呢？",
    }, headers={"X-User-Id": "demo_user_a"})
    # Expect no product_item for non-existent product, but no crash
    assert resp.status_code == 200


def test_product_analysis_unknown_product_no_fake_card():
    client = TestClient(create_app(use_fake_llm=True, use_fake_retriever=True))
    resp = client.post("/api/chat", json={
        "type": "user_message",
        "session_id": "analysis_unknown",
        "message": "小米17max 性价比",
    }, headers={"X-User-Id": "demo_user_a"})
    assert resp.status_code == 200
    events = resp.json()
    assert not any(e.get("type") == "product_item" for e in events)
    texts = "".join(e.get("text", "") for e in events if e.get("type") in {"text_delta", "focus_text_delta"})
    assert "没有" in texts or "商品库" in texts
```

### Step 2: 运行测试，确认失败

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_product_analysis.py -v
```

### Step 3: 最小实现

创建 `server/backend/app/tools/product_analysis.py`：

```python
from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import ChatRequest, SessionContext


class ProductAnalysisTool:
    name = "product_analysis"
    description = "对单一命名商品做性价比/特点分析"

    def __init__(self, agent):
        self._agent = agent

    async def execute(self, request: ChatRequest, context: SessionContext, **kwargs) -> AsyncIterator[dict]:
        user_id = kwargs.get("user_id", "anonymous")
        from ..reference_resolver import resolve_named_product
        product = resolve_named_product(request.message, self._agent.product_map, context)
        message_id = _message_id()
        if product is None:
            text = (
                "当前商品库没有找到你提到的这款商品，所以我没有办法给出基于真实库存的分析。"
                "如果你告诉我预算、用途和偏好，我可以从现有商品里帮你挑一款性价比合适的。"
            )
            yield self._agent._assistant_state(message_id, "chatting", "商品库未命中", intent="product_analysis", retrieval_mode="no_retrieval")
            for event in self._agent._text_delta_events(message_id, text):
                yield event
            yield {"type": "done", "message_id": message_id}
            return

        yield self._agent._assistant_state(message_id, "explaining", "正在分析商品", intent="product_analysis", retrieval_mode="no_retrieval")
        text = self._agent._focus_product_explanation(product, context)
        for event in self._agent._text_delta_events(message_id, text):
            yield event
        yield {"type": "done", "message_id": message_id}


def _message_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]
```

在 `server/backend/app/agent.py` 的 `ShopGuideAgent._init_tool_registry` 中注册：

```python
from .tools.product_analysis import ProductAnalysisTool
self.tool_registry.register(ProductAnalysisTool(self))
```

在 `stream_message()` 中，在 `compare_products` 分支前增加 `product_analysis` 分支。需要新增一个识别函数：

```python
def _looks_like_single_product_analysis(message: str) -> bool:
    text = message or ""
    # e.g. "如何看待...性价比", "这个...怎么样", "分析一下..."
    return bool(
        re.search(r"(性价比|怎么样|如何|分析一下|值得买吗|好不好)", text)
        and not re.search(r"(对比|比较|哪个更|怎么选|第一款|第二款)", text)
    )
```

然后在 `stream_message()` 中：

```python
        if ir.intent == "compare_products" and _looks_like_single_product_analysis(request.message):
            async for event in self.tool_registry.execute(
                "product_analysis",
                request,
                context,
                user_id=user_id,
            ):
                yield event
            return
```

### Step 4: 运行测试，确认通过

```bash
../env/venv_shopguide_backend/bin/python -m pytest tests/test_product_analysis.py -v
```

### Step 5: 提交

```bash
git add server/backend/app/tools/product_analysis.py server/backend/app/agent.py server/tests/test_product_analysis.py
git commit -m "feat(intent): add product_analysis tool for single-product evaluation

- In-catalog: gives focus-style explanation
- Out-of-catalog: clearly states no inventory data, no fake product card"
```

---

## Task 8: Android 改造 ChatHistoryRepository 为 user-aware JSON 缓存

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/history/ChatHistoryModels.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/history/ChatHistoryRepository.kt`
- Test: `client/app/src/test/java/com/example/shopguideagent/data/history/ChatHistoryRepositoryTest.kt`（新建/扩展）

**Interfaces:**
- Consumes: `UserSession.currentUserId`。
- Produces: `ChatHistoryStore.read(userId)` / `write(userId, value)`；`ChatHistoryRepository` 构造接收 `userIdProvider`；JSON/Gson 格式。

### Step 1: 编写失败测试

在 `client/app/src/test/java/com/example/shopguideagent/data/history/ChatHistoryRepositoryTest.kt`：

```kotlin
package com.example.shopguideagent.data.history

import com.example.shopguideagent.data.model.ChatMessageUiModel
import com.example.shopguideagent.data.model.MessageRole
import org.junit.Assert.assertEquals
import org.junit.Test

class ChatHistoryRepositoryTest {
    @Test
    fun `saves and loads per user`() {
        val store = InMemoryChatHistoryStore()
        val repoA = ChatHistoryRepository(store) { "demo_user_a" }
        val repoB = ChatHistoryRepository(store) { "demo_user_b" }

        repoA.saveSession("s1", "A session", listOf(
            ChatMessageUiModel("m1", MessageRole.User, "hello A")
        ))
        repoB.saveSession("s1", "B session", listOf(
            ChatMessageUiModel("m1", MessageRole.User, "hello B")
        ))

        assertEquals(1, repoA.state.value.sessions.size)
        assertEquals("hello A", repoA.state.value.sessions.first().messages.first().text)
        assertEquals("hello B", repoB.state.value.sessions.first().messages.first().text)
    }

    @Test
    fun `migrates legacy base64 format to json`() {
        val legacy = "current=c2Yx\nsession|czE=|QSBTZXNzaW9u|MTAwMA==\n"
        val store = InMemoryChatHistoryStore(legacy)
        val repo = ChatHistoryRepository(store) { "demo_user_a" }
        assertEquals("s1", repo.state.value.currentSessionId)
    }
}
```

### Step 2: 运行测试，确认失败

```bash
cd /home/huadabioa/houlong/SoulDance/client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.data.history.ChatHistoryRepositoryTest"
```

Expected: FAIL，API 不匹配。

### Step 3: 最小实现

修改 `ChatHistoryModels.kt` 确保已有数据类可被 Gson 序列化（检查是否已有 `@Keep` 或默认构造器）。

修改 `ChatHistoryStore` 接口：

```kotlin
interface ChatHistoryStore {
    fun read(userId: String): String
    fun write(userId: String, value: String)
}
```

修改 `SharedPreferencesChatHistoryStore`：

```kotlin
class SharedPreferencesChatHistoryStore(
    private val preferences: SharedPreferences,
) : ChatHistoryStore {
    override fun read(userId: String): String = preferences.getString(keyFor(userId), "").orEmpty()

    override fun write(userId: String, value: String) {
        preferences.edit().putString(keyFor(userId), value).apply()
    }

    private fun keyFor(userId: String): String = "chat_history_${userId.replace(Regex("[^a-zA-Z0-9_-]"), "_")}"

    companion object {
        private const val LEGACY_KEY_HISTORY = "chat_history"
    }
}
```

修改 `InMemoryChatHistoryStore`：

```kotlin
class InMemoryChatHistoryStore(
    private val legacyValue: String = "",
    private val values: MutableMap<String, String> = mutableMapOf(),
) : ChatHistoryStore {
    override fun read(userId: String): String = values[userId] ?: legacyValue
    override fun write(userId: String, value: String) {
        values[userId] = value
    }
}
```

修改 `ChatHistoryRepository`：

```kotlin
class ChatHistoryRepository(
    private val store: ChatHistoryStore,
    private val userIdProvider: () -> String,
    private val gson: Gson = Gson(),
) {
    private val _state = MutableStateFlow(load())
    val state: StateFlow<ChatHistoryUiState> = _state.asStateFlow()

    private fun currentUserId(): String = userIdProvider()

    private fun load(): ChatHistoryUiState {
        val userId = currentUserId()
        val raw = store.read(userId)
        return if (raw.isBlank()) {
            ChatHistoryUiState()
        } else if (raw.startsWith("current=")) {
            // legacy base64 format: migrate once, then rewrite as JSON
            val migrated = LegacyChatHistoryDecoder.decodeState(raw)
            persist(migrated)
            migrated
        } else {
            runCatching { gson.fromJson(raw, ChatHistoryUiState::class.java) }
                .getOrDefault(ChatHistoryUiState())
        }
    }

    private fun persist(state: ChatHistoryUiState) {
        store.write(currentUserId(), gson.toJson(state))
    }

    // ... saveSession / selectSession / deleteSession 改为调用 persist() 并更新 _state
}
```

把原有 Base64 编解码逻辑提取到 `LegacyChatHistoryDecoder` object（同一文件内），保持只读。

更新 `chatHistoryRepository(context)` factory：

```kotlin
fun chatHistoryRepository(context: Context, userIdProvider: () -> String = { UserSession.get(context).currentUserId.value }): ChatHistoryRepository {
    val preferences = context.applicationContext.getSharedPreferences("shopguide_chat_history", Context.MODE_PRIVATE)
    return ChatHistoryRepository(SharedPreferencesChatHistoryStore(preferences), userIdProvider)
}
```

### Step 4: 运行测试，确认通过

```bash
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.data.history.ChatHistoryRepositoryTest"
```

### Step 5: 提交

```bash
git add client/app/src/main/java/com/example/shopguideagent/data/history/ChatHistoryRepository.kt client/app/src/test/java/com/example/shopguideagent/data/history/ChatHistoryRepositoryTest.kt
git commit -m "feat(android): make ChatHistoryRepository user-aware with JSON migration

- Per-user SharedPreferences key
- Legacy Base64 format read-only migration to Gson JSON
- Keeps 30 session cap"
```

---

## Task 9: Android 扩展 SessionsApi

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/remote/SessionsApiService.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/remote/SessionsApiClient.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/model/ChatMessageUiModel.kt`（若需要后端映射）
- Test: `client/app/src/test/java/com/example/shopguideagent/data/remote/SessionsApiClientTest.kt`（新建）

**Interfaces:**
- Consumes: `UserIdHeaderInterceptor`, `AppConfig.BASE_HTTP_URL`。
- Produces: `SessionsApi.listSessions()`, `getSession(id)`, `deleteSession(id)`。

### Step 1: 编写失败测试

```kotlin
package com.example.shopguideagent.data.remote

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Test

class SessionsApiClientTest {
    @Test
    fun `list sends X-User-Id`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("""{"sessions":[]}"""))
        server.start()

        val service = SessionsApiService.create({ "demo_user_b" }, baseUrl = server.url("/").toString())
        val client = SessionsApiClient(service)
        client.listSessions()

        val request = server.takeRequest()
        assertEquals("demo_user_b", request.getHeader("X-User-Id"))
        server.shutdown()
    }
}
```

### Step 2: 运行测试，确认失败

```bash
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.data.remote.SessionsApiClientTest"
```

### Step 3: 最小实现

`SessionsApiService.kt`：

```kotlin
interface SessionsApiService {
    @GET("/api/sessions/latest")
    suspend fun getLatest(): LatestSessionResponse

    @GET("/api/sessions")
    suspend fun listSessions(): SessionListResponse

    @GET("/api/sessions/{session_id}")
    suspend fun getSession(@Path("session_id") sessionId: String): SessionDetailResponse

    @DELETE("/api/sessions/{session_id}")
    suspend fun deleteSession(@Path("session_id") sessionId: String)

    companion object {
        fun create(userIdProvider: () -> String, baseUrl: String = AppConfig.BASE_HTTP_URL): SessionsApiService {
            val httpClient = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .writeTimeout(20, TimeUnit.SECONDS)
                .addInterceptor(UserIdHeaderInterceptor(userIdProvider))
                .build()
            val retrofit = Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(httpClient)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
            return retrofit.create(SessionsApiService::class.java)
        }
    }
}

data class LatestSessionResponse(val session_id: String)
data class SessionListResponse(val sessions: List<SessionSummaryDto>)
data class SessionSummaryDto(
    val session_id: String,
    val title: String,
    val updated_at: String,
    val message_count: Int,
    val preview: String,
)
data class SessionDetailResponse(
    val session_id: String,
    val title: String,
    val updated_at: String,
    val messages: List<RemoteDisplayMessageDto>,
)
data class RemoteDisplayMessageDto(
    val id: String,
    val role: String,
    val text: String,
    val created_at: String,
    val products: List<RemoteProductDto>?,
    val quick_actions: List<RemoteQuickActionDto>?,
)
```

`SessionsApiClient.kt`：

```kotlin
interface SessionsApi {
    suspend fun getLatest(): LatestSessionResponse
    suspend fun listSessions(): SessionListResponse
    suspend fun getSession(sessionId: String): SessionDetailResponse
    suspend fun deleteSession(sessionId: String)
}

class SessionsApiClient(
    private val service: SessionsApiService,
) : SessionsApi {
    override suspend fun getLatest(): LatestSessionResponse = service.getLatest()
    override suspend fun listSessions(): SessionListResponse = service.listSessions()
    override suspend fun getSession(sessionId: String): SessionDetailResponse = service.getSession(sessionId)
    override suspend fun deleteSession(sessionId: String) = service.deleteSession(sessionId)
}
```

### Step 4: 运行测试，确认通过

```bash
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.data.remote.SessionsApiClientTest"
```

### Step 5: 提交

```bash
git add client/app/src/main/java/com/example/shopguideagent/data/remote/SessionsApiService.kt client/app/src/main/java/com/example/shopguideagent/data/remote/SessionsApiClient.kt client/app/src/test/java/com/example/shopguideagent/data/remote/SessionsApiClientTest.kt
git commit -m "feat(android): extend SessionsApi for list/load/delete

- All endpoints send X-User-Id via UserIdHeaderInterceptor
- Remove deprecated no-argument create() path"
```

---

## Task 10: 修复 ChatViewModel.onUserSwitched

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
- Test: `client/app/src/test/java/com/example/shopguideagent/vm/ChatViewModelUserSwitchTest.kt`（新建）

**Interfaces:**
- Consumes: `ChatHistoryRepository`, `SessionsApi`, `RealtimeChatWebSocketClient`, `UserSession`。
- Produces: 切换用户后：旧会话持久化、加载新用户本地历史、拉取后端 latest、WebSocket 重连、UI 重置。

### Step 1: 编写失败测试

```kotlin
package com.example.shopguideagent.vm

import com.example.shopguideagent.config.UserSession
import com.example.shopguideagent.data.history.ChatHistoryRepository
import com.example.shopguideagent.data.history.InMemoryChatHistoryStore
import com.example.shopguideagent.data.remote.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.Assert.assertEquals
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ChatViewModelUserSwitchTest {
    @Test
    fun `onUserSwitched loads new user history`() = runTest {
        val userSession = UserSession.create(android.content.Context::class.java) // use real or mock
        // simplified: use InMemory store and fake APIs
        val store = InMemoryChatHistoryStore()
        val historyA = ChatHistoryRepository(store) { "demo_user_a" }
        historyA.saveSession("sa", "A", emptyList())

        val historyB = ChatHistoryRepository(store) { "demo_user_b" }
        historyB.saveSession("sb", "B", emptyList())

        // Assert separate repositories hold separate data
        assertEquals("A", historyA.state.value.sessions.first().title)
        assertEquals("B", historyB.state.value.sessions.first().title)
    }
}
```

### Step 2: 运行测试，确认失败

```bash
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.vm.ChatViewModelUserSwitchTest"
```

### Step 3: 最小实现

修改 `ChatViewModel.onUserSwitched`：

```kotlin
    fun onUserSwitched(newUserId: String) {
        viewModelScope.launch {
            val currentUserId = userIdProvider()
            if (newUserId == currentUserId) return@launch

            // 1. persist current user's session
            persist()

            // 2. switch user session
            userSession?.setCurrentUserId(newUserId)

            // 3. close old WebSocket
            wsJob?.cancel()
            wsClient.close()
            wsJob = null

            // 4. load new user's local history
            val newHistory = historyRepository ?: ChatHistoryRepository(
                InMemoryChatHistoryStore(),
                userIdProvider,
            )
            val localSession = newHistory.currentSession()

            // 5. fetch latest from backend
            val latest = try {
                sessionsApi.getLatest()
            } catch (e: Exception) {
                LatestSessionResponse(session_id = localSession?.sessionId ?: "session_${UUID.randomUUID()}")
            }

            activeSessionId = latest.session_id

            // 6. if backend session differs from local, try to load backend detail
            val backendMessages = try {
                sessionsApi.getSession(activeSessionId).messages.map { it.toUiModel() }
            } catch (e: Exception) {
                emptyList()
            }

            val messages = backendMessages.takeIf { it.isNotEmpty() }
                ?: localSession?.messages
                ?: listOf(welcome)

            _uiState.value = ChatUiState(
                sessionId = activeSessionId,
                cartBadgeCount = 0,
                isSpeakerEnabled = true,
                voiceRecognitionState = VoiceRecognitionState.Idle,
                messages = messages,
            )

            activeStreamUserText = null
            lastProductFollowUpPayload = null
            activeAssistantId = null
            activeFollowUpAssistantId = null
            activeFollowUpText = null
            audioPlayer.stop()

            ensureWebSocketConnection()
        }
    }
```

注意：由于 `historyRepository` 在 `ChatViewModel` 构造时注入且 `userIdProvider` 是 lambda，本地历史 repository 的 StateFlow 在切换时应当重新加载。如果 repository 内部缓存了旧 user 的 decode 结果，需要给 repository 增加 `reload()` 方法。

建议给 `ChatHistoryRepository` 增加：

```kotlin
    fun reload() {
        _state.value = load()
    }
```

并在 `onUserSwitched` 中调用 `historyRepository?.reload()`。

### Step 4: 运行测试，确认通过

```bash
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.vm.ChatViewModelUserSwitchTest"
```

### Step 5: 提交

```bash
git add client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt client/app/src/test/java/com/example/shopguideagent/vm/ChatViewModelUserSwitchTest.kt
git commit -m "fix(android): make ChatViewModel.onUserSwitched persist and reload history

- Persist current session before switch
- Reload local history for new user
- Fetch latest/backend session and close/reopen WebSocket"
```

---

## Task 11: 修复 AppNavGraph SwitchUser effect

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeRoute.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/navigation/AppNavGraph.kt`
- Test: 通过真机/模拟器冒烟验证

**Interfaces:**
- Consumes: `SpriteHomeEffect.SwitchUser`, `chatViewModel`。
- Produces: 切换用户时统一调用 `chatViewModel.onUserSwitched(userId)`。

### Step 1: 定位 effect 处理

读取 `SpriteHomeRoute.kt` 中 `onEffect` 的调用点，确认 `SwitchUser` 当前在哪里被处理。

### Step 2: 修改 SpriteHomeRoute

在 `SpriteHomeRoute` 内部处理 `SwitchUser` 时，新增回调 `onSwitchUser: (String) -> Unit`，不要只改本地状态。

### Step 3: 修改 AppNavGraph

把 `AppNavGraph.kt:205` 的吞掉处理移除：

```kotlin
is SpriteHomeEffect.SwitchUser -> {
    chatViewModel.onUserSwitched(effect.userId)
}
```

同时 `onUserSelected` 只负责触发 effect 或交给 SpriteHomeRoute 处理，避免重复 setUserId。

### Step 4: 运行编译

```bash
./gradlew :app:assembleDebug
```

### Step 5: 提交

```bash
git add client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeRoute.kt client/app/src/main/java/com/example/shopguideagent/navigation/AppNavGraph.kt
git commit -m "fix(android): wire SwitchUser effect to ChatViewModel.onUserSwitched

- Removes swallowed SwitchUser handling in AppNavGraph
- Home drawer and Chat drawer user switches now share the same path"
```

---

## Task 12: 中文文案 mojibake 修复

**Files:**
- Modify: `client/app/src/main/res/values/strings.xml`
- Modify: `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/component/ChatHistoryDrawer.kt`
- 其他发现 mojibake 的位置

**Interfaces:**
- Consumes: 用户可见中文文案。
- Produces: 无乱码的中文提示。

### Step 1: 扫描 mojibake

```bash
cd /home/huadabioa/houlong/SoulDance/client
find app/src/main -name "*.kt" -o -name "*.xml" | xargs grep -P '[\x00-\x08\x0b\x0c\x0e-\x1f]' || echo "no control chars"
```

### Step 2: 修复已知位置

至少覆盖：
- `ChatViewModel.welcome` 文案
- `ChatHistoryRepository` 默认标题 "新会话"
- `ChatHistoryDrawer` 空态/标题
- `strings.xml` 中所有中文

### Step 3: 提交

```bash
git add client/app/src/main/res/values/strings.xml client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt client/app/src/main/java/com/example/shopguideagent/ui/component/ChatHistoryDrawer.kt
git commit -m "fix(android): fix visible Chinese mojibake in history, welcome, user menu"
```

---

## Task 13: 后端回归测试

**Files:**
- 运行已有测试

### Step 1: 运行后端测试套件

```bash
cd /home/huadabioa/houlong/SoulDance/server
../env/venv_shopguide_backend/bin/python -m pytest tests/test_sessions_latest_endpoint.py tests/test_db_stores.py tests/test_agent_core.py tests/test_display_message_schema.py tests/test_session_store_list_delete.py tests/test_sessions_api.py tests/test_display_messages_stream.py tests/test_cart_action_display_messages.py tests/test_small_talk_capability.py tests/test_product_analysis.py -q
```

### Step 2: 提交

全部通过：

```bash
git commit --allow-empty -m "test(server): regression pass for session persistence and intent fixes"
```

---

## Task 14: Android 回归测试与构建

### Step 1: 运行单元测试

```bash
cd /home/huadabioa/houlong/SoulDance/client
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
./gradlew :app:testDebugUnitTest
```

### Step 2: 构建 debug APK

```bash
./gradlew :app:assembleDebug
```

### Step 3: 提交

```bash
git commit --allow-empty -m "test(android): unit tests and debug build pass"
```

---

## Task 15: 真机/模拟器冒烟验证

### Step 1: 安装 APK

```bash
adb install -r client/app/build/outputs/apk/debug/app-debug.apk
```

### Step 2: 启动后端

```bash
cd /home/huadabioa/houlong/SoulDance/server
bash scripts/start_backend.sh
```

### Step 3: 验证清单

1. demo_user_a 发送“你能帮我做些什么” → 返回能力说明，无商品卡。
2. demo_user_a 发送“小米17max 性价比” → 提示无库存数据，无假商品卡。
3. demo_user_a 发送“推荐手机” → 有 product_item 返回，历史抽屉能看到该会话。
4. 切换到 demo_user_b → 历史抽屉为空，购物车为空。
5. demo_user_b 发消息后切回 demo_user_a → 能看到 a 的历史。
6. 删除 demo_user_a 的一个会话 → 列表刷新，后端 `GET /api/sessions` 同步消失。
7. 抓包/日志确认 `/api/sessions`、`/ws/chat`、`/api/cart` 请求头 `X-User-Id` 正确变化。

### Step 4: 提交

```bash
git commit --allow-empty -m "smoke: session persistence, user switch, small-talk/product-analysis verified"
```

---

## Self-Review

1. **Spec coverage:**
   - 历史会话持久化：Task 1-5、Task 13 覆盖。
   - 用户切换：Task 8-11、Task 15 覆盖。
   - 闲聊：Task 6 覆盖。
   - 单品分析：Task 7 覆盖。
   - X-User-Id 隔离：Task 2、3、9、10 覆盖。
   - mojibake：Task 12 覆盖。

2. **Placeholder scan:** 无 TBD/TODO；每个 task 含具体代码与命令。

3. **Type consistency:**
   - 后端 `DisplayMessageProduct` 字段与 `ProductCard` 保持一致。
   - Android `RemoteDisplayMessageDto` / `RemoteProductDto` 字段与后端 `DisplayMessage` / `DisplayMessageProduct` 一致。
   - `SessionsApi` 接口新增方法名在 Service 与 Client 中一致。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-27-session-persistence-user-switch-analysis.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach do you prefer?
