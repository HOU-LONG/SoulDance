# SoulDance 数据库与依赖基线实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 SoulDance 后端的 JSON 文件持久化升级为 PostgreSQL + pgvector，建立可复现的依赖基线，同时保持现有 API 和 Android 客户端兼容。

**Architecture:** 在 `server/backend/app/db/` 下新建 SQLAlchemy ORM 层与 repository 层；原有 `CartService`、`OrderService`、`SessionStore`、`FeedbackStore`、`UserProfileStore` 保留公共接口，内部逐步切换为数据库读写；使用 Alembic 管理 schema 迁移；商品 fixture 通过 seed 脚本入库，向量暂以整商品 chunk 形式存入 pgvector。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, psycopg 3, pgvector-python, Alembic, pip-tools.

## Global Constraints

- 保持 `/health`、`/api/products`、`/api/cart/*`、`/api/order/*`、`/api/stt`、`/ws/chat` 稳定。
- WebSocket 事件类型 `text_delta`、`product_item`、`cart_update`、`done`、`error` 保持兼容。
- 数据库迁移必须可回滚。
- 新增代码必须与现有 Pydantic 模型、`ShopGuideAgent` 调用链兼容。
- 不改变 Android 端已有 ViewModel 接口签名。
- 不引入 Docker / 容器化部署。
- 使用简体中文注释与自然语言，命令/代码/路径/API 保留英文。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `server/requirements.in` | 顶层直接依赖声明 |
| `server/requirements.lock` | 完整锁定依赖树（含哈希） |
| `server/requirements-dev.txt` | 开发/生成 lock 用依赖 |
| `server/backend/app/db/__init__.py` | DB 包初始化 |
| `server/backend/app/db/engine.py` | SQLAlchemy engine / session 工厂 |
| `server/backend/app/db/base.py` | declarative_base |
| `server/backend/app/db/models.py` | 所有 ORM 表定义 |
| `server/backend/app/db/repositories.py` | repository 层，封装数据库 CRUD |
| `server/backend/app/db/seed.py` | 从 fixture 导入商品与向量 |
| `server/alembic.ini` | Alembic 配置 |
| `server/migrations/env.py` | Alembic 运行环境 |
| `server/migrations/script.py.mako` | 迁移脚本模板 |
| `server/migrations/versions/` | 迁移脚本目录 |
| `server/backend/app/repositories/cart_repository.py` | Cart 数据库仓库（替代文件读写） |
| `server/backend/app/repositories/order_repository.py` | Order 数据库仓库 |
| `server/backend/app/repositories/session_repository.py` | Session 数据库仓库 |
| `server/backend/app/repositories/feedback_repository.py` | Feedback 数据库仓库 |
| `server/backend/app/repositories/profile_repository.py` | UserProfile 数据库仓库 |
| `server/tests/conftest.py` | 测试 fixtures，提供内存/测试数据库 |

---

## Task 1: 依赖声明与锁定

**Files:**
- Create: `server/requirements.in`
- Create: `server/requirements-dev.txt`
- Create: `server/requirements.lock`
- Modify: `deploy/env.example`

**Interfaces:**
- Produces: `server/requirements.lock` 可被 `pip install -r server/requirements.lock` 完整复现环境。

- [ ] **Step 1: 编写 `requirements.in`**

```text
# Core framework
fastapi==0.137.2
uvicorn[standard]==0.49.0
pydantic==2.13.4
python-multipart>=0.0.12

# HTTP / WebSocket clients
httpx==0.28.1
websockets==16.0

# Data & ML
numpy==2.3.5
jieba==0.42.1
rank-bm25==0.2.2
sentence-transformers==5.1.2

# LLM / ASR / TTS adapters
openai==2.38.0

# Database
sqlalchemy[asyncio]==2.0.51
psycopg[binary,pool]==3.3.4
pgvector==0.4.2
alembic==1.18.4

# Cache (optional, used by memory_cache)
redis[hiredis]==7.2.2

# JSON / env
orjson==3.11.9
python-dotenv>=1.0.0

# Testing
pytest==9.0.3
pytest-asyncio==1.3.0
respx>=0.22.0
```

