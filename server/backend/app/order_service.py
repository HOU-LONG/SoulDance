from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import Address, Order, OrderItem

logger = logging.getLogger(__name__)


ORDER_STATUS_ADDRESS_REQUIRED = "address_required"
ORDER_STATUS_AWAITING_CONFIRMATION = "awaiting_confirmation"
ORDER_STATUS_COMPLETED = "completed"

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


class OrderError(Exception):
    status_code = 400


class OrderNotFoundError(OrderError):
    status_code = 404


class OrderConflictError(OrderError):
    status_code = 409


class OrderService:
    def __init__(
        self,
        cart_service,
        persist_dir: str | Path | None = None,
        db_session=None,
    ):
        from .cart import CartService

        self._cart: CartService = cart_service
        self._orders: dict[str, list[Order]] = {}
        self._confirm_results: dict[str, dict[str, Order]] = {}
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self.db_session = db_session
        self._repo = None
        if self.db_session is not None:
            from .repositories.order_repository import OrderRepository
            self._repo = OrderRepository(self.db_session)
        if self.persist_dir and self._repo is None:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def initiate_checkout(self, session_id: str) -> Order:
        cart = self._cart.get(session_id)
        if not cart["items"]:
            raise OrderError("购物车为空，无法创建订单预览。")
        now = _now()
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
            status=ORDER_STATUS_ADDRESS_REQUIRED,
            items=items,
            total_amount=cart["total_amount"],
            created_at=now,
            updated_at=now,
        )
        self._save_order(order)
        return order

    def select_address(self, order_id: str, address_id: str) -> Order:
        order = self._require_order(order_id)
        if order.status == ORDER_STATUS_COMPLETED:
            raise OrderConflictError("订单已完成，不能修改地址。")
        address = next((a for a in MOCK_ADDRESSES if a.address_id == address_id), None)
        if address is None:
            raise OrderError("address not found")
        order.address = address
        order.status = ORDER_STATUS_AWAITING_CONFIRMATION
        order.confirmation_token = secrets.token_urlsafe(24)
        order.updated_at = _now()
        self._save_order(order)
        return order

    def confirm_order(
        self,
        order_id: str,
        confirmation_token: str | None,
        idempotency_key: str | None,
    ) -> Order:
        order = self._require_order(order_id)
        existing = self._get_confirm_result(order, idempotency_key)
        if existing is not None:
            return existing
        if order.status == ORDER_STATUS_COMPLETED:
            raise OrderConflictError("订单已完成。")
        if order.status != ORDER_STATUS_AWAITING_CONFIRMATION:
            raise OrderError("订单还未进入确认状态。")
        if not confirmation_token or confirmation_token != order.confirmation_token:
            raise OrderError("confirmation_token invalid")
        self._cart.checkout(order.session_id, idempotency_key=f"order:{order.order_id}")
        order.status = ORDER_STATUS_COMPLETED
        order.idempotency_key = idempotency_key
        order.updated_at = _now()
        self._remember_confirm_result(order, idempotency_key)
        self._save_order(order)
        return order

    def get_addresses(self) -> list[Address]:
        return list(MOCK_ADDRESSES)

    def _require_order(self, order_id: str) -> Order:
        order = self._get_order(order_id)
        if order is None:
            raise OrderNotFoundError("order not found")
        return order

    def _get_order(self, order_id: str) -> Order | None:
        if self._repo is not None:
            row = self._repo.get(order_id)
            if row is None:
                return None
            # 将 ORM 行转换为 Pydantic Order 模型
            return Order(
                order_id=row.order_id,
                session_id=row.session_id,
                status=row.status,
                items=[
                    OrderItem(
                        product_id=item.product_id,
                        title=item.title,
                        price=item.price,
                        quantity=item.quantity,
                        amount=item.amount,
                    )
                    for item in row.items
                ],
                total_amount=row.total_amount,
                address=Address.model_validate(row.address) if row.address else None,
                confirmation_token=row.confirmation_token,
                idempotency_key=row.idempotency_key,
                created_at=row.created_at.isoformat() if row.created_at else "",
                updated_at=row.updated_at.isoformat() if row.updated_at else "",
            )
        for orders in self._orders.values():
            for order in orders:
                if order.order_id == order_id:
                    return order
        return None

    def _get_confirm_result(self, order: Order, key: str | None) -> Order | None:
        if not key:
            return None
        return self._confirm_results.get(order.order_id, {}).get(key)

    def _remember_confirm_result(self, order: Order, key: str | None) -> None:
        if not key:
            return
        self._confirm_results.setdefault(order.order_id, {})[key] = order.model_copy(deep=True)

    def _save_order(self, order: Order) -> None:
        if self._repo is not None:
            from backend.app.db.models import Order as OrderOrm, OrderItem as OrderItemOrm
            existing = self._repo.get(order.order_id)
            if existing is None:
                orm_order = OrderOrm(
                    order_id=order.order_id,
                    session_id=order.session_id,
                    status=order.status,
                    total_amount=order.total_amount,
                    confirmation_token=order.confirmation_token,
                    idempotency_key=order.idempotency_key,
                    address=order.address.model_dump(mode="json") if order.address else None,
                    created_at=datetime.fromisoformat(order.created_at) if order.created_at else datetime.now(timezone.utc),
                    updated_at=datetime.fromisoformat(order.updated_at) if order.updated_at else datetime.now(timezone.utc),
                )
                for item in order.items:
                    orm_item = OrderItemOrm(
                        order_id=order.order_id,
                        product_id=item.product_id,
                        title=item.title,
                        price=item.price,
                        quantity=item.quantity,
                        amount=item.amount,
                    )
                    orm_order.items.append(orm_item)
                self._repo.save(orm_order)
            else:
                existing.status = order.status
                existing.total_amount = order.total_amount
                existing.confirmation_token = order.confirmation_token
                existing.idempotency_key = order.idempotency_key
                existing.address = order.address.model_dump(mode="json") if order.address else None
                existing.updated_at = datetime.fromisoformat(order.updated_at) if order.updated_at else datetime.now(timezone.utc)
                # 简单处理：删除旧 items 再重建
                for item in list(existing.items):
                    self.db_session.delete(item)
                for item in order.items:
                    orm_item = OrderItemOrm(
                        order_id=order.order_id,
                        product_id=item.product_id,
                        title=item.title,
                        price=item.price,
                        quantity=item.quantity,
                        amount=item.amount,
                    )
                    existing.items.append(orm_item)
                self.db_session.flush()
            return
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
        path = self._orders_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "orders": {
                sid: [o.model_dump(mode="json") for o in orders]
                for sid, orders in self._orders.items()
            },
            "confirm_results": {
                order_id: {key: order.model_dump(mode="json") for key, order in results.items()}
                for order_id, results in self._confirm_results.items()
            },
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self.persist_dir:
            return
        path = self._orders_path()
        if not path.exists():
            legacy_path = self.persist_dir / "orders.json"
            if legacy_path.exists():
                path = legacy_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "orders" in data:
                order_data = data.get("orders", {})
                confirm_data = data.get("confirm_results", {})
            else:
                order_data = data
                confirm_data = {}
            for sid, orders_data in order_data.items():
                self._orders[sid] = [Order.model_validate(o) for o in orders_data]
            for order_id, results in confirm_data.items():
                if isinstance(results, dict):
                    self._confirm_results[order_id] = {
                        str(key): Order.model_validate(value)
                        for key, value in results.items()
                        if isinstance(value, dict)
                    }
        except Exception:
            logger.warning("Failed to load order data, resetting", exc_info=True)
            self._orders = {}
            self._confirm_results = {}

    def _orders_path(self) -> Path:
        assert self.persist_dir is not None
        return self.persist_dir / "orders" / "orders.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
