from __future__ import annotations

import copy
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .image_assets import product_image_url_auto as product_image_url
from .models import Product

logger = logging.getLogger(__name__)


MAX_CART_QUANTITY = 99


class CartService:
    def __init__(
        self,
        products: list[Product],
        persist_path: str | Path | None = None,
        db_session=None,
    ):
        self.products = {product.product_id: product for product in products}
        self._carts: dict[str, dict[str, int]] = {}
        self._audit_log: dict[str, list[dict]] = {}
        self._idempotency_results: dict[str, dict[str, dict]] = {}
        self.persist_path = Path(persist_path) if persist_path else None
        self.db_session = db_session
        self._repo = None
        if self.db_session is not None:
            from .repositories.cart_repository import CartRepository
            self._repo = CartRepository(self.db_session)
        if self.persist_path and self._repo is None:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    # ... 保留原有 _load/_save/文件逻辑不变 ...

    def add(
        self,
        session_id: str,
        product_id: str,
        quantity: int = 1,
        idempotency_key: str | None = None,
    ) -> dict:
        if self._repo is not None:
            return self._db_add(session_id, product_id, quantity, idempotency_key)
        return self._file_add(session_id, product_id, quantity, idempotency_key)

    def _db_add(self, session_id, product_id, quantity, idempotency_key):
        existing = self._get_idempotency_result(session_id, idempotency_key)
        if existing is not None:
            return existing
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=False)
        self._repo.add(session_id, product_id, quantity)
        snapshot = self._db_get(session_id)
        self._remember_idempotency_result(session_id, idempotency_key, snapshot)
        return snapshot

    def _db_get(self, session_id):
        raw = self._repo.get(session_id)
        items = []
        total = 0.0
        for row in raw["items"]:
            product_id = row["product_id"]
            quantity = row["quantity"]
            product = self.products.get(product_id)
            if product is None:
                continue
            amount = product.price * quantity
            total += amount
            items.append({
                "product_id": product_id,
                "name": product.title,
                "brand": product.brand,
                "price": product.price,
                "quantity": quantity,
                "amount": amount,
                "main_image_url": product_image_url(product.image_path),
                "image_url": product_image_url(product.image_path),
                "selected": True,
            })
        return {"session_id": session_id, "items": items, "total_amount": total}

    def get(self, session_id: str) -> dict:
        if self._repo is not None:
            return self._db_get(session_id)
        return self._file_get(session_id)

    def update_quantity(self, session_id: str, product_id: str, quantity: int) -> dict:
        if self._repo is not None:
            return self._db_update_quantity(session_id, product_id, quantity)
        return self._file_update_quantity(session_id, product_id, quantity)

    def remove(self, session_id: str, product_id: str) -> dict:
        if self._repo is not None:
            return self._db_remove(session_id, product_id)
        return self._file_remove(session_id, product_id)

    def clear(self, session_id: str) -> dict:
        if self._repo is not None:
            return self._db_clear(session_id)
        return self._file_clear(session_id)

    def checkout(self, session_id: str, idempotency_key: str | None = None) -> dict:
        if self._repo is not None:
            return self._db_checkout(session_id, idempotency_key)
        return self._file_checkout(session_id, idempotency_key)

    def _db_update_quantity(self, session_id, product_id, quantity):
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=True)
        self._repo.update_quantity(session_id, product_id, quantity)
        return self._db_get(session_id)

    def _db_remove(self, session_id, product_id):
        self._validate_product(product_id)
        self._repo.remove(session_id, product_id)
        return self._db_get(session_id)

    def _db_clear(self, session_id):
        self._repo.clear(session_id)
        return self._db_get(session_id)

    def _db_checkout(self, session_id, idempotency_key):
        existing = self._get_idempotency_result(session_id, idempotency_key)
        if existing is not None:
            return existing
        snapshot = self._db_get(session_id)
        self._repo.checkout(session_id)
        result = {
            "status": "ok",
            "session_id": session_id,
            "order_id": f"demo_order_{session_id}_{uuid.uuid4().hex[:8]}",
            "paid_amount": snapshot["total_amount"],
            "items": snapshot["items"],
        }
        self._remember_idempotency_result(session_id, idempotency_key, result)
        return result

    def _file_add(self, session_id, product_id, quantity, idempotency_key):
        existing = self._get_idempotency_result(session_id, idempotency_key)
        if existing is not None:
            return existing
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=False)
        cart = self._carts.setdefault(session_id, {})
        cart[product_id] = cart.get(product_id, 0) + quantity
        self._log_action(session_id, "add", product_id, cart[product_id])
        snapshot = self.get(session_id)
        self._remember_idempotency_result(session_id, idempotency_key, snapshot)
        self._save()
        return snapshot

    def _file_get(self, session_id):
        cart = self._carts.setdefault(session_id, {})
        items = []
        total = 0.0
        for product_id, quantity in cart.items():
            product = self.products[product_id]
            amount = product.price * quantity
            total += amount
            items.append(
                {
                    "product_id": product.product_id,
                    "name": product.title,
                    "brand": product.brand,
                    "price": product.price,
                    "quantity": quantity,
                    "amount": amount,
                    "main_image_url": product_image_url(product.image_path),
                    "image_url": product_image_url(product.image_path),
                    "selected": True,
                }
            )
        return {"session_id": session_id, "items": items, "total_amount": total}

    def _file_update_quantity(self, session_id, product_id, quantity):
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=True)
        cart = self._carts.setdefault(session_id, {})
        if quantity == 0:
            cart.pop(product_id, None)
            self._log_action(session_id, "remove", product_id, 0)
        else:
            cart[product_id] = quantity
            self._log_action(session_id, "update", product_id, quantity)
        self._save()
        return self.get(session_id)

    def _file_remove(self, session_id, product_id):
        self._validate_product(product_id)
        self._carts.setdefault(session_id, {}).pop(product_id, None)
        self._log_action(session_id, "remove", product_id, 0)
        self._save()
        return self.get(session_id)

    def _file_clear(self, session_id):
        self._carts[session_id] = {}
        self._log_action(session_id, "clear", None, 0)
        self._save()
        return self.get(session_id)

    def _file_checkout(self, session_id, idempotency_key):
        existing = self._get_idempotency_result(session_id, idempotency_key)
        if existing is not None:
            return existing
        snapshot = self._file_get(session_id)
        self._log_action(session_id, "checkout", None, 0)
        self._file_clear(session_id)
        result = {
            "status": "ok",
            "session_id": session_id,
            "order_id": f"demo_order_{session_id}_{uuid.uuid4().hex[:8]}",
            "paid_amount": snapshot["total_amount"],
            "items": snapshot["items"],
        }
        self._remember_idempotency_result(session_id, idempotency_key, result)
        self._save()
        return result

    def get_audit_log(self, session_id: str) -> list[dict]:
        return list(self._audit_log.get(session_id, []))

    def _validate_product(self, product_id: str) -> None:
        if product_id not in self.products:
            raise KeyError(f"unknown product_id: {product_id}")

    def _validate_quantity(self, quantity: int, *, allow_zero: bool) -> None:
        min_quantity = 0 if allow_zero else 1
        if quantity < min_quantity or quantity > MAX_CART_QUANTITY:
            raise ValueError(f"quantity must be between {min_quantity} and {MAX_CART_QUANTITY}")

    def _get_idempotency_result(self, session_id: str, key: str | None) -> dict | None:
        if not key:
            return None
        result = self._idempotency_results.get(session_id, {}).get(key)
        return copy.deepcopy(result) if result is not None else None

    def _remember_idempotency_result(self, session_id: str, key: str | None, result: dict) -> None:
        if not key:
            return
        bucket = self._idempotency_results.setdefault(session_id, {})
        bucket[key] = copy.deepcopy(result)

    def _log_action(self, session_id: str, action: str, product_id: str | None, quantity: int) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "product_id": product_id,
            "quantity": quantity,
        }
        log = self._audit_log.setdefault(session_id, [])
        log.append(entry)
        if len(log) > 100:
            self._audit_log[session_id] = log[-100:]

    def _load(self) -> None:
        if not self.persist_path or not self.persist_path.exists():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if "carts" in data and "audit_log" in data:
                    self._carts = {
                        str(k): {str(pk): int(qv) for pk, qv in v.items()}
                        for k, v in data["carts"].items()
                        if isinstance(v, dict)
                    }
                    self._audit_log = {
                        str(k): list(v) for k, v in data["audit_log"].items()
                    }
                    raw_idempotency = data.get("idempotency_results", {})
                    if isinstance(raw_idempotency, dict):
                        self._idempotency_results = {
                            str(k): {str(ik): dict(iv) for ik, iv in v.items() if isinstance(iv, dict)}
                            for k, v in raw_idempotency.items()
                            if isinstance(v, dict)
                        }
                else:
                    self._carts = {
                        str(k): {str(pk): int(qv) for pk, qv in v.items()}
                        for k, v in data.items()
                        if isinstance(v, dict)
                    }
        except Exception:
            logger.warning("Failed to load cart data, resetting", exc_info=True)
            self._carts = {}
            self._audit_log = {}
            self._idempotency_results = {}

    def _save(self) -> None:
        if not self.persist_path:
            return
        payload = {
            "carts": self._carts,
            "audit_log": self._audit_log,
            "idempotency_results": self._idempotency_results,
        }
        self.persist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
