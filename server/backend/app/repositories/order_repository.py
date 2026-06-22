from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import Order, OrderItem


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, order_id: str) -> Order | None:
        return self.db.query(Order).filter_by(order_id=order_id).first()

    def save(self, order: Order) -> None:
        existing = self.db.query(Order).filter_by(order_id=order.order_id).first()
        if existing is None:
            self.db.add(order)
        self.db.flush()

    def list_by_session(self, session_id: str) -> list[Order]:
        return self.db.query(Order).filter_by(session_id=session_id).all()
