from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .models import FeedbackEvent

logger = logging.getLogger(__name__)


class FeedbackStore:
    """反馈事件收集与 JSON 文件持久化。

    按 session_id 组织事件，支持内存缓存 + 磁盘持久化。
    """

    def __init__(self, persist_path: str | Path | None = None, db_session=None):
        self._events: dict[str, list[FeedbackEvent]] = {}
        self.persist_path = Path(persist_path) if persist_path else None
        self.db_session = db_session
        self._repo = None
        if self.db_session is not None:
            from .repositories.feedback_repository import FeedbackRepository
            self._repo = FeedbackRepository(self.db_session)
        if self.persist_path and self._repo is None:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    # ---- 写入 ----

    def record(self, event: FeedbackEvent) -> None:
        """记录一条反馈事件。自动填充 timestamp。"""
        if not event.timestamp:
            event.timestamp = datetime.now(timezone.utc).isoformat()
        if self._repo is not None:
            self._repo.record(event)
            return
        sid = event.session_id
        if sid not in self._events:
            self._events[sid] = []
        self._events[sid].append(event)
        # 上限保护
        if len(self._events[sid]) > 200:
            self._events[sid] = self._events[sid][-200:]
        self._save()

    # ---- 读取 ----

    def get_all_events(self, session_id: str) -> list[FeedbackEvent]:
        """获取 session 全部反馈事件。"""
        if self._repo is not None:
            return self._repo.get_all_events(session_id)
        return list(self._events.get(session_id, []))

    def get_events_by_type(self, session_id: str, signal_types: list[str]) -> list[FeedbackEvent]:
        """按信号类型过滤。"""
        if self._repo is not None:
            events = self._repo.get_all_events(session_id)
            return [e for e in events if e.signal_type in signal_types]
        return [
            e for e in self._events.get(session_id, [])
            if e.signal_type in signal_types
        ]

    def count(self, session_id: str) -> int:
        if self._repo is not None:
            return self._repo.count(session_id)
        return len(self._events.get(session_id, []))

    # ---- 持久化 ----

    def _load(self) -> None:
        if not self.persist_path or not self.persist_path.exists():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for sid, raw_events in data.items():
                    self._events[sid] = [FeedbackEvent.model_validate(e) for e in raw_events]
        except Exception:
            logger.warning("Failed to load feedback data, starting fresh", exc_info=True)
            self._events = {}

    def _save(self) -> None:
        if not self.persist_path:
            return
        payload = {
            sid: [e.model_dump(mode="json") for e in events]
            for sid, events in self._events.items()
        }
        self.persist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
