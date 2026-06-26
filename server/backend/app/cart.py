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
        self._sku_selections: dict[str, dict[str, str]] = {}
        self._audit_log: dict[str, list[dict]] = {}
        self._idempotency_results: dict[str, dict[str, dict]] = {}
        self.persist_path = Path(persist_path) if persist_path else None
        self.db_session = db_session
        self._repo = None
        if self.db_session is not None:
            from .repositories.cart_repository import CartRepository
            self._repo = CartRepository(self.db_session)
        if self.persist_path and self._repo is None:
            self.persist_path.mkdir(parents=True, exist_ok=True)
            self._load()

    # ... 保留原有 _load/_save/文件逻辑不变 ...

    def add(
        self,
        user_id: str,
        session_id: str,
        product_id: str,
        quantity: int = 1,
        idempotency_key: str | None = None,
    ) -> dict:
        if self._repo is not None:
            return self._db_add(user_id, session_id, product_id, quantity, idempotency_key)
        return self._file_add(user_id, session_id, product_id, quantity, idempotency_key)

    def _db_add(self, user_id, session_id, product_id, quantity, idempotency_key):
        existing = self._get_idempotency_result(session_id, idempotency_key)
        if existing is not None:
            return existing
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=False)
        self._repo.add(user_id, session_id, product_id, quantity)
        snapshot = self._db_get(user_id, session_id)
        self._remember_idempotency_result(session_id, idempotency_key, snapshot)
        return snapshot

    def _db_get(self, user_id, session_id):
        raw = self._repo.get(user_id, session_id)
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

    def get(self, user_id: str, session_id: str) -> dict:
        if self._repo is not None:
            return self._db_get(user_id, session_id)
        return self._file_get(user_id, session_id)

    def update_quantity(self, user_id: str, session_id: str, product_id: str, quantity: int) -> dict:
        if self._repo is not None:
            return self._db_update_quantity(user_id, session_id, product_id, quantity)
        return self._file_update_quantity(user_id, session_id, product_id, quantity)

    def update_sku(self, user_id: str, session_id: str, product_id: str, property_value: str) -> dict:
        """Select a product SKU whose properties contain ``property_value``.

        Returns the updated cart snapshot.  Raises ``ValueError`` when no
        SKU property matches — the caller should present a clarification
        with the available options.
        """
        product = self.products.get(product_id)
        if product is None:
            raise ValueError(f"product {product_id} not found")
        if product_id not in self._carts.get(session_id, {}):
            raise ValueError(f"product {product_id} is not in cart")
        matched: str | None = None
        for sku in product.skus:
            for value in sku.properties.values():
                if property_value in value:
                    matched = sku.sku_id
                    break
            if matched:
                break
        if matched is None:
            options = [
                ", ".join(f"{k}: {v}" for k, v in sku.properties.items())
                for sku in product.skus
            ]
            raise ValueError(
                f"no SKU matching '{property_value}' for {product.title}. "
                f"Available: {'; '.join(options)}"
            )
        self._sku_selections.setdefault(session_id, {})[product_id] = matched
        self._log_action(session_id, "update_sku", product_id, 0)
        self._save_one(user_id, session_id)
        return self.get(user_id, session_id)

    def remove(self, user_id: str, session_id: str, product_id: str) -> dict:
        if self._repo is not None:
            return self._db_remove(user_id, session_id, product_id)
        return self._file_remove(user_id, session_id, product_id)

    def clear(self, user_id: str, session_id: str) -> dict:
        if self._repo is not None:
            return self._db_clear(user_id, session_id)
        return self._file_clear(user_id, session_id)

    def checkout(self, user_id: str, session_id: str, idempotency_key: str | None = None) -> dict:
        if self._repo is not None:
            return self._db_checkout(user_id, session_id, idempotency_key)
        return self._file_checkout(user_id, session_id, idempotency_key)

    def _db_update_quantity(self, user_id, session_id, product_id, quantity):
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=True)
        self._repo.update_quantity(user_id, session_id, product_id, quantity)
        return self._db_get(user_id, session_id)

    def _db_remove(self, user_id, session_id, product_id):
        self._validate_product(product_id)
        self._repo.remove(user_id, session_id, product_id)
        return self._db_get(user_id, session_id)

    def _db_clear(self, user_id, session_id):
        self._repo.clear(user_id, session_id)
        return self._db_get(user_id, session_id)

    def _db_checkout(self, user_id, session_id, idempotency_key):
        existing = self._get_idempotency_result(session_id, idempotency_key)
        if existing is not None:
            return existing
        snapshot = self._db_get(user_id, session_id)
        self._repo.checkout(user_id, session_id)
        result = {
            "status": "ok",
            "session_id": session_id,
            "order_id": f"demo_order_{session_id}_{uuid.uuid4().hex[:8]}",
            "paid_amount": snapshot["total_amount"],
            "items": snapshot["items"],
        }
        self._remember_idempotency_result(session_id, idempotency_key, result)
        return result

    def _file_add(self, user_id, session_id, product_id, quantity, idempotency_key):
        existing = self._get_idempotency_result(session_id, idempotency_key)
        if existing is not None:
            return existing
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=False)
        cart = self._carts.setdefault(session_id, {})
        cart[product_id] = cart.get(product_id, 0) + quantity
        self._log_action(session_id, "add", product_id, cart[product_id])
        snapshot = self.get(user_id, session_id)
        self._remember_idempotency_result(session_id, idempotency_key, snapshot)
        self._save_one(user_id, session_id)
        return snapshot

    def _file_get(self, user_id, session_id):
        cart = self._carts.setdefault(session_id, {})
        sku_map = self._sku_selections.get(session_id, {})
        items = []
        total = 0.0
        total_count = 0
        for product_id, quantity in cart.items():
            product = self.products[product_id]
            selected_sku_id = sku_map.get(product_id)
            selected_sku = None
            unit_price = product.price
            if selected_sku_id:
                for sku in product.skus:
                    if sku.sku_id == selected_sku_id:
                        selected_sku = sku
                        unit_price = sku.price
                        break
            amount = unit_price * quantity
            total += amount
            total_count += quantity
            item = {
                "product_id": product.product_id,
                "name": product.title,
                "brand": product.brand,
                "price": unit_price,
                "quantity": quantity,
                "amount": amount,
                "main_image_url": product_image_url(product.image_path),
                "image_url": product_image_url(product.image_path),
                "selected": True,
            }
            if selected_sku is not None:
                item["selected_sku"] = {
                    "sku_id": selected_sku.sku_id,
                    "properties": selected_sku.properties,
                    "unit_price": selected_sku.price,
                }
            items.append(item)
        return {"session_id": session_id, "items": items, "total_amount": total, "total_count": total_count}

    def _file_update_quantity(self, user_id, session_id, product_id, quantity):
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=True)
        cart = self._carts.setdefault(session_id, {})
        if quantity == 0:
            cart.pop(product_id, None)
            self._log_action(session_id, "remove", product_id, 0)
        else:
            cart[product_id] = quantity
            self._log_action(session_id, "update", product_id, quantity)
        self._save_one(user_id, session_id)
        return self.get(user_id, session_id)

    def _file_remove(self, user_id, session_id, product_id):
        self._validate_product(product_id)
        self._carts.setdefault(session_id, {}).pop(product_id, None)
        self._log_action(session_id, "remove", product_id, 0)
        self._save_one(user_id, session_id)
        return self.get(user_id, session_id)

    def _file_clear(self, user_id, session_id):
        self._carts[session_id] = {}
        self._log_action(session_id, "clear", None, 0)
        self._save_one(user_id, session_id)
        return self.get(user_id, session_id)

    def _file_checkout(self, user_id, session_id, idempotency_key):
        existing = self._get_idempotency_result(session_id, idempotency_key)
        if existing is not None:
            return existing
        snapshot = self._file_get(user_id, session_id)
        self._log_action(session_id, "checkout", None, 0)
        self._file_clear(user_id, session_id)
        result = {
            "status": "ok",
            "session_id": session_id,
            "order_id": f"demo_order_{session_id}_{uuid.uuid4().hex[:8]}",
            "paid_amount": snapshot["total_amount"],
            "items": snapshot["items"],
        }
        self._remember_idempotency_result(session_id, idempotency_key, result)
        self._save_one(user_id, session_id)
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

    def _path(self, user_id: str, session_id: str) -> Path:
        safe_user_id = user_id.replace("/", "_").replace("\\", "_")
        safe_session_id = session_id.replace("/", "_").replace("\\", "_")
        user_dir = self.persist_path / safe_user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / f"{safe_session_id}.json"

    def _load(self) -> None:
        if not self.persist_path or not self.persist_path.exists():
            return
        # Load all user session files from per-user directories
        for user_dir in self.persist_path.iterdir():
            if not user_dir.is_dir():
                continue
            user_id = user_dir.name
            for path in user_dir.glob("*.json"):
                session_id = path.stem
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        if "cart" in data:
                            self._carts[session_id] = {
                                str(pk): int(qv) for pk, qv in data["cart"].items()
                                if isinstance(qv, int)
                            }
                        if "audit_log" in data:
                            self._audit_log[session_id] = list(data["audit_log"])
                        if "idempotency_results" in data:
                            raw_idempotency = data["idempotency_results"]
                            if isinstance(raw_idempotency, dict):
                                self._idempotency_results[session_id] = {
                                    str(ik): dict(iv) for ik, iv in raw_idempotency.items()
                                    if isinstance(iv, dict)
                                }
                except Exception:
                    logger.warning("Failed to load cart %s/%s, skipping", user_id, session_id, exc_info=True)
                    continue

    def _save_one(self, user_id: str, session_id: str) -> None:
        if not self.persist_path:
            return
        path = self._path(user_id, session_id)
        tmp_path = path.with_suffix(".tmp")
        payload = {
            "cart": self._carts.get(session_id, {}),
            "audit_log": self._audit_log.get(session_id, []),
            "idempotency_results": self._idempotency_results.get(session_id, {}),
        }
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.rename(path)

    def _save(self) -> None:
        if not self.persist_path:
            return
        # Note: We save per user/session on demand in file-mode methods
        # The old monolithic save is kept for backward compatibility but not used
        pass
