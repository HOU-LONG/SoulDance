from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db.models import SessionState
from ..models import SessionContext


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, session_id: str) -> SessionContext | None:
        row = self.db.query(SessionState).filter_by(session_id=session_id).first()
        if row is None:
            return None
        return SessionContext.model_validate(row.state_json)

    def save(self, context: SessionContext) -> None:
        context.last_activity_at = datetime.now(timezone.utc).isoformat()
        row = self.db.query(SessionState).filter_by(session_id=context.session_id).first()
        if row is None:
            row = SessionState(session_id=context.session_id)
            self.db.add(row)
        row.state_json = context.model_dump(mode="json")
        row.schema_version = context.schema_version
        row.last_activity_at = datetime.now(timezone.utc)
        self.db.flush()

    def cleanup_expired(self, ttl_days: int) -> None:
        # SQLite 使用 julianday 计算过期时间
        cutoff_sql = text(f"julianday('now') - {ttl_days}")
        self.db.query(SessionState).filter(
            SessionState.last_activity_at < cutoff_sql
        ).delete(synchronize_session=False)
        self.db.flush()
