"""
购物车服务 — SoulDance 电商导购的购物车与结算逻辑。

===== 领域概念扫盲 =====

"幂等键"（idempotency_key）：
客户端为每次写操作（添加商品、结算）生成一个唯一 ID。后端用这个 ID 做去重：
同一个 key 的第二次请求直接返回第一次的结果，不会重复执行操作。
这解决了移动网络不稳定时用户重复点击的问题——比如用户点了两次"结算"，
只有第一次会真正清空购物车，第二次只是返回同一个订单号。

"双模式存储"（DB vs File）：
与 OrderService 类似的策略——有 db_session 优先 SQLite，否则用 JSON 文件，
都没有就纯内存（进程重启丢失）。详见 __init__ 文档。

"审计日志"（audit_log）：
每次购物车操作（add/remove/update/checkout）都记录一条带时间戳的日志，
保留最近 100 条。用于调试（排查"为什么我的购物车被清空了"）和潜在的分析需求。

"MAX_CART_QUANTITY"：
单个商品在购物车中的数量上限（99）。防止恶意请求把某个商品加到极大数量，
或者客户端出 bug 导致无限累加。

===== 与其它模块协作 =====

- main.py：装配时传入 products + persist_path + db_session，注册 /api/cart/* 路由
- order_service.py：checkout 时调用 cart.checkout() 清空购物车并获取快照
- repositories/cart_repository.py：数据库读写层
- models.py：Product, CartActionRequest
"""

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

# 单个商品在购物车中的数量上限。
# 99 是常见电商实践：既能覆盖正常批量采购（如企业礼品），又能防止恶意刷数量。
MAX_CART_QUANTITY = 99


