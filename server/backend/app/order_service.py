"""
订单状态机服务 — SoulDance 电商导购的订单生命周期管理。

===== 领域概念扫盲 =====

"状态机"（State Machine）是一种编程模式：一个实体（订单）在任意时刻只能处于
一个确定状态，只能通过有限的、明确定义的操作（action）在不同状态间转移。
就像现实世界的订单：先选地址 → 再确认 → 最后完成，不能跳步或倒退。

"幂等"（Idempotent）：同一个操作执行一次和执行多次，结果完全一样。
比如用户网络卡顿，连续点了两次"确认下单"，后端收到的两次请求只产生一个订单，
第二次请求直接返回第一次的结果。这是通过 idempotency_key 实现的。

"双写"（Dual-write）：数据同时写到内存（dict）和数据库（SQLite/ORM）。
数据库挂了至少内存还能用；重启丢内存但数据库还在。这是当前演示阶段的折中方案。

"confirmation_token"：确认令牌，select_address 时生成一个随机字符串，
confirm_order 时必须带上这个 token，防止用户绕过地址选择直接确认。

===== 状态流转图 =====

    [购物车结算]
         |
         v
  address_required ──(选择地址)──> awaiting_confirmation ──(确认)──> completed
    ^                                    |                          (终态，不可再变)
    |                                    |
    +────────(修改地址)───────────────────+

===== 存储策略 =====

- 有 db_session → 优先走 SQLite（OrderRepository），重启数据不丢
- 无 db_session + 有 persist_dir → 文件持久化（JSON），跨重启保留
- 都没有 → 纯内存 dict，进程重启全丢（仅用于快速测试）

===== 与其它模块协作 =====

- cart.py / CartService：initiate_checkout 从购物车取快照生成订单
- repositories/order_repository.py：数据库读写层
- db/models.py：SQLAlchemy ORM 映射（OrderOrm / OrderItemOrm）
- main.py：装配时传入 cart + db_session，注入到 /api/order/* 路由
"""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import Address, Order, OrderItem

logger = logging.getLogger(__name__)

# ── 订单状态常量 ─────────────────────────────────────────────
# 三个合法状态，整个服务中所有状态判断都以此为准。
# 状态名用英文常量避免硬编码字符串散落各处、打错字难排查。

ORDER_STATUS_ADDRESS_REQUIRED = "address_required"
# ↑ 初始状态：用户刚点了"结算"，购物车快照已生成，但还没选地址

ORDER_STATUS_AWAITING_CONFIRMATION = "awaiting_confirmation"
# ↑ 中间状态：地址已选定，confirmation_token 已生成，等待用户最终确认

ORDER_STATUS_COMPLETED = "completed"
# ↑ 终态：用户已确认，购物车已清空，订单不可再修改

# ── 模拟地址数据 ─────────────────────────────────────────────
# 当前演示阶段没有真实用户地址系统，用两套 mock 地址代替。
# 答辩/演示后可以替换为从数据库或用户服务读取真实地址。

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
    """订单业务异常的基类，所有订单相关错误都继承它。

    main.py 的 _order_or_http() 统一捕获 OrderError，
    按 status_code 转成对应的 HTTP 错误响应（400/404/409）。
    """
    status_code = 400


class OrderNotFoundError(OrderError):
    """订单不存在（404），通常因为 order_id 拼错或已过期被清理。"""
    status_code = 404


class OrderConflictError(OrderError):
    """订单状态冲突（409），比如已完成的订单不能再修改地址。"""
    status_code = 409


