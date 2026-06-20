from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import FeedbackEvent
from ..models import FeedbackEvent as FeedbackEventModel


class FeedbackRepository:
    def __init__(self, db: Session):
        self.db = db

    def record(self, event: FeedbackEventModel) -> None:
        if not event.timestamp:
            event.timestamp = datetime.now(timezone.utc).isoformat()
        row = FeedbackEvent(
            session_id=event.session_id,
            signal_type=event.signal_type,
            product_id=event.product_id,
            rating=event.rating,
            action_label=event.action_label,
            context=event.context,
            timestamp=datetime.fromisoformat(event.timestamp),
        )
        self.db.add(row)
        self.db.flush()

    def get_all_events(self, session_id: str) -> list[FeedbackEventModel]:
        rows = (
            self.db.query(FeedbackEvent)
            .filter_by(session_id=session_id)
            .order_by(FeedbackEvent.timestamp)
            .all()
        )
        return [self._to_model(r) for r in rows]

    def count(self, session_id: str) -> int:
        return self.db.query(FeedbackEvent).filter_by(session_id=session_id).count()

    def _to_model(self, row: FeedbackEvent) -> FeedbackEventModel:
        return FeedbackEventModel(
            session_id=row.session_id,
            signal_type=row.signal_type,
            product_id=row.product_id,
            rating=row.rating,
            action_label=row.action_label,
            context=row.context,
            timestamp=row.timestamp.isoformat(),
        )