class CartService:
    """购物车核心服务。

    ===== 存储模式（按优先级） =====
    模式 A（DB）：db_session → CartRepository → SQLite
    模式 B（文件）：persist_path → JSON 文件（按 user/session 目录结构）
    模式 C（纯内存）：dict，重启丢失

    ===== 内部数据结构 =====
    - _carts: {(user_id, session_id): {product_id: quantity}} — 购物车内容
    - _audit_log: {(user_id, session_id): [dict]} — 审计日志，每个操作一条记录
    - _idempotency_results: {(user_id, session_id): {idempotency_key: result}} — 幂等缓存
    """
    def __init__(
        self,
        products: list[Product],
        persist_path: str | Path | None = None,
        db_session=None,
    ):
        """初始化购物车服务。

        products: 完整商品列表，存储为 {product_id: Product} dict 供快速查找。
        persist_path: JSON 文件模式的持久化目录。
        db_session: SQLAlchemy session；不为 None 时启用 DB 模式。
        """
        self.products = {product.product_id: product for product in products}
        # In-memory carts are scoped by user and session.
        self._carts: dict[tuple[str, str], dict[str, int]] = {}
        self._sku_selections: dict[tuple[str, str], dict[str, str]] = {}
        # Audit log is scoped by user and session.
        self._audit_log: dict[tuple[str, str], list[dict]] = {}
        # Idempotency results are scoped by user and session.
        self._idempotency_results: dict[tuple[str, str], dict[str, dict]] = {}
        self.persist_path = Path(persist_path) if persist_path else None
        self.db_session = db_session
        self._repo = None
        if self.db_session is not None:
            from .repositories.cart_repository import CartRepository
            self._repo = CartRepository(self.db_session)
        if self.persist_path and self._repo is None:
            self.persist_path.mkdir(parents=True, exist_ok=True)
            self._load()  # 从磁盘恢复

    # ── 公开 API ──────────────────────────────────────────────
    # 每个方法先检查是否在 DB 模式（self._repo is not None），决定走 DB 还是文件。
    # 这种分支判断分散在各方法中不是最优雅的设计，但避免了在每个方法里重复
    # 捕获异常/回退的模板代码。

    @staticmethod
    def _key(user_id: str, session_id: str) -> tuple[str, str]:
        return (user_id, session_id)

    def add(
        self,
        user_id: str,
        session_id: str,
        product_id: str,
        quantity: int = 1,
        idempotency_key: str | None = None,
    ) -> dict:
        """向购物车添加商品。

        - 如果提供了 idempotency_key，先检查是否已执行过，是则直接返回缓存结果
        - 校验 product_id 合法性（必须在 products 中）
        - 校验 quantity 范围（>=1 且 <= MAX_CART_QUANTITY）
        - 返回当前购物车的完整快照（含所有商品、数量和总金额）
        """
        if self._repo is not None:
            return self._db_add(user_id, session_id, product_id, quantity, idempotency_key)
        return self._file_add(user_id, session_id, product_id, quantity, idempotency_key)

    def _db_add(self, user_id, session_id, product_id, quantity, idempotency_key):
        existing = self._get_idempotency_result(user_id, session_id, idempotency_key)
        if existing is not None:
            return existing
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=False)
        self._repo.add(user_id, session_id, product_id, quantity)
        snapshot = self._db_get(user_id, session_id)
        self._remember_idempotency_result(user_id, session_id, idempotency_key, snapshot)
        return snapshot

    def _db_get(self, user_id, session_id):
        raw = self._repo.get(user_id, session_id)
        sku_map = self._sku_selections.get(self._key(user_id, session_id), {})
        items = []
        total = 0.0
        total_count = 0
        for row in raw["items"]:
            product_id = row["product_id"]
            quantity = row["quantity"]
            product = self.products.get(product_id)
            if product is None:
                continue
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
                "product_id": product_id,
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
        if self._repo is not None:
            return self._db_update_sku(user_id, session_id, product_id, property_value)
        return self._file_update_sku(user_id, session_id, product_id, property_value)

    def _db_update_sku(self, user_id, session_id, product_id, property_value):
        self._validate_product(product_id)
        cart = self._repo.get(user_id, session_id)
        if not any(row["product_id"] == product_id for row in cart.get("items", [])):
            raise ValueError(f"product {product_id} is not in cart")
        product = self.products.get(product_id)
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
        self._sku_selections.setdefault(self._key(user_id, session_id), {})[product_id] = matched
        self._log_action(user_id, session_id, "update_sku", product_id, 0)
        return self._db_get(user_id, session_id)

    def _file_update_sku(self, user_id, session_id, product_id, property_value):
        product = self.products.get(product_id)
        if product_id not in self._carts.get(self._key(user_id, session_id), {}):
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
        self._sku_selections.setdefault(self._key(user_id, session_id), {})[product_id] = matched
        self._log_action(user_id, session_id, "update_sku", product_id, 0)
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
        """结算：获取购物车快照并清空购物车。

        幂等安全：同一个 idempotency_key 第二次调用直接返回缓存的结算结果，
        不会重复清空或生成新订单号。返回包含 order_id 和 paid_amount 的结果字典。
        """
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
        existing = self._get_idempotency_result(user_id, session_id, idempotency_key)
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
        self._remember_idempotency_result(user_id, session_id, idempotency_key, result)
        return result

    def _file_add(self, user_id, session_id, product_id, quantity, idempotency_key):
        """文件模式添加：幂等检查 → 校验 → 更新内存 → 记日志 → 写磁盘。

        DB 模式见 _db_add()，逻辑完全一致，仅存储介质不同。
        """
        existing = self._get_idempotency_result(user_id, session_id, idempotency_key)
        if existing is not None:
            return existing
        self._validate_product(product_id)
        self._validate_quantity(quantity, allow_zero=False)
        cart = self._carts.setdefault(self._key(user_id, session_id), {})
        cart[product_id] = cart.get(product_id, 0) + quantity
        self._log_action(user_id, session_id, "add", product_id, cart[product_id])
        snapshot = self.get(user_id, session_id)
        self._remember_idempotency_result(user_id, session_id, idempotency_key, snapshot)
        self._save_one(user_id, session_id)
        return snapshot

    def _file_get(self, user_id, session_id):
        cart = self._carts.setdefault(self._key(user_id, session_id), {})
        sku_map = self._sku_selections.get(self._key(user_id, session_id), {})
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
        cart = self._carts.setdefault(self._key(user_id, session_id), {})
        if quantity == 0:
            cart.pop(product_id, None)
            self._log_action(user_id, session_id, "remove", product_id, 0)
        else:
            cart[product_id] = quantity
            self._log_action(user_id, session_id, "update", product_id, quantity)
        self._save_one(user_id, session_id)
        return self.get(user_id, session_id)

    def _file_remove(self, user_id, session_id, product_id):
        self._validate_product(product_id)
        self._carts.setdefault(self._key(user_id, session_id), {}).pop(product_id, None)
        self._sku_selections.get(self._key(user_id, session_id), {}).pop(product_id, None)
        self._log_action(user_id, session_id, "remove", product_id, 0)
        self._save_one(user_id, session_id)
        return self.get(user_id, session_id)

    def _file_clear(self, user_id, session_id):
        self._carts[self._key(user_id, session_id)] = {}
        self._sku_selections[self._key(user_id, session_id)] = {}
        self._log_action(user_id, session_id, "clear", None, 0)
        self._save_one(user_id, session_id)
        return self.get(user_id, session_id)

    def _file_checkout(self, user_id, session_id, idempotency_key):
        existing = self._get_idempotency_result(user_id, session_id, idempotency_key)
        if existing is not None:
            return existing
        snapshot = self._file_get(user_id, session_id)
        self._log_action(user_id, session_id, "checkout", None, 0)
        self._file_clear(user_id, session_id)
        result = {
            "status": "ok",
            "session_id": session_id,
            "order_id": f"demo_order_{session_id}_{uuid.uuid4().hex[:8]}",
            "paid_amount": snapshot["total_amount"],
            "items": snapshot["items"],
        }
        self._remember_idempotency_result(user_id, session_id, idempotency_key, result)
        self._save_one(user_id, session_id)
        return result

    def get_audit_log(self, session_id: str, user_id: str = "anonymous") -> list[dict]:
        return list(self._audit_log.get(self._key(user_id, session_id), []))

    def _validate_product(self, product_id: str) -> None:
        """校验 product_id 存在于商品列表中，否则抛出 KeyError（→ 400）。"""
        if product_id not in self.products:
            raise KeyError(f"unknown product_id: {product_id}")

    def _validate_quantity(self, quantity: int, *, allow_zero: bool) -> None:
        """校验数量在合法范围内。

        allow_zero=True 用于 update_quantity（允许数量为 0 表示删除）和 remove 操作。
        add 操作 allow_zero=False，因为添加商品数量至少为 1。
        """
        min_quantity = 0 if allow_zero else 1
        if quantity < min_quantity or quantity > MAX_CART_QUANTITY:
            raise ValueError(f"quantity must be between {min_quantity} and {MAX_CART_QUANTITY}")

    def _get_idempotency_result(self, user_id: str, session_id: str, key: str | None) -> dict | None:
        """Return a cached idempotent result scoped to one user session."""
        if not key:
            return None
        result = self._idempotency_results.get(self._key(user_id, session_id), {}).get(key)
        return copy.deepcopy(result) if result is not None else None

    def _remember_idempotency_result(self, user_id: str, session_id: str, key: str | None, result: dict) -> None:
        """Store a successful operation result for idempotent replay."""
        if not key:
            return
        bucket = self._idempotency_results.setdefault(self._key(user_id, session_id), {})
        bucket[key] = copy.deepcopy(result)

    def _log_action(self, user_id: str, session_id: str, action: str, product_id: str | None, quantity: int) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "product_id": product_id,
            "quantity": quantity,
        }
        key = self._key(user_id, session_id)
        log = self._audit_log.setdefault(key, [])
        log.append(entry)
        if len(log) > 100:
            self._audit_log[key] = log[-100:]

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
                        key = self._key(user_id, session_id)
                        if "cart" in data:
                            self._carts[key] = {
                                str(pk): int(qv) for pk, qv in data["cart"].items()
                                if isinstance(qv, int)
                            }
                        if "audit_log" in data:
                            self._audit_log[key] = list(data["audit_log"])
                        if "idempotency_results" in data:
                            raw_idempotency = data["idempotency_results"]
                            if isinstance(raw_idempotency, dict):
                                self._idempotency_results[key] = {
                                    str(ik): dict(iv) for ik, iv in raw_idempotency.items()
                                    if isinstance(iv, dict)
                                }
                        if "sku_selections" in data:
                            raw_sku = data["sku_selections"]
                            if isinstance(raw_sku, dict):
                                self._sku_selections[key] = dict(raw_sku)
                except Exception:
                    logger.warning("Failed to load cart %s/%s, skipping", user_id, session_id, exc_info=True)
                    continue

    def _save_one(self, user_id: str, session_id: str) -> None:
        if not self.persist_path:
            return
        path = self._path(user_id, session_id)
        tmp_path = path.with_suffix(".tmp")
        key = self._key(user_id, session_id)
        payload = {
            "cart": self._carts.get(key, {}),
            "sku_selections": self._sku_selections.get(key, {}),
            "audit_log": self._audit_log.get(key, []),
            "idempotency_results": self._idempotency_results.get(key, {}),
        }
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.rename(path)

    def _save(self) -> None:
        if not self.persist_path:
            return
        # Note: We save per user/session on demand in file-mode methods
        # The old monolithic save is kept for backward compatibility but not used
        pass