class OrderService:
    """订单状态机的核心服务。

    ===== 三种运行模式（按优先级） =====

    模式 A（数据库模式）：db_session 不为 None
        → 使用 OrderRepository（SQLAlchemy ORM）读写 SQLite
        → 状态持久化，重启不丢
        → 条件：main.py 装配时传入了 db_session（settings.database_url 存在）

    模式 B（文件模式）：db_session 为 None 但 persist_dir 不为 None
        → 每个 session 的订单序列化为 JSON 文件
        → 启动时从文件恢复，修改后写回
        → 条件：SHOPGUIDE_SESSION_DIR 配置了路径

    模式 C（纯内存模式）：db_session 和 persist_dir 都是 None
        → 用 dict 存储，进程重启全部丢失
        → 仅用于快速冒烟测试

    ===== 关键字段说明 =====

    - _orders: 按 session_id 分组的订单列表 {session_id: [Order, ...]}
    - _confirm_results: 已确认订单的幂等缓存 {order_id: {idempotency_key: Order}}
      用于 confirm_order 的去重——同一个 idempotency_key 第二次请求直接返回缓存结果
    - _repo: 数据库模式下的 OrderRepository 实例；为 None 表示走文件/内存
    """

    def __init__(
        self,
        cart_service,
        persist_dir: str | Path | None = None,
        db_session=None,
    ):
        from .cart import CartService

        self._cart: CartService = cart_service
        # 内存存储：key = session_id，value = 该 session 的订单列表
        self._orders: dict[str, list[Order]] = {}
        # 幂等确认结果缓存：key = order_id，value = {idempotency_key: Order}
        # 这是幂等性的核心——重复请求直接返回缓存结果，不会重复下单
        self._confirm_results: dict[str, dict[str, Order]] = {}
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self.db_session = db_session
        self._repo = None
        # 优先走数据库持久化；数据库不可用时退到文件/内存
        if self.db_session is not None:
            from .repositories.order_repository import OrderRepository
            self._repo = OrderRepository(self.db_session)
        if self.persist_dir and self._repo is None:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._load()  # 从磁盘恢复之前的订单数据

    # ── 公开 API ──────────────────────────────────────────────
    # 以下三个方法是订单状态机的对外接口，分别对应状态流转的三个步骤。

    def initiate_checkout(self, user_id: str, session_id: str) -> Order:
        """步骤 1：从购物车快照生成订单预览。

        此时订单进入 address_required 状态。不会清空购物车——那要等 confirm_order。
        如果购物车为空则直接报错，因为没有商品就无法创建有意义的订单。

        返回的 Order 包含：订单 ID、商品明细（从购物车复制）、总金额、初始状态。
        """
        cart = self._cart.get(user_id, session_id)
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
        """步骤 2：选择收货地址，生成 confirmation_token，进入待确认状态。

        从 MOCK_ADDRESSES 中匹配 address_id（当前演示阶段用 mock，后续可接真实地址服务）。
        匹配成功后：
        1. 把选中的地址写入订单
        2. 将状态从 address_required 推进到 awaiting_confirmation
        3. 生成一个随机 confirmation_token（secrets.token_urlsafe(24)），
           后续 confirm_order 必须携带此 token，防止跳过地址选择直接确认

        如果订单已处于 completed 状态，抛出 OrderConflictError——已完成的订单不能再改地址。
        """
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
        user_id: str,
        order_id: str,
        confirmation_token: str | None,
        idempotency_key: str | None,
    ) -> Order:
        """步骤 3：最终确认订单，触发购物车清空，进入终态。

        ===== 幂等性保证 =====
        通过 idempotency_key 判断是否为重复请求：
        - 如果同一个 (order_id, idempotency_key) 已成功确认过，直接返回缓存的订单结果
        - 这确保用户网络重试、客户端重发不会产生重复订单

        ===== 校验链 =====
        1. 幂等检查：已确认过 → 直接返回缓存
        2. 终态检查：状态已是 completed → 409 冲突（不能重复确认已完成的订单）
        3. 状态检查：状态不是 awaiting_confirmation → 400（还没选地址不能确认）
        4. Token 校验：confirmation_token 不匹配 → 400（防绕过地址选择）

        ===== 副作用 =====
        - 购物车 checkout（清空购物车，生成 demo_order_xxx 的订单号）
        - 订单状态更新为 completed
        - 记录幂等结果到 _confirm_results 缓存
        - 持久化到 DB 或文件
        """
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
        self._cart.checkout(user_id, order.session_id, idempotency_key=f"order:{order.order_id}")
        order.status = ORDER_STATUS_COMPLETED
        order.idempotency_key = idempotency_key
        order.updated_at = _now()
        self._remember_confirm_result(order, idempotency_key)
        self._save_order(order)
        return order

    def get_addresses(self) -> list[Address]:
        """返回可选的收货地址列表（当前为 MOCK_ADDRESSES）。

        演示/答辩后应替换为从用户地址服务或数据库查询。
        """
        return list(MOCK_ADDRESSES)

    # ── 内部辅助方法 ──────────────────────────────────────────

    def _require_order(self, order_id: str) -> Order:
        """按 order_id 查找订单，找不到则抛出 OrderNotFoundError（404）。

        这是"乐观查找"模式——调用方假定订单一定存在，不存在就是异常。
        所有公开 API 都通过此方法获取订单，保证错误处理的一致性。
        """
        order = self._get_order(order_id)
        if order is None:
            raise OrderNotFoundError("order not found")
        return order

    def _get_order(self, order_id: str) -> Order | None:
        """从存储中查找订单。优先走 DB repository，其次内存 dict。

        注意：DB 模式下的 ORM → Pydantic 转换不经过 _orders 内存字典，
        每次都是从数据库直接查，避免了数据一致性问题。
        """
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
        """幂等查询：根据 (order_id, idempotency_key) 查找已缓存的确认结果。

        key 为 None 时直接返回 None——没有幂等键就不做去重，每次都是新请求。
        这是设计决定：幂等是可选的，不强求客户端提供 idempotency_key。
        """
        if not key:
            return None
        return self._confirm_results.get(order.order_id, {}).get(key)

    def _remember_confirm_result(self, order: Order, key: str | None) -> None:
        """记录一次成功的确认结果，用于后续幂等查询。

        使用 model_copy(deep=True) 深拷贝，确保后续对原 order 的修改
        不会污染已缓存的幂等结果。
        """
        if not key:
            return
        self._confirm_results.setdefault(order.order_id, {})[key] = order.model_copy(deep=True)

    def _save_order(self, order: Order) -> None:
        """持久化订单到 DB 或文件（取决于当前运行模式）。

        ===== DB 模式 =====
        - 首次保存（existing is None）：创建新的 ORM 对象（OrderOrm + OrderItemOrm），
          通过 OrderRepository.save() 写入数据库
        - 更新保存（existing 已存在）：原地修改已有 ORM 对象的字段值。
          items 的处理采用"删旧建新"策略——先删除旧 items 行，再插入新 items 行。
          这是为了简化同步逻辑：避免逐条对比哪些 item 改了/删了/新增了。
          副作用：items 的自增主键会变化，但不影响业务（关联走 order_id 外键）。
          order 级别的字段（status/total/address/token）直接赋值即可。
        ===== 内存模式 =====
        - 按 session_id 分组存储，同一订单存在则替换，不存在则追加
        - 追加后调用 _save() 写磁盘
        """
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
        """将内存中的全部订单 + 幂等确认结果序列化到 JSON 文件。

        仅在文件模式下调用（persist_dir 不为 None 且没有 DB）。
        文件结构：
        {
          "orders": {session_id: [Order的JSON列表], ...},
          "confirm_results": {order_id: {idempotency_key: Order的JSON}, ...}
        }
        DB 模式下不调用此方法（数据在 SQLite 中已有持久化）。
        """
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
        """从 JSON 文件恢复订单和幂等确认结果到内存。

        支持两种格式（向后兼容）：
        1. 新格式：{"orders": {...}, "confirm_results": {...}}
        2. 旧格式（legacy）：直接是 {session_id: [Order列表]}，没有 confirm_results

        如果文件损坏（JSON 解析失败），清空内存状态并从零开始。
        这比崩溃更友好——用户虽然丢了历史订单，但服务还能用。
        """
        if not self.persist_dir:
            return
        path = self._orders_path()
        if not path.exists():
            # 向后兼容：尝试从旧路径 orders.json 读取
            legacy_path = self.persist_dir / "orders.json"
            if legacy_path.exists():
                path = legacy_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "orders" in data:
                # 新格式（含 confirm_results）
                order_data = data.get("orders", {})
                confirm_data = data.get("confirm_results", {})
            else:
                # 旧格式（只有订单列表，没有 confirm_results）
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
        """订单持久化文件的路径：{persist_dir}/orders/orders.json"""
        assert self.persist_dir is not None
        return self.persist_dir / "orders" / "orders.json"


def _now() -> str:
    """返回当前 UTC 时间的 ISO 8601 格式字符串，供订单 created_at/updated_at 使用。

    使用 UTC（无时区歧义）+ ISO 8601（国际标准、机器可解析），避免时区转换问题。
    """
    return datetime.now(timezone.utc).isoformat()
