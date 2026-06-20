from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .image_assets import product_image_url_auto as product_image_url
from .models import Product

logger = logging.getLogger(__name__)


class CartService:
    def __init__(self, products: list[Product], persist_path: str | Path | None = None):
        self.products = {product.product_id: product for product in products}
        self._carts: dict[str, dict[str, int]] = {}
        self._audit_log: dict[str, list[dict]] = {}
        self.persist_path = Path(persist_path) if persist_path else None
        if self.persist_path:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def add(self, session_id: str, product_id: str, quantity: int = 1) -> dict:
        if product_id not in self.products:
            raise KeyError(f"unknown product_id: {product_id}")
        cart = self._carts.setdefault(session_id, {})
        cart[product_id] = cart.get(product_id, 0) + max(quantity, 1)
        self._log_action(session_id, "add", product_id, cart[product_id])
        self._save()
        return self.get(session_id)

    def update_quantity(self, session_id: str, product_id: str, quantity: int) -> dict:
        if product_id not in self.products:
            raise KeyError(f"unknown product_id: {product_id}")
        cart = self._carts.setdefault(session_id, {})
        if quantity <= 0:
            cart.pop(product_id, None)
            self._log_action(session_id, "remove", product_id, 0)
        else:
            cart[product_id] = quantity
            self._log_action(session_id, "update", product_id, quantity)
        self._save()
        return self.get(session_id)

    def remove(self, session_id: str, product_id: str) -> dict:
        self._carts.setdefault(session_id, {}).pop(product_id, None)
        self._log_action(session_id, "remove", product_id, 0)
        self._save()
        return self.get(session_id)

    def clear(self, session_id: str) -> dict:
        self._carts[session_id] = {}
        self._log_action(session_id, "clear", None, 0)
        self._save()
        return self.get(session_id)

    def get(self, session_id: str) -> dict:
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

    def checkout(self, session_id: str) -> dict:
        snapshot = self.get(session_id)
        self._log_action(session_id, "checkout", None, 0)
        self.clear(session_id)
        return {
            "status": "ok",
            "session_id": session_id,
            "order_id": f"demo_order_{session_id}_{uuid.uuid4().hex[:8]}",
            "paid_amount": snapshot["total_amount"],
            "items": snapshot["items"],
        }

    def get_audit_log(self, session_id: str) -> list[dict]:
        return list(self._audit_log.get(session_id, []))

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
                    # 新格式: {"carts": {...}, "audit_log": {...}}
                    self._carts = {
                        str(k): {str(pk): int(qv) for pk, qv in v.items()}
                        for k, v in data["carts"].items()
                        if isinstance(v, dict)
                    }
                    self._audit_log = {
                        str(k): list(v) for k, v in data["audit_log"].items()
                    }
                else:
                    # 旧格式向后兼容: {session_id: {product_id: quantity}}
                    self._carts = {
                        str(k): {str(pk): int(qv) for pk, qv in v.items()}
                        for k, v in data.items()
                        if isinstance(v, dict)
                    }
        except Exception:
            logger.warning("Failed to load cart data, resetting", exc_info=True)
            self._carts = {}

    def _save(self) -> None:
        if not self.persist_path:
            return
        payload = {
            "carts": self._carts,
            "audit_log": self._audit_log,
        }
        self.persist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
