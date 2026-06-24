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


def _migrate_sqlite_table(engine: Engine, table: str) -> int:
    """Rebuild `table` with a new schema and copy old rows in."""
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
            counts[table] = _migrate_sqlite_table(engine, table)
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