- [ ] **Step 2: 编写 `requirements-dev.txt`**

```text
pip-tools==7.4.1
-r requirements.in
```

- [ ] **Step 3: 生成 `requirements.lock`**

Run:
```bash
cd server
../env/venv_shopguide_backend/bin/pip install pip-tools
../env/venv_shopguide_backend/bin/pip-compile --generate-hashes --output-file requirements.lock requirements.in
```

Expected: `requirements.lock` 生成成功，包含所有依赖及哈希。

- [ ] **Step 4: 验证安装**

Run:
```bash
cd server
../env/venv_shopguide_backend/bin/pip install -r requirements.lock
../env/venv_shopguide_backend/bin/python -c "import sqlalchemy, psycopg, pgvector, alembic; print('ok')"
```

Expected: 输出 `ok`。

- [ ] **Step 5: 更新 `deploy/env.example` 添加数据库环境变量**

Append:
```text
# PostgreSQL + pgvector
SHOPGUIDE_DATABASE_URL=postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide
SHOPGUIDE_EMBEDDING_DIMENSION=384
```

- [ ] **Step 6: 提交**

```bash
git add server/requirements.in server/requirements-dev.txt server/requirements.lock deploy/env.example
git commit -m "chore: add PostgreSQL/pgvector/Alembic dependencies and lock file

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: 数据库连接与配置

**Files:**
- Modify: `server/backend/app/config.py`
- Create: `server/backend/app/db/__init__.py`
- Create: `server/backend/app/db/engine.py`
- Create: `server/backend/app/db/base.py`

**Interfaces:**
- Consumes: `SHOPGUIDE_DATABASE_URL` from environment.
- Produces: `get_engine()`, `get_session()` in `server/backend/app/db/engine.py`.

- [ ] **Step 1: 修改 `server/backend/app/config.py` 添加数据库设置**

```python
# 在 Settings 类中添加字段
database_url: str = ""
embedding_dimension: int = 384
```

在 `get_settings()` 中添加：
```python
database_url=os.getenv("SHOPGUIDE_DATABASE_URL", ""),
embedding_dimension=int(os.getenv("SHOPGUIDE_EMBEDDING_DIMENSION", "384")),
```

- [ ] **Step 2: 编写 `server/backend/app/db/base.py`**

```python
from sqlalchemy.orm import declarative_base

Base = declarative_base()
```

- [ ] **Step 3: 编写 `server/backend/app/db/engine.py`**

```python
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url or "postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide"
        _engine = create_engine(url, pool_pre_ping=True, future=True)
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal()


def init_db():
    from .base import Base
    Base.metadata.create_all(bind=get_engine())
```

- [ ] **Step 4: 编写 `server/backend/app/db/__init__.py`**

```python
from .base import Base
from .engine import get_engine, get_session, init_db

__all__ = ["Base", "get_engine", "get_session", "init_db"]
```

- [ ] **Step 5: 运行简单连接测试**

Run:
```bash
cd server
../env/venv_shopguide_backend/bin/python -c "from backend.app.db import get_engine; print(get_engine())"
```

Expected: 输出 engine 对象，无异常（需本地 PostgreSQL 运行）。

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/db/ server/backend/app/config.py
git commit -m "feat(db): add SQLAlchemy engine and settings

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: ORM 模型定义

**Files:**
- Create: `server/backend/app/db/models.py`

**Interfaces:**
- Produces: SQLAlchemy ORM classes matching existing Pydantic models.

- [ ] **Step 1: 编写 `server/backend/app/db/models.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProductOrm(Base):
    __tablename__ = "products"

    product_id = Column(String(64), primary_key=True)
    title = Column(String(512), nullable=False)
    brand = Column(String(128), nullable=False, index=True)
    category = Column(String(128), nullable=False, index=True)
    sub_category = Column(String(128), nullable=False, index=True)
    price = Column(Float, nullable=False)
    image_path = Column(String(512), default="")
    brand_region = Column(String(64), default="未知")
    review_rating = Column(Float, default=0.0)
    marketing_description = Column(Text, default="")
    search_text = Column(Text, default="")
    extracted_terms = Column(JSON, default=list)
    faqs = Column(JSON, default=list)
    reviews = Column(JSON, default=list)
    version = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    source = Column(String(128), default="fixture")
    content_hash = Column(String(64), default="")

    skus = relationship("ProductSkuOrm", back_populates="product", cascade="all, delete-orphan")
    chunks = relationship("ProductChunkOrm", back_populates="product", cascade="all, delete-orphan")


