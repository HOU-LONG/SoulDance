from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from ..models import SessionContext

logger = logging.getLogger(__name__)


class SessionStore:
    DEFAULT_TTL_DAYS = 7
    CURRENT_SCHEMA_VERSION = 1

    def __init__(
        self,
        persist_dir: str | Path | None = None,
        ttl_days: int = DEFAULT_TTL_DAYS,
        db_session=None,
    ):
        self._sessions: dict[tuple[str, str], SessionContext] = {}
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self.ttl_days = ttl_days
        self.db_session = db_session
        self._repo = None
        if self.db_session is not None:
            from ..repositories.session_repository import SessionRepository
            self._repo = SessionRepository(self.db_session)
        if self.persist_dir and self._repo is None:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._cleanup_expired()
            self._load_all()

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
                ctx.last_activity_at = datetime.now(timezone.utc).isoformat()
                self._repo.save(user_id, ctx)
            return
        if not self.persist_dir:
            return
        context = self._sessions.get(key)
        if context is None:
            return
        context.schema_version = self.CURRENT_SCHEMA_VERSION
        context.last_activity_at = datetime.now(timezone.utc).isoformat()
        path = self._path(user_id, session_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(context.model_dump_json(), encoding="utf-8")
        tmp_path.rename(path)

    def save_all(self) -> None:
        if self._repo is not None:
            for key in list(self._sessions):
                user_id, session_id = key
                self.save(user_id, session_id)
            return
        if not self.persist_dir:
            return
        for key in list(self._sessions):
            user_id, session_id = key
            self.save(user_id, session_id)

    def _path(self, user_id: str, session_id: str) -> Path:
        safe_user_id = user_id.replace("/", "_").replace("\\", "_")
        safe_session_id = session_id.replace("/", "_").replace("\\", "_")
        user_dir = self.persist_dir / safe_user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / f"{safe_session_id}.json"

    def _load_one(self, user_id: str, session_id: str) -> SessionContext | None:
        if not self.persist_dir:
            return None
        path = self._path(user_id, session_id)
        if not path.exists():
            return None
        try:
            data = path.read_text(encoding="utf-8")
            ctx = SessionContext.model_validate_json(data)
            if ctx.schema_version < self.CURRENT_SCHEMA_VERSION:
                ctx = self._migrate_if_needed(ctx)
            return ctx
        except Exception:
            logger.warning("Failed to load session %s/%s, backing up as corrupted", user_id, session_id, exc_info=True)
            corrupted_path = path.with_suffix(".corrupted")
            path.rename(corrupted_path)
            return None

    def _load_all(self) -> None:
        if not self.persist_dir:
            return
        for user_dir in self.persist_dir.iterdir():
            if not user_dir.is_dir():
                continue
            user_id = user_dir.name
            for path in user_dir.glob("*.json"):
                session_id = path.stem
                loaded = self._load_one(user_id, session_id)
                if loaded is not None:
                    self._sessions[(user_id, session_id)] = loaded

    def _cleanup_expired(self) -> None:
        if self._repo is not None:
            self._repo.cleanup_expired(self.ttl_days)
            return
        if not self.persist_dir:
            return
        now = time.time()
        cutoff = now - self.ttl_days * 86400
        for user_dir in self.persist_dir.iterdir():
            if not user_dir.is_dir():
                continue
            for path in user_dir.glob("*.json"):
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                except OSError:
                    pass
            try:
                if not any(user_dir.iterdir()):
                    user_dir.rmdir()
            except OSError:
                pass

    def get_latest_session_id(self, user_id: str) -> str | None:
        """获取用户最近使用的会话 ID。"""
        if self._repo is not None:
            return self._repo.get_latest_session_id(user_id)
        # Check in-memory sessions first (covers non-persistent / test mode)
        in_memory_latest = None
        in_memory_latest_time = None
        for (uid, sid), ctx in self._sessions.items():
            if uid == user_id:
                ctx_time = ctx.last_activity_at
                if ctx_time and (in_memory_latest_time is None or ctx_time > in_memory_latest_time):
                    in_memory_latest_time = ctx_time
                    in_memory_latest = sid
        if in_memory_latest is not None:
            return in_memory_latest
        if not self.persist_dir:
            return None
        # For file mode, find the most recently modified session for the user
        user_dir = self.persist_dir / user_id.replace("/", "_").replace("\\", "_")
        if not user_dir.exists():
            return None
        latest_path = None
        latest_mtime = 0.0
        for path in user_dir.glob("*.json"):
            mtime = path.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_path = path
        if latest_path:
            return latest_path.stem
        return None

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

    def checkpoint(self, user_id: str, session_id: str, stage: str) -> None:
        """回合级自动保存。走 get() 而非私有字典，正确支持 repo/file/in-memory。

        先通过 get() 确保 session 在 _sessions 中存在（repo 模式会从 DB 加载），
        然后更新 checkpoint_stage，最后调用 save() 持久化。
        """
        try:
            ctx = self.get(user_id, session_id)
            ctx.state.checkpoint_stage = stage
            self.save(user_id, session_id)
        except Exception:
            logger.warning(f"[checkpoint] save failed for {user_id}/{session_id}", exc_info=True)

    def recover(self, user_id: str, session_id: str):
        """恢复会话，返回 SessionRecovery 或 None。"""
        from ..models import SessionRecovery
        try:
            ctx = self.get(user_id, session_id)
        except Exception:
            return None

        stage = ctx.state.checkpoint_stage
        has_history = bool(ctx.dialog_turns)

        if stage == "turn_start":
            return SessionRecovery(
                user_message_restored=True, products_cached=False,
                hint="你刚才的消息我已收到，正在重新理解...",
            )
        elif stage == "post_retrieve":
            return SessionRecovery(
                user_message_restored=True, products_cached=True,
                hint="刚才的检索结果已恢复，我继续为你分析...",
            )
        elif stage == "turn_end":
            return SessionRecovery(user_message_restored=True, products_cached=True, hint=None)
        elif has_history:
            return SessionRecovery(
                user_message_restored=True, products_cached=False,
                hint="对话历史已恢复，请告诉我你最后的问题。",
            )
        return None

    def _migrate_if_needed(self, ctx: SessionContext) -> SessionContext:
        # v1→current: no structural changes yet. When schema changes, add per-version
        # migration steps here before bumping CURRENT_SCHEMA_VERSION.
        ctx.schema_version = self.CURRENT_SCHEMA_VERSION
        return ctx
