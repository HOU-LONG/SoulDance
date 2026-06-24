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
