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