class ProductSkuOrm(Base):
    __tablename__ = "product_skus"

    sku_id = Column(String(64), primary_key=True)
    product_id = Column(String(64), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    properties = Column(JSON, default=dict)
    price = Column(Float, nullable=False)
    product = relationship("ProductOrm", back_populates="skus")


class ProductChunkOrm(Base):
    __tablename__ = "product_chunks"

    chunk_id = Column(String(64), primary_key=True, default=lambda: f"chunk_{uuid.uuid4().hex[:12]}")
    product_id = Column(String(64), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    sku_id = Column(String(64), nullable=True, index=True)
    category_id = Column(String(128), nullable=True, index=True)
    chunk_type = Column(String(64), default="description", nullable=False, index=True)
    source_type = Column(String(64), default="official_detail")
    trust_level = Column(String(32), default="official")
    document_version = Column(Integer, default=1, nullable=False)
    content = Column(Text, default="")
    embedding = Column(Vector(384))
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    product = relationship("ProductOrm", back_populates="chunks")


class CartOrm(Base):
    __tablename__ = "carts"

    session_id = Column(String(128), primary_key=True)
    version = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    items = relationship("CartItemOrm", back_populates="cart", cascade="all, delete-orphan")


class CartItemOrm(Base):
    __tablename__ = "cart_items"

    item_id = Column(String(64), primary_key=True, default=lambda: f"ci_{uuid.uuid4().hex[:12]}")
    session_id = Column(String(128), ForeignKey("carts.session_id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(64), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    added_at = Column(DateTime(timezone=True), default=utc_now)
    cart = relationship("CartOrm", back_populates="items")


class AddressOrm(Base):
    __tablename__ = "addresses"

    address_id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    phone = Column(String(64), nullable=False)
    province = Column(String(128), nullable=False)
    city = Column(String(128), nullable=False)
    detail = Column(Text, default="")
    is_default = Column(Boolean, default=False)


class OrderOrm(Base):
    __tablename__ = "orders"

    order_id = Column(String(64), primary_key=True)
    session_id = Column(String(128), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    total_amount = Column(Float, default=0.0)
    confirmation_token = Column(String(128), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    address_id = Column(String(64), ForeignKey("addresses.address_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    address = relationship("AddressOrm")
    items = relationship("OrderItemOrm", back_populates="order", cascade="all, delete-orphan")


class OrderItemOrm(Base):
    __tablename__ = "order_items"

    item_id = Column(String(64), primary_key=True, default=lambda: f"oi_{uuid.uuid4().hex[:12]}")
    order_id = Column(String(64), ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(64), nullable=False)
    title = Column(String(512), nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    order = relationship("OrderOrm", back_populates="items")


class SessionOrm(Base):
    __tablename__ = "sessions"

    session_id = Column(String(128), primary_key=True)
    payload = Column(JSON, default=dict)
    schema_version = Column(Integer, default=1, nullable=False)
    last_activity_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)


class FeedbackEventOrm(Base):
    __tablename__ = "feedback_events"

    event_id = Column(String(64), primary_key=True, default=lambda: f"fe_{uuid.uuid4().hex[:12]}")
    session_id = Column(String(128), nullable=False, index=True)
    signal_type = Column(String(64), nullable=False)
    product_id = Column(String(64), nullable=True, index=True)
    rating = Column(Integer, nullable=True)
    action_label = Column(String(256), nullable=True)
    context = Column(JSON, default=dict)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class UserProfileOrm(Base):
    __tablename__ = "user_profiles"

    user_id = Column(String(128), primary_key=True)
    payload = Column(JSON, default=dict)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
```

- [ ] **Step 2: 创建并运行迁移脚本**

Run:
```bash
cd server
../env/venv_shopguide_backend/bin/alembic init migrations
```

编辑 `server/alembic.ini`：
```ini
[alembic]
script_location = migrations
prepend_sys_path = .
version_path_separator = os

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

编辑 `server/migrations/env.py`：
```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.app.db.base import Base
from backend.app.db.models import *  # noqa

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    return os.getenv("SHOPGUIDE_DATABASE_URL", "postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide")


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

生成初始迁移：
```bash
cd server
SHOPGUIDE_DATABASE_URL=postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide ../env/venv_shopguide_backend/bin/alembic revision --autogenerate -m "initial schema"
```

升级：
```bash
cd server
SHOPGUIDE_DATABASE_URL=postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide ../env/venv_shopguide_backend/bin/alembic upgrade head
```

Expected: 所有表创建成功，无报错。

- [ ] **Step 3: 提交**

```bash
git add server/alembic.ini server/migrations/ server/backend/app/db/models.py
git commit -m "feat(db): add ORM models and Alembic initial migration

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Repository 层与 CartService 数据库迁移

**Files:**
- Create: `server/backend/app/repositories/__init__.py`
- Create: `server/backend/app/repositories/cart_repository.py`
- Modify: `server/backend/app/cart.py`
- Create: `server/tests/test_cart_db.py`

**Interfaces:**
- Consumes: `CartOrm`, `CartItemOrm` from `server/backend/app/db/models.py`.
- Produces: `CartRepository` with `get(session_id)`, `add(session_id, product_id, quantity)`, `update_quantity(...)`, `remove(...)`, `clear(...)`, `checkout(...)`.

- [ ] **Step 1: 编写 `server/backend/app/repositories/__init__.py`**

```python
from .cart_repository import CartRepository
from .feedback_repository import FeedbackRepository
from .order_repository import OrderRepository
from .profile_repository import ProfileRepository
from .session_repository import SessionRepository

__all__ = ["CartRepository", "OrderRepository", "SessionRepository", "FeedbackRepository", "ProfileRepository"]
```

- [ ] **Step 2: 编写 `server/backend/app/repositories/cart_repository.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import CartItemOrm, CartOrm


class CartRepository:
    def __init__(self, db: Session):
        self.db = db

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def get(self, session_id: str) -> dict:
        cart = self.db.query(CartOrm).filter_by(session_id=session_id).first()
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
        cart = self.db.query(CartOrm).filter_by(session_id=session_id).first()
        if cart is None:
            cart = CartOrm(session_id=session_id)
            self.db.add(cart)
        item = next((i for i in cart.items if i.product_id == product_id), None)
        if item is None:
            item = CartItemOrm(session_id=session_id, product_id=product_id, quantity=quantity)
            cart.items.append(item)
        else:
            item.quantity += quantity
        cart.updated_at = self._now()
        self.db.flush()
        return self.get(session_id)

    def update_quantity(self, session_id: str, product_id: str, quantity: int) -> dict:
        cart = self.db.query(CartOrm).filter_by(session_id=session_id).first()
        if cart is None:
            return self.get(session_id)
        item = next((i for i in cart.items if i.product_id == product_id), None)
        if quantity == 0:
            if item:
                self.db.delete(item)
        elif item is not None:
            item.quantity = quantity
        else:
            item = CartItemOrm(session_id=session_id, product_id=product_id, quantity=quantity)
            cart.items.append(item)
        cart.updated_at = self._now()
        self.db.flush()
        return self.get(session_id)

    def remove(self, session_id: str, product_id: str) -> dict:
        cart = self.db.query(CartOrm).filter_by(session_id=session_id).first()
        if cart is None:
            return self.get(session_id)
        item = next((i for i in cart.items if i.product_id == product_id), None)
        if item:
            self.db.delete(item)
        cart.updated_at = self._now()
        self.db.flush()
        return self.get(session_id)

    def clear(self, session_id: str) -> dict:
        cart = self.db.query(CartOrm).filter_by(session_id=session_id).first()
        if cart:
            for item in list(cart.items):
                self.db.delete(item)
            cart.updated_at = self._now()
            self.db.flush()
        return self.get(session_id)

    def checkout(self, session_id: str) -> dict:
        return self.clear(session_id)
```

- [ ] **Step 3: 修改 `server/backend/app/cart.py` 支持数据库仓库**

保留原有文件接口不变，在 `__init__` 增加可选 `db_session` 参数，并在方法内部优先使用 repository：

```python
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

    def add(self, session_id: str, product_id: str, quantity: int = 1, idempotency_key: str | None = None):
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
```

（注：`_file_*` 为原有文件持久化方法的私有前缀重命名，保持逻辑不变。）

- [ ] **Step 4: 编写测试 `server/tests/test_cart_db.py`**

```python
import pytest

from backend.app.cart import CartService
from backend.app.db import Base, get_engine, get_session
from backend.app.db.models import CartItemOrm, CartOrm
from backend.app.models import Product


@pytest.fixture(scope="function")
def db():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    session = get_session()
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
    service.add("s1", "p1", 2)
    snapshot = service.get("s1")
    assert len(snapshot["items"]) == 1
    assert snapshot["items"][0]["quantity"] == 2
    assert snapshot["total_amount"] == 200.0
```

- [ ] **Step 5: 运行测试**

Run:
```bash
cd server
SHOPGUIDE_DATABASE_URL=postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide ../env/venv_shopguide_backend/bin/python -m pytest tests/test_cart_db.py -v
```

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add server/backend/app/repositories/ server/backend/app/cart.py server/tests/test_cart_db.py
git commit -m "feat(cart): migrate CartService to PostgreSQL repository

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: OrderService / SessionStore / FeedbackStore / UserProfileStore 数据库迁移

**Files:**
- Create: `server/backend/app/repositories/order_repository.py`
- Create: `server/backend/app/repositories/session_repository.py`
- Create: `server/backend/app/repositories/feedback_repository.py`
- Create: `server/backend/app/repositories/profile_repository.py`
- Modify: `server/backend/app/order_service.py`
- Modify: `server/backend/app/session_store.py`
- Modify: `server/backend/app/feedback_store.py`
- Modify: `server/backend/app/user_profile_store.py`

**Interfaces:**
- Consumes: ORM models from `server/backend/app/db/models.py`.
- Produces: Repositories exposing same semantics as original JSON stores.

- [ ] **Step 1-4: 依次创建 repository 文件**

每个 repository 提供与原 JSON store 等价的方法，例如：

`server/backend/app/repositories/order_repository.py`：
```python
from sqlalchemy.orm import Session
from backend.app.db.models import AddressOrm, OrderItemOrm, OrderOrm


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, order_id: str) -> OrderOrm | None:
        return self.db.query(OrderOrm).filter_by(order_id=order_id).first()

    def save(self, order: OrderOrm) -> None:
        existing = self.db.query(OrderOrm).filter_by(order_id=order.order_id).first()
        if existing is None:
            self.db.add(order)
        self.db.flush()

    def list_by_session(self, session_id: str) -> list[OrderOrm]:
        return self.db.query(OrderOrm).filter_by(session_id=session_id).all()
```

`server/backend/app/repositories/session_repository.py`：
```python
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.db.models import SessionOrm
from backend.app.models import SessionContext


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, session_id: str) -> SessionContext | None:
        row = self.db.query(SessionOrm).filter_by(session_id=session_id).first()
        if row is None:
            return None
        return SessionContext.model_validate(row.payload)

    def save(self, context: SessionContext) -> None:
        context.last_activity_at = datetime.now(timezone.utc).isoformat()
        row = self.db.query(SessionOrm).filter_by(session_id=context.session_id).first()
        if row is None:
            row = SessionOrm(session_id=context.session_id)
            self.db.add(row)
        row.payload = context.model_dump(mode="json")
        row.schema_version = context.schema_version
        row.last_activity_at = datetime.now(timezone.utc)
        self.db.flush()

    def cleanup_expired(self, ttl_days: int) -> None:
        from sqlalchemy import text
        cutoff = text("NOW() - INTERVAL '%s days'" % ttl_days)
        self.db.query(SessionOrm).filter(SessionOrm.last_activity_at < cutoff).delete(synchronize_session=False)
        self.db.flush()
```

`server/backend/app/repositories/feedback_repository.py`：
```python
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.db.models import FeedbackEventOrm
from backend.app.models import FeedbackEvent


class FeedbackRepository:
    def __init__(self, db: Session):
        self.db = db

    def record(self, event: FeedbackEvent) -> None:
        if not event.timestamp:
            event.timestamp = datetime.now(timezone.utc).isoformat()
        row = FeedbackEventOrm(
            session_id=event.session_id,
            signal_type=event.signal_type,
            product_id=event.product_id,
            rating=event.rating,
            action_label=event.action_label,
            context=event.context,
            timestamp=datetime.fromisoformat(event.timestamp),
        )
        self.db.add(row)
        self.db.flush()

    def get_all_events(self, session_id: str) -> list[FeedbackEvent]:
        rows = self.db.query(FeedbackEventOrm).filter_by(session_id=session_id).order_by(FeedbackEventOrm.timestamp).all()
        return [self._to_model(r) for r in rows]

    def count(self, session_id: str) -> int:
        return self.db.query(FeedbackEventOrm).filter_by(session_id=session_id).count()

    def _to_model(self, row: FeedbackEventOrm) -> FeedbackEvent:
        return FeedbackEvent(
            session_id=row.session_id,
            signal_type=row.signal_type,
            product_id=row.product_id,
            rating=row.rating,
            action_label=row.action_label,
            context=row.context,
            timestamp=row.timestamp.isoformat(),
        )
```

`server/backend/app/repositories/profile_repository.py`：
```python
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.db.models import UserProfileOrm
from backend.app.models import UserFeedbackProfile


class ProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: str) -> UserFeedbackProfile | None:
        row = self.db.query(UserProfileOrm).filter_by(user_id=user_id).first()
        if row is None:
            return None
        return UserFeedbackProfile.model_validate(row.payload)

    def save(self, profile: UserFeedbackProfile) -> None:
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        row = self.db.query(UserProfileOrm).filter_by(user_id=profile.user_id).first()
        if row is None:
            row = UserProfileOrm(user_id=profile.user_id)
            self.db.add(row)
        row.payload = profile.model_dump(mode="json")
        row.updated_at = datetime.now(timezone.utc)
        self.db.flush()
```

- [ ] **Step 5-8: 修改对应 service/store 文件**

为每个类增加可选 `db_session` 参数；若传入则使用 DB repository，否则保留原有 JSON 文件逻辑。保持公共方法签名不变。

- [ ] **Step 9: 编写集成测试**

Create `server/tests/test_db_stores.py`：
```python
import pytest
from backend.app.db import Base, get_engine, get_session
from backend.app.feedback_store import FeedbackStore
from backend.app.models import FeedbackEvent
from backend.app.order_service import OrderService
from backend.app.session_store import SessionStore
from backend.app.user_profile_store import UserProfileStore


@pytest.fixture(scope="function")
def db():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    session = get_session()
    yield session
    session.rollback()
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_session_store_roundtrip(db):
    store = SessionStore(db_session=db)
    ctx = store.get("sess_1")
    ctx.state.dialog_state.turn_index = 5
    store.save("sess_1")
    reloaded = store.get("sess_1")
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
```

- [ ] **Step 10: 运行测试**

Run:
```bash
cd server
SHOPGUIDE_DATABASE_URL=postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide ../env/venv_shopguide_backend/bin/python -m pytest tests/test_db_stores.py -v
```

Expected: PASS

- [ ] **Step 11: 提交**

```bash
git add server/backend/app/repositories/ server/backend/app/order_service.py server/backend/app/session_store.py server/backend/app/feedback_store.py server/backend/app/user_profile_store.py server/tests/test_db_stores.py
git commit -m "feat(db): migrate order/session/feedback/profile stores to PostgreSQL

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: 商品与向量 Seed 脚本

**Files:**
- Create: `server/backend/app/db/seed.py`
- Modify: `server/backend/app/data_loader.py`（可选，支持从 DB 加载）

**Interfaces:**
- Consumes: `ecommerce_agent_dataset/` JSON fixtures; `data_loader.load_products`.
- Produces: `seed_database(products, engine)` that populates `products`, `product_skus`, `product_chunks`.

- [ ] **Step 1: 编写 `server/backend/app/db/seed.py`**

```python
from __future__ import annotations

from sqlalchemy.orm import Session

from ..data_loader import load_products
from ..embedding_retriever import EmbeddingRetriever
from ..models import Product
from .base import Base
from .engine import get_engine
from .models import ProductChunkOrm, ProductOrm, ProductSkuOrm


def seed_products(products: list[Product], session: Session, embedder: EmbeddingRetriever | None = None):
    for p in products:
        orm = ProductOrm(
            product_id=p.product_id,
            title=p.title,
            brand=p.brand,
            category=p.category,
            sub_category=p.sub_category,
            price=p.price,
            image_path=p.image_path,
            brand_region=p.brand_region,
            review_rating=p.review_rating,
            marketing_description=p.marketing_description,
            search_text=p.search_text,
            extracted_terms=p.extracted_terms,
            faqs=p.faqs,
            reviews=p.reviews,
        )
        session.merge(orm)
        for sku in p.skus:
            session.merge(ProductSkuOrm(
                sku_id=sku.sku_id,
                product_id=p.product_id,
                properties=sku.properties,
                price=sku.price,
            ))
        chunk_text = p.chunk or f"{p.title} {p.marketing_description} {p.search_text}".strip()
        embedding = None
        if embedder and embedder.model is not None:
            embedding = embedder.model.encode([chunk_text], normalize_embeddings=True).tolist()[0]
        session.merge(ProductChunkOrm(
            chunk_id=f"chunk_{p.product_id}",
            product_id=p.product_id,
            category_id=p.category,
            chunk_type="description",
            source_type="fixture",
            trust_level="official",
            document_version=1,
            content=chunk_text,
            embedding=embedding,
        ))
    session.commit()


def seed_database(settings=None, products: list[Product] | None = None):
    from ..config import get_settings
    settings = settings or get_settings()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    if products is None:
        products = load_products(settings.dataset_path)
    from ..embedding_retriever import EmbeddingRetriever
    embedder = EmbeddingRetriever(products, settings.embedding_path, settings.embedding_device, settings.use_embedding)
    with Session(engine) as session:
        seed_products(products, session, embedder)


if __name__ == "__main__":
    seed_database()
```

- [ ] **Step 2: 运行 seed 脚本**

Run:
```bash
cd server
SHOPGUIDE_DATABASE_URL=postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide ../env/venv_shopguide_backend/bin/python -m backend.app.db.seed
```

Expected: 商品、SKU、chunk 入库成功。

- [ ] **Step 3: 验证向量索引**

Run:
```bash
psql -U shopguide -d shopguide -c "SELECT product_id, chunk_type FROM product_chunks LIMIT 5;"
```

Expected: 输出 5 条记录。

- [ ] **Step 4: 提交**

```bash
git add server/backend/app/db/seed.py
git commit -m "feat(db): add product and vector seed script

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: 更新 `main.py` 使用数据库服务

**Files:**
- Modify: `server/backend/app/main.py`

**Interfaces:**
- Consumes: DB engine/session, repositories.
- Produces: `create_app()` wires DB-backed services when `database_url` is set.

- [ ] **Step 1: 修改 `create_app()` 注入数据库 session**

```python
from .db import get_session, init_db
from .repositories import CartRepository, OrderRepository, SessionRepository, FeedbackRepository, ProfileRepository

def create_app(...):
    settings = get_settings()
    # ... existing setup ...

    if settings.database_url:
        init_db()

    def _get_db():
        db = get_session()
        try:
            yield db
        finally:
            db.close()

    # 在需要时传入 db_session
    # 注意：原有 create_app 内部是同步构造，FastAPI 依赖注入用于请求级 session。
    # 对 WebSocket 和启动时构造的服务，需要创建一个 scoped session 或延迟获取。
```

由于当前 `create_app` 在模块导入时构造服务，需要调整服务构造方式，使其在请求/WebSocket 处理时获取 session。最小改动方案：
- 保留文件服务作为默认；
- 当 `database_url` 存在时，使用一个全局同步 `Session` 用于服务构造（适合单 worker 演示），并在应用关闭时关闭。

更生产化的方案是将服务改为按请求获取 session，但这会改动较大。本计划采用最小兼容方案：单全局 session。

```python
    db_session = None
    if settings.database_url:
        init_db()
        db_session = get_session()

    cart = CartService(products, settings.cart_path or None, db_session=db_session)
    order_service = OrderService(cart, settings.session_dir or None, db_session=db_session)
    session_store = SessionStore(settings.session_dir or None, ttl_days=settings.session_ttl_days, db_session=db_session)
    feedback_store = FeedbackStore(settings.feedback_path or None, db_session=db_session)
    user_profile_store = UserProfileStore(settings.user_profile_dir or None, db_session=db_session)
```

并在 `@app.on_event("shutdown")` 中关闭 `db_session`。

- [ ] **Step 2: 运行原有测试确保兼容**

Run:
```bash
cd server
SHOPGUIDE_DATABASE_URL=postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide ../env/venv_shopguide_backend/bin/python -m pytest tests/test_api.py tests/test_agent_core.py -v
```

Expected: 原有测试通过。

- [ ] **Step 3: 提交**

```bash
git add server/backend/app/main.py
git commit -m "feat(main): wire database-backed services into FastAPI app

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: 全量测试与验收

**Files:**
- Modify: `server/tests/conftest.py`

**Interfaces:**
- Produces: Test fixtures for in-memory SQLite or test PostgreSQL.

- [ ] **Step 1: 更新 `server/tests/conftest.py` 提供测试数据库**

```python
import pytest
from backend.app.db import Base, get_engine


@pytest.fixture(scope="function", autouse=True)
def reset_database():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
```

- [ ] **Step 2: 运行全量后端测试**

Run:
```bash
cd server
SHOPGUIDE_DATABASE_URL=postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide_test ../env/venv_shopguide_backend/bin/python -m pytest tests/ -v --tb=short
```

Expected: 所有测试通过（可能需要针对仍使用文件路径的测试做局部调整）。

- [ ] **Step 3: 运行后端冒烟测试**

Run:
```bash
SHOPGUIDE_DATABASE_URL=postgresql+psycopg://shopguide:shopguide@localhost:5432/shopguide ARK_API_KEY="" bash server/scripts/start_backend.sh
```

Expected: 后端启动成功，`/health` 返回 `ok`。

- [ ] **Step 4: 提交**

```bash
git add server/tests/conftest.py
git commit -m "test: add test database reset fixture and verify full suite

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- 依赖锁定：Task 1 ✅
- PostgreSQL + pgvector + SQLAlchemy + Alembic：Tasks 2-3 ✅
- 文件持久化迁移到数据库：Tasks 4-5 ✅
- Seed 脚本：Task 6 ✅
- 原有测试仍通过：Task 7-8 ✅

**2. Placeholder scan:**
- 无 "TBD" / "TODO" / "implement later"。
- `cart.py` 的完整 DB 分支在实现时需要展开为多个私有方法，计划中已给出模式。

**3. Type consistency:**
- `CartRepository.get()` 返回原始 dict；`CartService` 负责组装带价格的 UI snapshot，与现有接口一致。
- ORM 模型字段名与 Pydantic 模型一致。

**4. 已知风险与后续工作：**
- `main.py` 使用单全局 session，适合单 worker；多 worker 场景需改用请求级 session 或连接池。
- 向量维度 384 需与 `bge-small-zh-v1.5` 一致；若使用其他模型需调整。
- 里程碑 B（RAG 增强）将基于本计划的 `product_chunks` 表继续拆分 chunk。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-20-database-and-dependency-baseline.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
