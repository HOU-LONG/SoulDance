from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from .models import SessionContext

logger = logging.getLogger(__name__)


class SessionStore:
    DEFAULT_TTL_DAYS = 7
    CURRENT_SCHEMA_VERSION = 1

    def __init__(self, persist_dir: str | Path | None = None, ttl_days: int = DEFAULT_TTL_DAYS):
        self._sessions: dict[str, SessionContext] = {}
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self.ttl_days = ttl_days
        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._cleanup_expired()
            self._load_all()

    def get(self, session_id: str) -> SessionContext:
        if session_id not in self._sessions:
            loaded = self._load_one(session_id)
            self._sessions[session_id] = loaded if loaded else SessionContext(session_id=session_id)
        ctx = self._sessions[session_id]
        ctx.last_activity_at = datetime.now(timezone.utc).isoformat()
        return ctx

    def save(self, session_id: str) -> None:
        if not self.persist_dir:
            return
        context = self._sessions.get(session_id)
        if context is None:
            return
        context.schema_version = self.CURRENT_SCHEMA_VERSION
        context.last_activity_at = datetime.now(timezone.utc).isoformat()
        path = self._path(session_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(context.model_dump_json(), encoding="utf-8")
        tmp_path.rename(path)

    def save_all(self) -> None:
        if not self.persist_dir:
            return
        for session_id in list(self._sessions):
            self.save(session_id)

    def _path(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return self.persist_dir / f"{safe_id}.json"

    def _load_one(self, session_id: str) -> SessionContext | None:
        if not self.persist_dir:
            return None
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            data = path.read_text(encoding="utf-8")
            ctx = SessionContext.model_validate_json(data)
            if ctx.schema_version < self.CURRENT_SCHEMA_VERSION:
                ctx = self._migrate_if_needed(ctx)
            return ctx
        except Exception:
            logger.warning("Failed to load session %s, backing up as corrupted", session_id, exc_info=True)
            corrupted_path = path.with_suffix(".corrupted")
            path.rename(corrupted_path)
            return None

    def _load_all(self) -> None:
        if not self.persist_dir:
            return
        for path in self.persist_dir.glob("*.json"):
            session_id = path.stem
            loaded = self._load_one(session_id)
            if loaded is not None:
                self._sessions[session_id] = loaded

    def _cleanup_expired(self) -> None:
        if not self.persist_dir:
            return
        now = time.time()
        cutoff = now - self.ttl_days * 86400
        for path in self.persist_dir.glob("*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    def _migrate_if_needed(self, ctx: SessionContext) -> SessionContext:
        # v1→current: no structural changes yet. When schema changes, add per-version
        # migration steps here before bumping CURRENT_SCHEMA_VERSION.
        ctx.schema_version = self.CURRENT_SCHEMA_VERSION
        return ctx
