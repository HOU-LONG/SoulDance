# User Switching And Tenant Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add demo-grade user switching (Footer dropdown + persisted client identity + `X-User-Id` header transport + backend dependency + per-user repositories + one-time DB migration), so that `(user_id, session_id)` tenant isolation can be observed end-to-end before the compression spec's Task 4 runs.

**Architecture:** Identity travels in a single `X-User-Id` HTTP/WebSocket header from a mutable `UserSession` on the client to a FastAPI dependency on the backend. Repositories take `user_id` as a required parameter, and `session_states`/`carts` enforce `UniqueConstraint(user_id, session_id)`. A one-time migration script rewrites existing rows as `user_id='anonymous'` so backward compatibility holds.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, SQLite (dev), Pydantic 2; Kotlin/Android, OkHttp, Compose, kotlinx.coroutines.

## Global Constraints

- Demo-grade only: no login, no token, no OAuth, no admin endpoints.
- `X-User-Id` is the single transport for identity; bodies never carry it.
- Missing header resolves to `user_id="anonymous"` for backward compatibility; existing tests must not be edited to send the header.
- User id validation: `^[a-z0-9_]{1,64}$` — anything else returns HTTP 400.
- Existing 397-test backend regression must stay green throughout.
- `session_id` keeps its current naming and lifetime semantics; only its uniqueness scope changes from global to `(user_id, session_id)`.
- Concurrency stays last-write-wins (locking is a later spec's concern).
- All Chinese comments and copy in the existing code stay Chinese; new copy follows the same convention.

---

## File Structure

### Backend (Python)

- Create: `server/backend/app/identity.py`
  - `get_current_user_id(request: Request) -> str` FastAPI dependency, validation regex, `ANONYMOUS_USER_ID` constant.
- Create: `server/scripts/migrate_session_tenant_keys.py`
  - One-time idempotent migration for `session_states` and `carts` covering SQLite (table rebuild) and Postgres (alter + index swap).
- Modify: `server/backend/app/db/models.py`
  - Add `user_id` to `SessionState` and `Cart`. Remove `unique=True` on their `session_id` columns. Add `UniqueConstraint("user_id", "session_id", ...)`.
- Modify: `server/backend/app/repositories/session_repository.py`
  - All methods require `user_id: str`.
  - Add `get_latest_session_id(user_id)` for the "jump to latest session on switch" flow.
- Modify: `server/backend/app/repositories/cart_repository.py`
  - All methods require `user_id`.
- Modify: `server/backend/app/session_store.py`
  - `get(user_id, session_id)`, `save(user_id, session_id)`, `save_all` iterates `(user_id, session_id)` pairs.
- Modify: `server/backend/app/cart.py` and `server/backend/app/cart_service.py` if it exists
  - Plumb `user_id` through to the repository.
- Modify: `server/backend/app/main.py`
  - Add `user_id: str = Depends(get_current_user_id)` to every endpoint that touches session/cart/feedback.
  - Add `GET /api/sessions/latest` endpoint.
  - WebSocket reads `X-User-Id` from the upgrade headers.
- Modify: `server/backend/app/agent.py`
  - `ShopGuideAgent.handle_message`, `stream_message`, and any session-keyed method takes `user_id`.

### Backend tests

- Create: `server/tests/test_identity_dependency.py`
- Create: `server/tests/test_tenant_isolation.py`
- Create: `server/tests/test_sessions_latest_endpoint.py`
- Create: `server/tests/test_migration_script.py`
- Modify: `server/tests/test_db_stores.py` — every repo call adds a `user_id` arg.
- Modify: `server/tests/test_session_ttl.py` — same.
- Modify: `server/tests/test_api.py`, `server/tests/test_websocket_protocol_envelope.py` — assert anonymous-default behavior still passes existing assertions.
- Modify: `server/tests/test_cart_db.py`, `server/tests/test_order_flow.py` — pass `user_id`.

### Client (Kotlin)

- Modify: `client/app/src/main/java/com/example/shopguideagent/config/UserSession.kt`
  - `object UserSession` becomes a `class UserSession` (singleton via Application) with a `StateFlow<String> currentUserId`, `PRESET_USERS` list, `setCurrentUserId(String)`, SharedPreferences persistence.
- Create: `client/app/src/main/java/com/example/shopguideagent/data/remote/UserIdHeaderInterceptor.kt`
  - OkHttp `Interceptor` that adds `X-User-Id` to every request.
- Modify: every `OkHttpClient.Builder()` site in `client/app/src/main/java/com/example/shopguideagent/data/remote/`
  - Add `UserIdHeaderInterceptor`. Sites: `RealtimeChatWebSocketClient`, `OrderApiService`, `SttApiService`, any other `OkHttpClient` introduction.
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt`
  - Add `X-User-Id` to the upgrade `Request`.
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/component/ChatHistoryDrawer.kt`
  - `DrawerUserFooter` becomes a dropdown.
- Create: `client/app/src/main/java/com/example/shopguideagent/data/local/FirePointsStore.kt`
  - Per-user SharedPreferences-backed storage for firePoints (so switching can rescope it).
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt`
  - Read firePoints from `FirePointsStore` keyed by `currentUserId`. Re-collect when the id changes.
- Modify: `client/app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt`
  - Read `userId` from `UserSession.currentUserId.value` (not the const), reload on collection.
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/model/ChatMessage.kt`
  - `toJson` default no longer references `UserSession.DEFAULT_SESSION_ID` directly; pass it in.
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/local/SessionStore.kt`
  - `currentSessionId()` reads the active user's latest session id (kept simple: still returns `DEFAULT_SESSION_ID` for v1, but uses it as a per-user default).
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`
  - On `currentUserId` change, call `GET /api/sessions/latest`, then reopen the WebSocket against the returned session id.

### Client tests

- Create: `client/app/src/test/java/com/example/shopguideagent/config/UserSessionTest.kt`
- Create: `client/app/src/test/java/com/example/shopguideagent/data/remote/UserIdHeaderInterceptorTest.kt`
- Modify: `client/app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.kt` — assert switch reloads.

---

## Task 1: Backend Identity Dependency

**Files:**
- Create: `server/backend/app/identity.py`
- Create: `server/tests/test_identity_dependency.py`

**Interfaces:**
- Consumes: nothing (foundational task).
- Produces: `get_current_user_id(request: Request) -> str`, constant `ANONYMOUS_USER_ID = "anonymous"`, validator `is_valid_user_id(value: str) -> bool` (regex `^[a-z0-9_]{1,64}$`).

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_identity_dependency.py
from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from backend.app.identity import (
    ANONYMOUS_USER_ID,
    get_current_user_id,
    is_valid_user_id,
)


def _make_request(headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


def test_get_current_user_id_returns_anonymous_when_header_missing() -> None:
    assert get_current_user_id(_make_request()) == ANONYMOUS_USER_ID


def test_get_current_user_id_reads_x_user_id_header() -> None:
    request = _make_request({"X-User-Id": "demo_user_a"})
    assert get_current_user_id(request) == "demo_user_a"


def test_get_current_user_id_rejects_malformed_header() -> None:
    request = _make_request({"X-User-Id": "Demo User!"})
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(request)
    assert exc.value.status_code == 400
    assert "user_id" in exc.value.detail.lower()


def test_get_current_user_id_rejects_too_long_value() -> None:
    request = _make_request({"X-User-Id": "x" * 65})
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(request)
    assert exc.value.status_code == 400


def test_is_valid_user_id_accepts_lowercase_alnum_underscore() -> None:
    assert is_valid_user_id("demo_user_a")
    assert is_valid_user_id("u1")
    assert is_valid_user_id("a" * 64)


def test_is_valid_user_id_rejects_uppercase_special_or_too_long() -> None:
    assert not is_valid_user_id("Demo")
    assert not is_valid_user_id("user-a")
    assert not is_valid_user_id("")
    assert not is_valid_user_id("a" * 65)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/huadabioa/houlong/SoulDance/server
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_identity_dependency.py
```

Expected: FAIL — `ModuleNotFoundError: backend.app.identity`.

- [ ] **Step 3: Implement the identity module**

```python
# server/backend/app/identity.py
"""User identity transport — single source for tenant attribution.

A request without `X-User-Id` resolves to `ANONYMOUS_USER_ID` (Spec
principle 4). Malformed values fail loud with HTTP 400 so client bugs
cannot silently corrupt the ledger (Spec principle 8).
"""
from __future__ import annotations

import re

from fastapi import HTTPException, Request

ANONYMOUS_USER_ID = "anonymous"
_USER_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def is_valid_user_id(value: str) -> bool:
    return bool(_USER_ID_RE.fullmatch(value))


def get_current_user_id(request: Request) -> str:
    raw = request.headers.get("X-User-Id")
    if raw is None:
        return ANONYMOUS_USER_ID
    if not is_valid_user_id(raw):
        raise HTTPException(
            status_code=400,
            detail="Invalid X-User-Id header: must match ^[a-z0-9_]{1,64}$",
        )
    return raw
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_identity_dependency.py
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add server/backend/app/identity.py server/tests/test_identity_dependency.py
git commit -m "feat: add X-User-Id FastAPI dependency

Task 1 of user switching and tenant isolation plan
(docs/superpowers/specs/2026-06-24-user-switching-and-tenant-isolation-spec.md).

Adds get_current_user_id() dependency: reads X-User-Id, validates
against ^[a-z0-9_]{1,64}$, returns 'anonymous' when missing for
backward compatibility, raises HTTP 400 on malformed input.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Tenant-Aware DB Schema And Migration Script

**Files:**
- Modify: `server/backend/app/db/models.py`
- Create: `server/scripts/migrate_session_tenant_keys.py`
- Create: `server/tests/test_migration_script.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SessionState.user_id`, `Cart.user_id` columns; `UniqueConstraint("user_id", "session_id")` on both tables; `migrate_session_tenant_keys.migrate(engine) -> dict` returning `{"session_states": int, "carts": int}` migration counts; idempotent (re-running returns zeros).

- [ ] **Step 1: Write the failing migration tests**

```python
# server/tests/test_migration_script.py
"""Migration script for adding user_id to session_states and carts.

The script must:
- be idempotent (running twice does not double-write or raise)
- preserve existing rows (set user_id='anonymous')
- enforce the new (user_id, session_id) uniqueness afterwards
- work on SQLite (where the old single-column unique is an autoindex
  that requires a table rebuild)
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from backend.scripts.migrate_session_tenant_keys import migrate


def _build_legacy_schema(engine) -> None:
    """Re-create the pre-migration schema so the test mirrors prod."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE session_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(128) NOT NULL UNIQUE,
                state_json JSON NOT NULL DEFAULT '{}',
                schema_version INTEGER NOT NULL DEFAULT 1,
                last_activity_at DATETIME,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
        conn.execute(text("CREATE INDEX ix_session_states_session_id ON session_states (session_id)"))
        conn.execute(text("""
            CREATE TABLE carts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(128) NOT NULL UNIQUE,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
        conn.execute(text("INSERT INTO session_states (session_id, state_json) VALUES ('s1', '{}')"))
        conn.execute(text("INSERT INTO session_states (session_id, state_json) VALUES ('s2', '{}')"))
        conn.execute(text("INSERT INTO carts (session_id) VALUES ('s1')"))


def test_migrate_backfills_anonymous_and_drops_old_unique() -> None:
    engine = create_engine("sqlite:///:memory:")
    _build_legacy_schema(engine)
    result = migrate(engine)
    assert result["session_states"] == 2
    assert result["carts"] == 1
    with engine.begin() as conn:
        rows = list(conn.execute(text("SELECT user_id, session_id FROM session_states ORDER BY session_id")))
        assert rows == [("anonymous", "s1"), ("anonymous", "s2")]
        # Old single-column unique on session_id must NOT survive: same
        # session_id is now permitted across different user_id values.
        conn.execute(text("INSERT INTO session_states (user_id, session_id, state_json) VALUES ('u_b', 's1', '{}')"))
        rows = list(conn.execute(text("SELECT user_id FROM session_states WHERE session_id='s1' ORDER BY user_id")))
        assert rows == [("anonymous",), ("u_b",)]


def test_migrate_is_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    _build_legacy_schema(engine)
    first = migrate(engine)
    second = migrate(engine)
    assert first["session_states"] == 2
    assert second["session_states"] == 0
    assert second["carts"] == 0


def test_migrate_enforces_new_composite_unique() -> None:
    engine = create_engine("sqlite:///:memory:")
    _build_legacy_schema(engine)
    migrate(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO session_states (user_id, session_id, state_json) VALUES ('u', 'sNew', '{}')"))
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO session_states (user_id, session_id, state_json) VALUES ('u', 'sNew', '{}')"))


def test_migrate_on_fresh_schema_is_noop() -> None:
    """If schema already has user_id (e.g. fresh dev DB created from
    updated SQLAlchemy models), the migration should silently no-op.
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE session_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous',
                session_id VARCHAR(128) NOT NULL,
                state_json JSON NOT NULL DEFAULT '{}',
                schema_version INTEGER NOT NULL DEFAULT 1,
                last_activity_at DATETIME,
                created_at DATETIME,
                updated_at DATETIME,
                UNIQUE (user_id, session_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE carts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous',
                session_id VARCHAR(128) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME,
                UNIQUE (user_id, session_id)
            )
        """))
    result = migrate(engine)
    assert result == {"session_states": 0, "carts": 0}
```

- [ ] **Step 2: Run the failing tests**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_migration_script.py
```

Expected: FAIL — `ModuleNotFoundError: backend.scripts.migrate_session_tenant_keys`.

- [ ] **Step 3: Add `scripts/__init__.py` if missing**

```bash
test -f server/backend/scripts/__init__.py || mkdir -p server/backend/scripts && touch server/backend/scripts/__init__.py
```

Note: this plan places the migration under `server/backend/scripts/` (not `server/scripts/`) so it lives inside the `backend` package and is importable from tests.

- [ ] **Step 4: Implement the migration script**

```python
# server/backend/scripts/migrate_session_tenant_keys.py
"""One-time migration: add user_id to session_states and carts, drop
the old single-column session_id uniqueness, enforce (user_id, session_id).

Idempotent: detects whether the schema already has user_id and exits
silently if so. Dialect-aware: rebuilds the table on SQLite where
column-level UNIQUE creates an autoindex that cannot be dropped in
place; uses ALTER on Postgres.

Usage:
    python -m backend.scripts.migrate_session_tenant_keys

Or programmatically:
    from backend.scripts.migrate_session_tenant_keys import migrate
    migrate(engine)
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _has_user_id(engine: Engine, table: str) -> bool:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns(table)}
    return "user_id" in columns


def _migrate_sqlite_table(engine: Engine, table: str, extra_columns_sql: str) -> int:
    """Rebuild `table` with a new schema and copy old rows in.

    `extra_columns_sql` is the full column list (excluding id/user_id/session_id)
    for the new table definition.
    """
    new_table = f"{table}_new"
    with engine.begin() as conn:
        # Count rows we'll migrate so the return value reflects actual work.
        row_count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
        conn.execute(text(f"DROP TABLE IF EXISTS {new_table}"))
        if table == "session_states":
            conn.execute(text(f"""
                CREATE TABLE {new_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous',
                    session_id VARCHAR(128) NOT NULL,
                    state_json JSON NOT NULL DEFAULT '{{}}',
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    last_activity_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME,
                    UNIQUE (user_id, session_id)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO {new_table}
                    (id, user_id, session_id, state_json, schema_version, last_activity_at, created_at, updated_at)
                SELECT
                    id, 'anonymous', session_id, state_json, schema_version, last_activity_at, created_at, updated_at
                FROM {table}
            """))
        elif table == "carts":
            conn.execute(text(f"""
                CREATE TABLE {new_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous',
                    session_id VARCHAR(128) NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME,
                    UNIQUE (user_id, session_id)
                )
            """))
            conn.execute(text(f"""
                INSERT INTO {new_table}
                    (id, user_id, session_id, created_at, updated_at)
                SELECT
                    id, 'anonymous', session_id, created_at, updated_at
                FROM {table}
            """))
        else:
            raise ValueError(f"Unknown table: {table}")
        conn.execute(text(f"DROP TABLE {table}"))
        conn.execute(text(f"ALTER TABLE {new_table} RENAME TO {table}"))
        # Recreate the secondary index on session_id (now non-unique).
        conn.execute(text(f"CREATE INDEX ix_{table}_session_id ON {table} (session_id)"))
        conn.execute(text(f"CREATE INDEX ix_{table}_user_id ON {table} (user_id)"))
    return row_count


def _migrate_postgres_table(engine: Engine, table: str) -> int:
    with engine.begin() as conn:
        row_count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous'"))
        conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_session_id_key"))
        conn.execute(text(f"DROP INDEX IF EXISTS ix_{table}_session_id"))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_session_id ON {table} (session_id)"))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON {table} (user_id)"))
        conn.execute(text(
            f"ALTER TABLE {table} ADD CONSTRAINT uq_{table}_user_session UNIQUE (user_id, session_id)"
        ))
    return row_count


def migrate(engine: Engine) -> dict[str, int]:
    """Migrate `session_states` and `carts` to include user_id.

    Returns a dict of how many rows were migrated per table. A no-op
    (already-migrated) call returns zeros and does not raise.
    """
    dialect = engine.dialect.name
    counts: dict[str, int] = {}
    for table in ("session_states", "carts"):
        if _has_user_id(engine, table):
            counts[table] = 0
            continue
        if dialect == "sqlite":
            counts[table] = _migrate_sqlite_table(engine, table, "")
        else:
            counts[table] = _migrate_postgres_table(engine, table)
    return counts


if __name__ == "__main__":
    from backend.app.config import get_settings
    from backend.app.db.engine import create_engine_from_url

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("SHOPGUIDE_DATABASE_URL is not set; cannot migrate.")
    engine = create_engine_from_url(settings.database_url)
    summary = migrate(engine)
    print(f"Migration complete: {summary}")
```

- [ ] **Step 5: Run migration tests to verify they pass**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_migration_script.py
```

Expected: PASS, 4 tests.

- [ ] **Step 6: Update SQLAlchemy models to match the new schema**

Edit `server/backend/app/db/models.py`. For `Cart` (around line 113-121), change:

```python
class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, default="anonymous", index=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_carts_user_session"),)

    items: Mapped[list["CartItem"]] = relationship(
        "CartItem", back_populates="cart", cascade="all, delete-orphan", lazy="selectin"
    )
```

For `SessionState` (around line 184-195), change:

```python
class SessionState(Base):
    __tablename__ = "session_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, default="anonymous", index=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_session_states_user_session"),)
```

- [ ] **Step 7: Run migration tests again (sanity)**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_migration_script.py
```

Expected: still PASS.

- [ ] **Step 8: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add server/backend/app/db/models.py \
        server/backend/scripts/__init__.py \
        server/backend/scripts/migrate_session_tenant_keys.py \
        server/tests/test_migration_script.py
git commit -m "feat: add user_id to session_states and carts with migration

Task 2 of user switching and tenant isolation plan.

Adds user_id column to session_states and carts, replaces the old
single-column session_id unique constraint with composite
UniqueConstraint(user_id, session_id). Provides an idempotent
migration script that backfills existing rows as user_id='anonymous',
handles SQLite (table rebuild) and Postgres (ALTER + index swap),
and no-ops on an already-migrated schema.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Dual-Key Session Repository

**Files:**
- Modify: `server/backend/app/repositories/session_repository.py`
- Modify: `server/backend/app/session_store.py`
- Create: `server/tests/test_tenant_isolation.py`
- Modify: `server/tests/test_db_stores.py`
- Modify: `server/tests/test_session_ttl.py`

**Interfaces:**
- Consumes: `SessionState.user_id` from Task 2.
- Produces:
  - `SessionRepository.get(user_id: str, session_id: str) -> SessionContext | None`
  - `SessionRepository.save(user_id: str, context: SessionContext) -> None`
  - `SessionRepository.get_latest_session_id(user_id: str) -> str | None`
  - `SessionStore.get(user_id: str, session_id: str) -> SessionContext`
  - `SessionStore.save(user_id: str, session_id: str) -> None`

- [ ] **Step 1: Write the failing isolation tests**

```python
# server/tests/test_tenant_isolation.py
"""Two users with the same session_id must not see each other's state."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.db.base import Base
from backend.app.db.engine import create_engine_from_url
from backend.app.models import SessionContext
from backend.app.repositories.session_repository import SessionRepository
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db_session():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_same_session_id_isolated_across_users(db_session) -> None:
    repo = SessionRepository(db_session)
    ctx_a = SessionContext(session_id="s1", focus_product_id="pA")
    ctx_b = SessionContext(session_id="s1", focus_product_id="pB")
    repo.save("user_a", ctx_a)
    repo.save("user_b", ctx_b)
    db_session.commit()
    assert repo.get("user_a", "s1").focus_product_id == "pA"
    assert repo.get("user_b", "s1").focus_product_id == "pB"


def test_repository_returns_none_for_unknown_pair(db_session) -> None:
    repo = SessionRepository(db_session)
    assert repo.get("user_x", "missing") is None


def test_get_latest_session_id_scopes_to_user(db_session) -> None:
    repo = SessionRepository(db_session)
    repo.save("user_a", SessionContext(session_id="s_a1"))
    repo.save("user_a", SessionContext(session_id="s_a2"))
    repo.save("user_b", SessionContext(session_id="s_b1"))
    db_session.commit()
    # Most recently saved one per user.
    assert repo.get_latest_session_id("user_a") == "s_a2"
    assert repo.get_latest_session_id("user_b") == "s_b1"
    assert repo.get_latest_session_id("never_seen") is None


def test_duplicate_user_session_pair_raises_integrity(db_session) -> None:
    from backend.app.db.models import SessionState
    db_session.add(SessionState(user_id="u", session_id="s", state_json={}))
    db_session.add(SessionState(user_id="u", session_id="s", state_json={}))
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run failing tests**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_tenant_isolation.py
```

Expected: FAIL — `SessionRepository.save()` does not yet take a `user_id` positional.

- [ ] **Step 3: Update `SessionRepository`**

Replace the contents of `server/backend/app/repositories/session_repository.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db.models import SessionState
from ..models import SessionContext


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: str, session_id: str) -> SessionContext | None:
        row = (
            self.db.query(SessionState)
            .filter_by(user_id=user_id, session_id=session_id)
            .first()
        )
        if row is None:
            return None
        return SessionContext.model_validate(row.state_json)

    def save(self, user_id: str, context: SessionContext) -> None:
        context.last_activity_at = datetime.now(timezone.utc).isoformat()
        row = (
            self.db.query(SessionState)
            .filter_by(user_id=user_id, session_id=context.session_id)
            .first()
        )
        if row is None:
            row = SessionState(user_id=user_id, session_id=context.session_id)
            self.db.add(row)
        row.state_json = context.model_dump(mode="json")
        row.schema_version = context.schema_version
        row.last_activity_at = datetime.now(timezone.utc)
        self.db.flush()

    def get_latest_session_id(self, user_id: str) -> str | None:
        row = (
            self.db.query(SessionState)
            .filter_by(user_id=user_id)
            .order_by(SessionState.last_activity_at.desc())
            .first()
        )
        return row.session_id if row else None

    def cleanup_expired(self, ttl_days: int) -> None:
        cutoff_sql = text(f"julianday('now') - {ttl_days}")
        self.db.query(SessionState).filter(
            SessionState.last_activity_at < cutoff_sql
        ).delete(synchronize_session=False)
        self.db.flush()
```

- [ ] **Step 4: Update `SessionStore` to thread `user_id`**

Edit `server/backend/app/session_store.py`. The `get`/`save` methods become two-arg, and the in-memory cache key becomes a tuple:

```python
# At top of class, after _sessions: dict[str, ...]
self._sessions: dict[tuple[str, str], SessionContext] = {}

def get(self, user_id: str, session_id: str) -> SessionContext:
    key = (user_id, session_id)
    if self._repo is not None:
        ctx = self._repo.get(user_id, session_id)
        if ctx is None:
            ctx = SessionContext(session_id=session_id)
            self._repo.save(user_id, ctx)
        else:
            ctx.last_activity_at = datetime.now(timezone.utc).isoformat()
            self._repo.save(user_id, ctx)
        self._sessions[key] = ctx
        return ctx
    if key not in self._sessions:
        loaded = self._load_one(user_id, session_id)
        self._sessions[key] = loaded if loaded else SessionContext(session_id=session_id)
    ctx = self._sessions[key]
    ctx.last_activity_at = datetime.now(timezone.utc).isoformat()
    return ctx

def save(self, user_id: str, session_id: str) -> None:
    key = (user_id, session_id)
    if self._repo is not None:
        ctx = self._sessions.get(key)
        if ctx is None:
            ctx = self._repo.get(user_id, session_id)
        if ctx is not None:
            ctx.schema_version = self.CURRENT_SCHEMA_VERSION
            self._repo.save(user_id, ctx)
        return
    context = self._sessions.get(key)
    if not context:
        return
    context.schema_version = self.CURRENT_SCHEMA_VERSION
    path = self._path(user_id, session_id)
    ...  # existing file-write logic, but path now incorporates user_id
```

For file-mode persistence (when no DB), update `_path`, `_load_one`, `_load_all`, `save_all` to include `user_id` in the on-disk layout: `<persist_dir>/<user_id>/<session_id>.json`.

- [ ] **Step 5: Update existing repository/store tests to pass user_id**

Find every call to `SessionRepository.get(...)` / `.save(...)` and `SessionStore.get(...)` / `.save(...)` in:
- `server/tests/test_db_stores.py`
- `server/tests/test_session_ttl.py`

Add `"anonymous"` as the first positional argument to preserve current behavior.

```bash
grep -rn "session_repo\.\|SessionRepository\|sessions\.get\|sessions\.save\|session_store\.get\|session_store\.save" server/tests/
```

For each match, prepend `"anonymous"` as the user id positional.

- [ ] **Step 6: Run isolation + regression tests**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_tenant_isolation.py tests/test_db_stores.py tests/test_session_ttl.py
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add server/backend/app/repositories/session_repository.py \
        server/backend/app/session_store.py \
        server/tests/test_tenant_isolation.py \
        server/tests/test_db_stores.py \
        server/tests/test_session_ttl.py
git commit -m "feat: dual-key session repository (user_id, session_id)

Task 3 of user switching and tenant isolation plan.

SessionRepository.get/save now require user_id as the first positional
argument; calling without it is a TypeError, not a silent default.
Adds get_latest_session_id(user_id) for the 'jump to latest session
on switch' flow. SessionStore threads user_id through its in-memory
cache (keyed by tuple) and file-mode persistence layout.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Dual-Key Cart Repository And Service

**Files:**
- Modify: `server/backend/app/repositories/cart_repository.py`
- Modify: `server/backend/app/cart.py`
- Modify: `server/tests/test_cart_db.py`
- Modify: `server/tests/test_order_flow.py`
- Modify: `server/tests/test_tenant_isolation.py`

**Interfaces:**
- Consumes: `Cart.user_id` from Task 2.
- Produces:
  - `CartRepository.get(user_id, session_id) -> dict`
  - `CartRepository.add(user_id, session_id, product_id, quantity) -> dict`
  - `CartRepository.update_quantity(user_id, session_id, product_id, quantity) -> dict`
  - `CartRepository.remove(user_id, session_id, product_id) -> dict`
  - `CartRepository.clear(user_id, session_id) -> dict`
  - `cart.get/add/update_quantity/remove/clear/checkout` all take `user_id` first.

- [ ] **Step 1: Extend the isolation test with cart coverage**

Append to `server/tests/test_tenant_isolation.py`:

```python
def test_cart_repository_isolates_by_user(db_session) -> None:
    from backend.app.repositories.cart_repository import CartRepository
    repo = CartRepository(db_session)
    repo.add("user_a", "s1", "prod_x", 2)
    repo.add("user_b", "s1", "prod_y", 3)
    db_session.commit()
    cart_a = repo.get("user_a", "s1")
    cart_b = repo.get("user_b", "s1")
    assert {i["product_id"] for i in cart_a["items"]} == {"prod_x"}
    assert {i["product_id"] for i in cart_b["items"]} == {"prod_y"}
```

- [ ] **Step 2: Run to confirm failure**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_tenant_isolation.py::test_cart_repository_isolates_by_user
```

Expected: FAIL.

- [ ] **Step 3: Update `CartRepository` signatures**

In `server/backend/app/repositories/cart_repository.py`, every method that currently filters by `session_id` becomes `filter_by(user_id=user_id, session_id=session_id)`. New cart creation supplies `user_id`:

```python
def get(self, user_id: str, session_id: str) -> dict:
    cart = (
        self.db.query(Cart)
        .filter_by(user_id=user_id, session_id=session_id)
        .first()
    )
    if cart is None:
        return {"session_id": session_id, "items": [], "total_amount": 0.0}
    items = []
    for item in cart.items:
        items.append({"product_id": item.product_id, "quantity": item.quantity})
    return {"session_id": session_id, "items": items, "total_amount": 0.0}

def add(self, user_id: str, session_id: str, product_id: str, quantity: int) -> dict:
    cart = (
        self.db.query(Cart)
        .filter_by(user_id=user_id, session_id=session_id)
        .first()
    )
    if cart is None:
        cart = Cart(user_id=user_id, session_id=session_id)
        self.db.add(cart)
        self.db.flush()
    ...  # rest unchanged
    return self.get(user_id, session_id)
```

Apply the same pattern to `update_quantity`, `remove`, `clear`. The internal `self.get(...)` calls at method ends must pass both args.

- [ ] **Step 4: Update `cart.py` service-layer signatures**

`Cart` (the service) wraps the repository; mirror the signatures: `get(user_id, session_id)`, `add(user_id, session_id, product_id, quantity)`, etc. The checkout flow already takes `session_id`; add `user_id` to its signature.

- [ ] **Step 5: Update existing cart tests**

In `server/tests/test_cart_db.py` and `server/tests/test_order_flow.py`, every call to repo/service methods that takes `session_id` now also takes `user_id="anonymous"` as the first positional.

- [ ] **Step 6: Run all cart tests**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_tenant_isolation.py tests/test_cart_db.py tests/test_order_flow.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add server/backend/app/repositories/cart_repository.py \
        server/backend/app/cart.py \
        server/tests/test_tenant_isolation.py \
        server/tests/test_cart_db.py \
        server/tests/test_order_flow.py
git commit -m "feat: dual-key cart repository and service

Task 4 of user switching and tenant isolation plan.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Wire user_id Into Agent Lifecycle And HTTP Endpoints

**Files:**
- Modify: `server/backend/app/agent.py`
- Modify: `server/backend/app/main.py`
- Create: `server/tests/test_sessions_latest_endpoint.py`
- Modify: `server/tests/test_api.py`
- Modify: `server/tests/test_agent_core.py`

**Interfaces:**
- Consumes: identity dependency from Task 1, repositories from Tasks 3-4.
- Produces:
  - `ShopGuideAgent.handle_message(user_id: str, session_id: str, message: str, ...)`
  - `ShopGuideAgent.stream_message(user_id: str, ..., request: ChatRequest)`
  - HTTP endpoint `GET /api/sessions/latest` returning `{"session_id": str}`.
  - All existing endpoints (`/api/cart/*`, `/api/feedback/*`, `/api/chat`, WS `/chat/stream`) accept `user_id` via `Depends(get_current_user_id)`.

- [ ] **Step 1: Write the failing latest-session endpoint test**

```python
# server/tests/test_sessions_latest_endpoint.py
"""GET /api/sessions/latest returns the user's most recent session id."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_latest_session_returns_new_id_for_unknown_user(api_client: TestClient) -> None:
    response = api_client.get("/api/sessions/latest", headers={"X-User-Id": "demo_user_a"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


def test_latest_session_returns_different_ids_per_user(api_client: TestClient) -> None:
    # Drive at least one chat turn for each user so each has a session row.
    api_client.post(
        "/api/chat/test",  # use whatever the existing test seam is
        headers={"X-User-Id": "demo_user_a"},
        json={"session_id": "s_a", "message": "hi"},
    )
    api_client.post(
        "/api/chat/test",
        headers={"X-User-Id": "demo_user_b"},
        json={"session_id": "s_b", "message": "hi"},
    )
    a = api_client.get("/api/sessions/latest", headers={"X-User-Id": "demo_user_a"}).json()
    b = api_client.get("/api/sessions/latest", headers={"X-User-Id": "demo_user_b"}).json()
    assert a["session_id"] == "s_a"
    assert b["session_id"] == "s_b"
```

If `api_client` fixture doesn't yet exist, copy the standard one from `tests/test_api.py`.

- [ ] **Step 2: Run to confirm failure**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q tests/test_sessions_latest_endpoint.py
```

Expected: FAIL — 404 or 500.

- [ ] **Step 3: Add the endpoint to `main.py`**

Near the existing `debug_session` route (around line 182), add:

```python
from .identity import get_current_user_id

@app.get("/api/sessions/latest")
def get_latest_session(user_id: str = Depends(get_current_user_id)):
    latest = session_store.get_latest_session_id(user_id) if hasattr(session_store, "get_latest_session_id") else None
    if latest is None:
        # No prior session; mint a stable demo-friendly id.
        latest = f"{user_id}_session_default"
    return {"session_id": latest}
```

And add `get_latest_session_id(user_id)` to `SessionStore` (passthrough to `self._repo.get_latest_session_id(user_id)` when DB-backed; for file mode, scan directory names).

- [ ] **Step 4: Add `user_id` Depends to every session/cart/feedback endpoint**

Each affected endpoint signature in `server/backend/app/main.py`:

```python
@app.get("/api/cart/{session_id}")
def get_cart(session_id: str, user_id: str = Depends(get_current_user_id)):
    return _cart_success(cart.get(user_id, session_id))

@app.post("/api/cart/add")
def add_cart(request: CartActionRequest, user_id: str = Depends(get_current_user_id)):
    ...
    cart.add(user_id, request.session_id, ...)
```

Repeat for `update_quantity`, `remove`, `clear`, `checkout`. Repeat for `/api/feedback/*` (pass `user_id` to `feedback_store.count` / `feedback_aggregator.aggregate` if those signatures are also dual-key-aware; if you decide feedback stays session-only for this spec, document it inline).

- [ ] **Step 5: WebSocket header propagation**

Find the WebSocket endpoint (around `main.py` line 200). Add:

```python
@app.websocket("/chat/stream")
async def chat_stream(websocket: WebSocket):
    await websocket.accept()
    raw_user_id = websocket.headers.get("X-User-Id")
    if raw_user_id is None:
        user_id = ANONYMOUS_USER_ID
    elif not is_valid_user_id(raw_user_id):
        await websocket.close(code=4400)
        return
    else:
        user_id = raw_user_id
    ...
    context = agent.sessions.get(user_id, request.session_id)
    ...
    session_store.save(user_id, request.session_id)
```

- [ ] **Step 6: Update `ShopGuideAgent` to thread user_id**

`ShopGuideAgent.handle_message`, `stream_message`, and any helper that calls `self.sessions.get(session_id)` must now call `self.sessions.get(user_id, session_id)` and `self.sessions.save(user_id, session_id)`. Add `user_id` as the first parameter.

- [ ] **Step 7: Update agent tests**

`server/tests/test_agent_core.py` — every call to `agent.handle_message(...)` / `agent.stream_message(...)` / `agent.sessions.get(...)` adds `"anonymous"` as the first arg.

- [ ] **Step 8: Run focused tests**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q \
    tests/test_sessions_latest_endpoint.py \
    tests/test_api.py \
    tests/test_agent_core.py \
    tests/test_websocket_protocol_envelope.py
```

Expected: PASS.

- [ ] **Step 9: Run the full backend regression**

```bash
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q
```

Expected: PASS with the count we had before this plan (397) plus the new tests from Tasks 1-5.

- [ ] **Step 10: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add server/backend/app/agent.py \
        server/backend/app/main.py \
        server/backend/app/session_store.py \
        server/tests/test_sessions_latest_endpoint.py \
        server/tests/test_api.py \
        server/tests/test_agent_core.py \
        server/tests/test_websocket_protocol_envelope.py
git commit -m "feat: thread user_id through agent and HTTP/WS endpoints

Task 5 of user switching and tenant isolation plan.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Client Mutable UserSession With Persistence

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/config/UserSession.kt`
- Create: `client/app/src/test/java/com/example/shopguideagent/config/UserSessionTest.kt`

**Interfaces:**
- Consumes: nothing (foundational client task).
- Produces:
  - `UserSession.PRESET_USERS: List<PresetUser>` (data class with `id`, `displayName`, `avatarHint`).
  - `UserSession.currentUserId: StateFlow<String>` — observable, starts at first preset.
  - `UserSession.setCurrentUserId(id: String)` — validates against `PRESET_USERS`, persists to SharedPreferences.
  - `UserSession.DEFAULT_SESSION_ID` kept as a per-user default constant.

- [ ] **Step 1: Write the failing UserSession tests**

```kotlin
// client/app/src/test/java/com/example/shopguideagent/config/UserSessionTest.kt
package com.example.shopguideagent.config

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Test
import org.mockito.kotlin.mock
import org.mockito.kotlin.whenever
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertTrue

class UserSessionTest {

    private fun fakePrefs(): SharedPreferences {
        val store = mutableMapOf<String, String?>()
        return mock<SharedPreferences>().also { prefs ->
            whenever(prefs.getString(org.mockito.kotlin.any(), org.mockito.kotlin.anyOrNull())).thenAnswer {
                store[it.arguments[0] as String] ?: (it.arguments[1] as String?)
            }
            val editor = mock<SharedPreferences.Editor>()
            whenever(editor.putString(org.mockito.kotlin.any(), org.mockito.kotlin.anyOrNull())).thenAnswer {
                store[it.arguments[0] as String] = it.arguments[1] as String?
                editor
            }
            whenever(editor.apply()).then {}
            whenever(prefs.edit()).thenReturn(editor)
        }
    }

    @Test
    fun `preset users contains exactly three demo entries`() {
        assertEquals(3, UserSession.PRESET_USERS.size)
        assertTrue(UserSession.PRESET_USERS.all { it.id.matches(Regex("^[a-z0-9_]{1,64}$")) })
    }

    @Test
    fun `cold start defaults to first preset user`() = runTest {
        val session = UserSession.create(fakePrefs())
        assertEquals(UserSession.PRESET_USERS.first().id, session.currentUserId.first())
    }

    @Test
    fun `setCurrentUserId persists and updates flow`() = runTest {
        val prefs = fakePrefs()
        val session = UserSession.create(prefs)
        session.setCurrentUserId(UserSession.PRESET_USERS[1].id)
        assertEquals(UserSession.PRESET_USERS[1].id, session.currentUserId.first())
        // A second instance backed by the same prefs sees the persisted value.
        val reopened = UserSession.create(prefs)
        assertEquals(UserSession.PRESET_USERS[1].id, reopened.currentUserId.first())
    }

    @Test
    fun `setCurrentUserId rejects unknown id`() {
        val session = UserSession.create(fakePrefs())
        assertFails { session.setCurrentUserId("not_a_preset") }
    }
}
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/huadabioa/houlong/SoulDance/client
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.config.UserSessionTest"
```

Expected: FAIL — class isn't a `class`, methods don't exist.

- [ ] **Step 3: Replace `UserSession`**

```kotlin
// client/app/src/main/java/com/example/shopguideagent/config/UserSession.kt
package com.example.shopguideagent.config

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class PresetUser(
    val id: String,
    val displayName: String,
    val avatarHint: String,
)

/**
 * 演示级用户身份单例。
 *
 * - PRESET_USERS：写死在客户端的 3 个用户。后端按需懒创建对应记录。
 * - currentUserId：可观察的当前用户 id，全应用唯一来源。
 * - setCurrentUserId：切换并持久化到 SharedPreferences。
 *
 * 不要在新代码里读 UserSession.USER_ID 之类的常量。
 */
class UserSession private constructor(
    private val preferences: SharedPreferences,
) {
    private val _currentUserId = MutableStateFlow(
        preferences.getString(KEY_CURRENT_USER_ID, null) ?: PRESET_USERS.first().id
    )
    val currentUserId: StateFlow<String> = _currentUserId.asStateFlow()

    fun setCurrentUserId(id: String) {
        require(PRESET_USERS.any { it.id == id }) { "Unknown preset user id: $id" }
        preferences.edit().putString(KEY_CURRENT_USER_ID, id).apply()
        _currentUserId.value = id
    }

    companion object {
        const val DEFAULT_SESSION_ID = "demo_session_001"

        val PRESET_USERS: List<PresetUser> = listOf(
            PresetUser("demo_user_a", "演示用户 A", "A"),
            PresetUser("demo_user_b", "演示用户 B", "B"),
            PresetUser("demo_user_c", "演示用户 C", "C"),
        )

        private const val KEY_CURRENT_USER_ID = "current_user_id"
        private const val PREFS_NAME = "shopguide_user_session"

        @Volatile private var instance: UserSession? = null

        fun create(preferences: SharedPreferences): UserSession =
            UserSession(preferences)

        fun get(context: Context): UserSession {
            val existing = instance
            if (existing != null) return existing
            synchronized(this) {
                val again = instance
                if (again != null) return again
                val prefs = context.applicationContext.getSharedPreferences(
                    PREFS_NAME, Context.MODE_PRIVATE
                )
                val created = UserSession(prefs)
                instance = created
                return created
            }
        }

        /**
         * Compatibility shim for the few callers that still expect a const.
         * Remove these once all call sites read currentUserId.
         */
        const val USER_ID = "demo_user_a"
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/huadabioa/houlong/SoulDance/client
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.config.UserSessionTest"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add client/app/src/main/java/com/example/shopguideagent/config/UserSession.kt \
        client/app/src/test/java/com/example/shopguideagent/config/UserSessionTest.kt
git commit -m "feat: mutable persisted UserSession with preset users

Task 6 of user switching and tenant isolation plan.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: OkHttp X-User-Id Interceptor

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/data/remote/UserIdHeaderInterceptor.kt`
- Create: `client/app/src/test/java/com/example/shopguideagent/data/remote/UserIdHeaderInterceptorTest.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiService.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/data/remote/SttApiService.kt`

**Interfaces:**
- Consumes: `UserSession.currentUserId` from Task 6.
- Produces:
  - `class UserIdHeaderInterceptor(private val userIdProvider: () -> String) : okhttp3.Interceptor`
  - Every OkHttp client built in the codebase includes this interceptor.
  - WebSocket upgrade requests carry `X-User-Id` in their `Request.Builder().header(...)`.

- [ ] **Step 1: Write the failing interceptor test**

```kotlin
// client/app/src/test/java/com/example/shopguideagent/data/remote/UserIdHeaderInterceptorTest.kt
package com.example.shopguideagent.data.remote

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals

class UserIdHeaderInterceptorTest {
    private lateinit var server: MockWebServer

    @Before fun setUp() { server = MockWebServer().apply { start() } }
    @After fun tearDown() { server.shutdown() }

    @Test
    fun `adds X-User-Id header from provider`() {
        server.enqueue(MockResponse().setBody("ok"))
        val client = OkHttpClient.Builder()
            .addInterceptor(UserIdHeaderInterceptor { "demo_user_b" })
            .build()
        client.newCall(Request.Builder().url(server.url("/")).build()).execute().close()
        val recorded = server.takeRequest()
        assertEquals("demo_user_b", recorded.getHeader("X-User-Id"))
    }

    @Test
    fun `does not overwrite an explicitly set header`() {
        server.enqueue(MockResponse().setBody("ok"))
        val client = OkHttpClient.Builder()
            .addInterceptor(UserIdHeaderInterceptor { "from_provider" })
            .build()
        val req = Request.Builder().url(server.url("/")).header("X-User-Id", "explicit").build()
        client.newCall(req).execute().close()
        assertEquals("explicit", server.takeRequest().getHeader("X-User-Id"))
    }
}
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/huadabioa/houlong/SoulDance/client
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.data.remote.UserIdHeaderInterceptorTest"
```

Expected: FAIL — class does not exist.

- [ ] **Step 3: Implement the interceptor**

```kotlin
// client/app/src/main/java/com/example/shopguideagent/data/remote/UserIdHeaderInterceptor.kt
package com.example.shopguideagent.data.remote

import okhttp3.Interceptor
import okhttp3.Response

/**
 * 为所有出站 HTTP 请求附加 X-User-Id。
 *
 * 单一身份传递通道：避免在 body 里再塞一份 user_id。
 * 如果调用方已经显式设置了 X-User-Id（例如测试），保留不覆盖。
 */
class UserIdHeaderInterceptor(
    private val userIdProvider: () -> String,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        if (original.header(HEADER_NAME) != null) {
            return chain.proceed(original)
        }
        val updated = original.newBuilder()
            .header(HEADER_NAME, userIdProvider())
            .build()
        return chain.proceed(updated)
    }

    companion object {
        const val HEADER_NAME = "X-User-Id"
    }
}
```

- [ ] **Step 4: Add the interceptor to all OkHttp builders**

In `RealtimeChatWebSocketClient.kt`, change the lazy `client` to:

```kotlin
private val client: OkHttpClient by lazy {
    val logging = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
    OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .addInterceptor(logging)
        .addInterceptor(UserIdHeaderInterceptor(userIdProvider))
        .build()
}
```

Take `userIdProvider: () -> String` as a constructor parameter and update call sites to pass `{ UserSession.get(context).currentUserId.value }`.

In the WebSocket request builder, also add the header on the upgrade request itself (some servers don't pass interceptor headers through the upgrade):

```kotlin
val request = Request.Builder()
    .url("${AppConfig.BASE_WS_URL}${AppConfig.WS_CHAT_PATH}")
    .header(UserIdHeaderInterceptor.HEADER_NAME, userIdProvider())
    .build()
```

Repeat the `addInterceptor(UserIdHeaderInterceptor(...))` change in `OrderApiService.kt` and `SttApiService.kt`. Add `userIdProvider` to their constructors with default `{ UserSession.get(applicationContext).currentUserId.value }`.

- [ ] **Step 5: Run the test to verify pass**

```bash
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.data.remote.UserIdHeaderInterceptorTest"
```

Expected: PASS.

- [ ] **Step 6: Run the full client unit-test suite**

```bash
cd /home/huadabioa/houlong/SoulDance/client
./gradlew :app:testDebugUnitTest
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add client/app/src/main/java/com/example/shopguideagent/data/remote/UserIdHeaderInterceptor.kt \
        client/app/src/main/java/com/example/shopguideagent/data/remote/RealtimeChatWebSocketClient.kt \
        client/app/src/main/java/com/example/shopguideagent/data/remote/OrderApiService.kt \
        client/app/src/main/java/com/example/shopguideagent/data/remote/SttApiService.kt \
        client/app/src/test/java/com/example/shopguideagent/data/remote/UserIdHeaderInterceptorTest.kt
git commit -m "feat: add X-User-Id OkHttp interceptor for REST and WS

Task 7 of user switching and tenant isolation plan.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Per-User Local State (Cart, firePoints) Rescoping

**Files:**
- Create: `client/app/src/main/java/com/example/shopguideagent/data/local/FirePointsStore.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt`
- Modify: `client/app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.kt`

**Interfaces:**
- Consumes: `UserSession.currentUserId` from Task 6.
- Produces:
  - `interface FirePointsStore { fun load(userId: String): Int; fun save(userId: String, value: Int) }`
  - `SharedPreferencesFirePointsStore` implementation, keyed `fire_points_<userId>`.
  - `CartViewModel(userIdProvider: () -> String, ...)` — drops the const default, reloads on user change.

- [ ] **Step 1: Write failing CartViewModel switch test**

Add to `client/app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.kt`:

```kotlin
@Test
fun `switching userId reloads items from per-user storage`() = runTest {
    val store = InMemoryCartPersistenceStore().apply {
        saveCartItems("demo_user_a", listOf(makeItem("apple", 1)))
        saveCartItems("demo_user_b", listOf(makeItem("banana", 2)))
    }
    var currentUser = "demo_user_a"
    val vm = CartViewModel(
        persistenceStore = store,
        userIdProvider = { currentUser },
        sessionId = "s1",
    )
    advanceUntilIdle()
    assertEquals(listOf("apple"), vm.uiState.value.items.map { it.productId })
    currentUser = "demo_user_b"
    vm.onCurrentUserChanged()
    advanceUntilIdle()
    assertEquals(listOf("banana"), vm.uiState.value.items.map { it.productId })
}
```

- [ ] **Step 2: Run to confirm failure**

```bash
./gradlew :app:testDebugUnitTest --tests "com.example.shopguideagent.vm.CartViewModelTest"
```

Expected: FAIL.

- [ ] **Step 3: Refactor `CartViewModel`**

Replace its `userId: String = UserSession.USER_ID` parameter with `userIdProvider: () -> String = { UserSession.get(...).currentUserId.value }`. Add `onCurrentUserChanged()` that re-runs `persistenceStore.loadCartItems(userIdProvider())`. In production, wire `viewModelScope.launch { UserSession.get(context).currentUserId.collect { onCurrentUserChanged() } }` from the ViewModel's `init`.

- [ ] **Step 4: Implement `FirePointsStore` and wire it into `SpriteHomeViewModel`**

```kotlin
// client/app/src/main/java/com/example/shopguideagent/data/local/FirePointsStore.kt
package com.example.shopguideagent.data.local

import android.content.SharedPreferences

interface FirePointsStore {
    fun load(userId: String): Int
    fun save(userId: String, value: Int)
}

class SharedPreferencesFirePointsStore(
    private val preferences: SharedPreferences,
) : FirePointsStore {
    override fun load(userId: String): Int = preferences.getInt(key(userId), DEFAULT)
    override fun save(userId: String, value: Int) {
        preferences.edit().putInt(key(userId), value).apply()
    }
    private fun key(userId: String): String = "fire_points_$userId"
    companion object { const val DEFAULT = 700 }
}

class InMemoryFirePointsStore : FirePointsStore {
    private val store = mutableMapOf<String, Int>()
    override fun load(userId: String): Int = store[userId] ?: 700
    override fun save(userId: String, value: Int) { store[userId] = value }
}
```

In `SpriteHomeViewModel`, replace the hardcoded `firePoints = 700` with a per-user load. Provide `onCurrentUserChanged()` that reloads.

- [ ] **Step 5: Run tests**

```bash
./gradlew :app:testDebugUnitTest
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add client/app/src/main/java/com/example/shopguideagent/data/local/FirePointsStore.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/home/SpriteHomeViewModel.kt \
        client/app/src/main/java/com/example/shopguideagent/vm/CartViewModel.kt \
        client/app/src/test/java/com/example/shopguideagent/vm/CartViewModelTest.kt
git commit -m "feat: rescope local cart and firePoints per user

Task 8 of user switching and tenant isolation plan.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: Footer Dropdown UI And Switch Flow

**Files:**
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/component/ChatHistoryDrawer.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt`
- Modify: `client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt`

**Interfaces:**
- Consumes: everything Tasks 6-8 produced.
- Produces:
  - `DrawerUserFooter` becomes a dropdown menu showing the current user, the other two presets, and the existing "更换头像" action.
  - On switch, `ChatViewModel.onUserSwitched(newUserId: String)` calls `setCurrentUserId`, hits `GET /api/sessions/latest`, closes the old WebSocket, opens a new one against the returned session id.

- [ ] **Step 1: Rewrite `DrawerUserFooter`**

Convert it from a single-action Surface into a dropdown anchor. Use `ExposedDropdownMenuBox` or a manual `DropdownMenu` keyed to a local `expanded` state. Items:

```kotlin
PRESET_USERS.forEach { user ->
    DropdownMenuItem(
        text = { Text("${user.displayName}${if (user.id == currentUserId) "（当前）" else ""}") },
        onClick = {
            expanded = false
            if (user.id != currentUserId) onUserSelected(user.id)
        },
    )
}
HorizontalDivider()
DropdownMenuItem(
    text = { Text("点击更换头像") },
    onClick = { expanded = false; onAvatarChangeRequested() },
)
```

`DrawerUserFooter` signature:

```kotlin
@Composable
private fun DrawerUserFooter(
    currentUserId: String,
    userAvatarUri: String?,
    onUserSelected: (String) -> Unit,
    onAvatarChangeRequested: () -> Unit,
)
```

- [ ] **Step 2: Wire the switch flow in `ChatViewModel`**

```kotlin
fun onUserSwitched(newUserId: String) {
    viewModelScope.launch {
        UserSession.get(application).setCurrentUserId(newUserId)
        val latest = sessionsApi.getLatest(newUserId)
        closeWebSocket()
        reopenWebSocketWith(latest.session_id)
        cartViewModel.onCurrentUserChanged()
        spriteHomeViewModel.onCurrentUserChanged()
    }
}
```

`sessionsApi.getLatest` is a small new Retrofit/raw-OkHttp call hitting `GET /api/sessions/latest`. The response: `data class LatestSession(val session_id: String)`.

- [ ] **Step 3: Wire `ChatScreen`**

Pass `currentUserId` (collected via `userSession.currentUserId.collectAsStateWithLifecycle()`) and `onUserSelected = chatViewModel::onUserSwitched` into `ChatHistoryDrawer`.

- [ ] **Step 4: Run the client test suite**

```bash
cd /home/huadabioa/houlong/SoulDance/client
./gradlew :app:testDebugUnitTest
```

Expected: PASS.

- [ ] **Step 5: Manual smoke (documented, not gated)**

Build and install the debug APK, manually verify:
- Drawer footer shows current user; tapping reveals a dropdown with 3 users + "更换头像".
- Selecting another user changes the displayed name; cart and firePoints content change.
- Reopening drawer after switch shows the new user as current.
- Killing and reopening the app restores the last selected user.

Document these results in the PR description.

- [ ] **Step 6: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add client/app/src/main/java/com/example/shopguideagent/ui/component/ChatHistoryDrawer.kt \
        client/app/src/main/java/com/example/shopguideagent/ui/screen/ChatScreen.kt \
        client/app/src/main/java/com/example/shopguideagent/vm/ChatViewModel.kt
git commit -m "feat: footer dropdown user switcher + sessions/latest flow

Task 9 of user switching and tenant isolation plan.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Acceptance Regression + Documentation

**Files:**
- No new files. Update `docs/superpowers/plans/2026-06-24-session-context-compression.md` Task 4 description to reference this plan as a prerequisite.

- [ ] **Step 1: Full backend regression**

```bash
cd /home/huadabioa/houlong/SoulDance/server
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m pytest -q
```

Expected: PASS. All previously-passing 397 tests still pass; plan adds Tasks 1-5 tests (~25-30 new).

- [ ] **Step 2: Full client regression**

```bash
cd /home/huadabioa/houlong/SoulDance/client
./gradlew :app:testDebugUnitTest
```

Expected: PASS.

- [ ] **Step 3: Migration dry-run against the dev SQLite**

```bash
SHOPGUIDE_DATABASE_URL="sqlite:///$PWD/server/data/dev.sqlite" \
/home/huadabioa/houlong/SoulDance/env/venv_shopguide_backend/bin/python -m backend.scripts.migrate_session_tenant_keys
```

Expected: prints non-zero migration counts on first run; running again prints `{'session_states': 0, 'carts': 0}`.

- [ ] **Step 4: Acceptance walkthrough against spec**

Open `docs/superpowers/specs/2026-06-24-user-switching-and-tenant-isolation-spec.md` and check each of the 12 Acceptance Criteria. Note any gaps; either fix or document.

- [ ] **Step 5: Update the compression plan's Task 4 note**

Edit `docs/superpowers/plans/2026-06-24-session-context-compression.md`. In its Task 4, prepend:

> Prerequisite: `2026-06-24-user-switching-and-tenant-isolation.md` Tasks 1-5 have shipped. `SessionRepository` is already keyed by `(user_id, session_id)`. This task only adds the new `SessionCompressionStateRow` table and the dual-key methods for it; do not re-derive the identity layer.

- [ ] **Step 6: Commit**

```bash
cd /home/huadabioa/houlong/SoulDance
git add docs/superpowers/plans/2026-06-24-session-context-compression.md
git commit -m "docs: cross-link compression Task 4 to user switching plan

Final task of user switching and tenant isolation plan.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review Summary

**Spec coverage check:**

| Acceptance criterion | Task |
|---|---|
| 1. Footer dropdown | 9 |
| 2. Persisted identity | 6 |
| 3. Header transport | 7 |
| 4. Server dependency | 1 |
| 5. Sessions latest endpoint | 5 |
| 6. DB constraint | 2 |
| 7. Repository signatures | 3, 4 |
| 8. Migration script | 2 |
| 9. Client local state rescoping | 8 |
| 10. Round-trip switch | 9 (manual smoke) + 8 (unit) |
| 11. Backward compat | 1, 3, 4, 5 |
| 12. Isolation tests | 3, 4 |

All 12 criteria are covered.

**Type/signature consistency check:**

- `get_current_user_id(request: Request) -> str` — Task 1 defines, Task 5 uses via `Depends`.
- `SessionRepository.get/save(user_id, ...)` — Task 3 defines, Task 5 uses (via `SessionStore`).
- `SessionRepository.get_latest_session_id(user_id) -> str | None` — Task 3 defines, Task 5 endpoint consumes.
- `migrate(engine) -> dict[str, int]` — Task 2 defines, Task 10 invokes.
- `UserSession.currentUserId: StateFlow<String>` — Task 6 defines, Tasks 7, 8, 9 consume.
- `UserSession.setCurrentUserId(id: String)` — Task 6, used in Task 9.
- `UserIdHeaderInterceptor(userIdProvider: () -> String)` — Task 7 defines, used in same Task across OkHttp builders.
- `FirePointsStore.load/save(userId: String, ...)` — Task 8 defines and uses.
- `CartViewModel(userIdProvider, ...)` — Task 8 defines, used in Task 9.

All cross-task references resolve.

**Placeholder scan:**

- No "TBD", "TODO", "fill in details".
- All test code blocks contain the actual test body.
- All command blocks are runnable as written.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-24-user-switching-and-tenant-isolation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task with a two-stage review between tasks. Best for a 10-task plan that touches both client and server.

**2. Inline Execution** — execute the plan in this session using executing-plans, with checkpoints between tasks for your review.

Which approach?
