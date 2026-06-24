from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.feedback_store import FeedbackStore
from backend.app.models import FeedbackEvent
from backend.app.order_service import OrderService
from backend.app.session_store import SessionStore
from backend.app.user_profile_store import UserProfileStore


@pytest.fixture(scope="function")
def db():
    # 使用 SQLite 内存数据库用于无外部 DB 环境的测试
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
    Base.metadata.drop_all(bind=engine)


# 为 OrderService 提供一个 mock cart_service
class _MockCartService:
    def __init__(self):
        self._items = {}

    def get(self, session_id: str) -> dict:
        items = []
        total = 0.0
        for pid, qty in self._items.get(session_id, {}).items():
            items.append({
                "product_id": pid,
                "name": f"Product {pid}",
                "price": 100.0,
                "quantity": qty,
                "amount": 100.0 * qty,
            })
            total += 100.0 * qty
        return {"session_id": session_id, "items": items, "total_amount": total}

    def checkout(self, session_id: str, idempotency_key: str | None = None) -> dict:
        self._items[session_id] = {}
        return {"status": "ok"}

    def add(self, session_id: str, product_id: str, quantity: int = 1, idempotency_key: str | None = None) -> dict:
        if session_id not in self._items:
            self._items[session_id] = {}
        self._items[session_id][product_id] = self._items[session_id].get(product_id, 0) + quantity
        return self.get(session_id)


@pytest.fixture
def mock_cart():
    return _MockCartService()


def test_session_store_roundtrip(db):
    store = SessionStore(db_session=db)
    ctx = store.get("anonymous", "sess_1")
    ctx.state.dialog_state.turn_index = 5
    store.save("anonymous", "sess_1")
    reloaded = store.get("anonymous", "sess_1")
    assert reloaded.state.dialog_state.turn_index == 5


def test_feedback_store_roundtrip(db):
    store = FeedbackStore(db_session=db)
    store.record(FeedbackEvent(session_id="s1", signal_type="add_to_cart", product_id="p1"))
    events = store.get_all_events("s1")
    assert len(events) == 1
    assert events[0].product_id == "p1"


def test_user_profile_store_roundtrip(db):
    store = UserProfileStore(db_session=db)
    profile = store.get("u1")
    profile.total_ratings = 3
    store.save(profile)
    reloaded = store.get("u1")
    assert reloaded.total_ratings == 3


def test_order_service_checkout(db, mock_cart):
    # 先往 mock cart 里加商品
    mock_cart.add("s1", "p1", 2)
    service = OrderService(mock_cart, db_session=db)
    order = service.initiate_checkout("s1")
    assert order.status == "address_required"
    assert order.total_amount == 200.0
    assert len(order.items) == 1
    assert order.items[0].product_id == "p1"

    # 选择地址
    updated = service.select_address(order.order_id, "addr_1")
    assert updated.status == "awaiting_confirmation"
    assert updated.address is not None
    assert updated.confirmation_token is not None

    # 确认订单
    confirmed = service.confirm_order(
        order.order_id,
        confirmation_token=updated.confirmation_token,
        idempotency_key="key_1",
    )
    assert confirmed.status == "completed"

    # 幂等测试
    same = service.confirm_order(
        order.order_id,
        confirmation_token=updated.confirmation_token,
        idempotency_key="key_1",
    )
    assert same.status == "completed"


def test_order_service_get_not_found(db, mock_cart):
    service = OrderService(mock_cart, db_session=db)
    from backend.app.order_service import OrderNotFoundError
    with pytest.raises(OrderNotFoundError):
        service.select_address("nonexistent", "addr_1")
