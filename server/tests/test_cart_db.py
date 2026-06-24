from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.cart import CartService
from backend.app.db.base import Base
from backend.app.db.models import CartItem, Cart
from backend.app.models import Product


@pytest.fixture(scope="function")
def db():
    # 使用 SQLite 内存数据库作为 PostgreSQL 的替代，用于无外部 DB 环境的测试
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def products():
    return [
        Product(product_id="p1", title="A", brand="B", category="c", sub_category="s", price=100.0, image_path=""),
    ]


def test_cart_add_and_get(db, products):
    service = CartService(products, db_session=db)
    service.add("anonymous", "s1", "p1", 2)
    snapshot = service.get("anonymous", "s1")
    assert len(snapshot["items"]) == 1
    assert snapshot["items"][0]["quantity"] == 2
    assert snapshot["total_amount"] == 200.0


def test_cart_update_quantity(db, products):
    service = CartService(products, db_session=db)
    service.add("anonymous", "s1", "p1", 2)
    service.update_quantity("anonymous", "s1", "p1", 5)
    snapshot = service.get("anonymous", "s1")
    assert snapshot["items"][0]["quantity"] == 5
    assert snapshot["total_amount"] == 500.0


def test_cart_remove(db, products):
    service = CartService(products, db_session=db)
    service.add("anonymous", "s1", "p1", 2)
    service.remove("anonymous", "s1", "p1")
    snapshot = service.get("anonymous", "s1")
    assert len(snapshot["items"]) == 0
    assert snapshot["total_amount"] == 0.0


def test_cart_clear(db, products):
    service = CartService(products, db_session=db)
    service.add("anonymous", "s1", "p1", 2)
    service.clear("anonymous", "s1")
    snapshot = service.get("anonymous", "s1")
    assert len(snapshot["items"]) == 0
    assert snapshot["total_amount"] == 0.0


def test_cart_checkout(db, products):
    service = CartService(products, db_session=db)
    service.add("anonymous", "s1", "p1", 2)
    result = service.checkout("anonymous", "s1")
    assert result["status"] == "ok"
    assert result["paid_amount"] == 200.0
    # checkout 后购物车应被清空
    snapshot = service.get("anonymous", "s1")
    assert len(snapshot["items"]) == 0


def test_cart_add_same_product_accumulates(db, products):
    service = CartService(products, db_session=db)
    service.add("anonymous", "s1", "p1", 2)
    service.add("anonymous", "s1", "p1", 3)
    snapshot = service.get("anonymous", "s1")
    assert snapshot["items"][0]["quantity"] == 5
    assert snapshot["total_amount"] == 500.0


def test_cart_idempotency(db, products):
    service = CartService(products, db_session=db)
    result1 = service.add("anonymous", "s1", "p1", 2, idempotency_key="key1")
    result2 = service.add("anonymous", "s1", "p1", 99, idempotency_key="key1")
    # 第二次应返回第一次的结果（幂等）
    assert result2 == result1
    # 数据库里实际数量应该是 2（因为第二次被幂等拦截了）
    snapshot = service.get("anonymous", "s1")
    assert snapshot["items"][0]["quantity"] == 2
