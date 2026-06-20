from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import CartItem, Cart


class CartRepository:
    def __init__(self, db: Session):
        self.db = db

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def get(self, session_id: str) -> dict:
        cart = self.db.query(Cart).filter_by(session_id=session_id).first()
        if cart is None:
            return {"session_id": session_id, "items": [], "total_amount": 0.0}
        items = []
        total = 0.0
        for item in cart.items:
            # 商品价格从 product map 取，这里 repository 只返回原始结构
            items.append({
                "product_id": item.product_id,
                "quantity": item.quantity,
            })
            # total 由 service 层计算
        return {"session_id": session_id, "items": items, "total_amount": total}

    def add(self, session_id: str, product_id: str, quantity: int) -> dict:
        cart = self.db.query(Cart).filter_by(session_id=session_id).first()
        if cart is None:
            cart = Cart(session_id=session_id)
            self.db.add(cart)
            self.db.flush()
        item = next((i for i in cart.items if i.product_id == product_id), None)
        if item is None:
            item = CartItem(cart_id=cart.id, product_id=product_id, quantity=quantity)
            self.db.add(item)
        else:
            item.quantity += quantity
        cart.updated_at = self._now()
        self.db.flush()
        return self.get(session_id)

    def update_quantity(self, session_id: str, product_id: str, quantity: int) -> dict:
        cart = self.db.query(Cart).filter_by(session_id=session_id).first()
        if cart is None:
            return self.get(session_id)
        item = next((i for i in cart.items if i.product_id == product_id), None)
        if quantity == 0:
            if item:
                self.db.delete(item)
                self.db.flush()
                self.db.expire(cart, ["items"])
        elif item is not None:
            item.quantity = quantity
        else:
            item = CartItem(cart_id=cart.id, product_id=product_id, quantity=quantity)
            self.db.add(item)
        cart.updated_at = self._now()
        self.db.flush()
        return self.get(session_id)

    def remove(self, session_id: str, product_id: str) -> dict:
        cart = self.db.query(Cart).filter_by(session_id=session_id).first()
        if cart is None:
            return self.get(session_id)
        item = next((i for i in cart.items if i.product_id == product_id), None)
        if item:
            self.db.delete(item)
            self.db.flush()
            self.db.expire(cart, ["items"])
        cart.updated_at = self._now()
        self.db.flush()
        return self.get(session_id)

    def clear(self, session_id: str) -> dict:
        cart = self.db.query(Cart).filter_by(session_id=session_id).first()
        if cart:
            for item in list(cart.items):
                self.db.delete(item)
            self.db.flush()
            self.db.expire(cart, ["items"])
            cart.updated_at = self._now()
            self.db.flush()
        return self.get(session_id)

    def checkout(self, session_id: str) -> dict:
        return self.clear(session_id)
