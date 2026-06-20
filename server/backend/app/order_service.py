from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import Address, Order, OrderItem

logger = logging.getLogger(__name__)


MOCK_ADDRESSES = [
    Address(
        address_id="addr_1",
        name="张三",
        phone="138****1234",
        province="北京",
        city="北京市",
        detail="某某路100号",
        is_default=True,
    ),
    Address(
        address_id="addr_2",
        name="张三",
        phone="138****1234",
        province="上海",
        city="上海市",
        detail="某某大道200号",
        is_default=False,
    ),
]


class OrderService:
    def __init__(self, cart_service, persist_dir: str | Path | None = None):
        from .cart import CartService
        self._cart: CartService = cart_service
        self._orders: dict[str, list[Order]] = {}
        self.persist_dir = Path(persist_dir) if persist_dir else None
        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def initiate_checkout(self, session_id: str) -> Order:
        cart = self._cart.get(session_id)
        items = [
            OrderItem(
                product_id=item["product_id"],
                title=item["name"],
                price=item["price"],
                quantity=item["quantity"],
                amount=item["amount"],
            )
            for item in cart["items"]
        ]
        order = Order(
            order_id=f"order_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            status="pending_address",
            items=items,
            total_amount=cart["total_amount"],
        )
        self._save_order(order)
        return order

    def select_address(self, order_id: str, address_id: str) -> Order | None:
        order = self._get_order(order_id)
        if not order:
            return None
        address = next((a for a in MOCK_ADDRESSES if a.address_id == address_id), None)
        if address:
            order.address = address
            order.status = "pending_confirm"
            self._save_order(order)
        return order

    def confirm_order(self, order_id: str) -> Order | None:
        order = self._get_order(order_id)
        if not order or order.status != "pending_confirm":
            return None
        self._cart.checkout(order.session_id)
        order.status = "paid"
        self._save_order(order)
        return order

    def get_addresses(self) -> list[Address]:
        return list(MOCK_ADDRESSES)

    def _get_order(self, order_id: str) -> Order | None:
        for orders in self._orders.values():
            for order in orders:
                if order.order_id == order_id:
                    return order
        return None

    def _save_order(self, order: Order) -> None:
        sid = order.session_id
        if sid not in self._orders:
            self._orders[sid] = []
        existing = [o for o in self._orders[sid] if o.order_id == order.order_id]
        if existing:
            idx = self._orders[sid].index(existing[0])
            self._orders[sid][idx] = order
        else:
            self._orders[sid].append(order)
        self._save()

    def _save(self) -> None:
        if not self.persist_dir:
            return
        path = self.persist_dir / "orders.json"
        data = {
            sid: [o.model_dump(mode="json") for o in orders]
            for sid, orders in self._orders.items()
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self.persist_dir:
            return
        path = self.persist_dir / "orders.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for sid, orders_data in data.items():
                self._orders[sid] = [Order.model_validate(o) for o in orders_data]
        except Exception:
            logger.warning("Failed to load order data, resetting", exc_info=True)
            self._orders = {}
