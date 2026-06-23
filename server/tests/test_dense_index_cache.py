"""Phase 1 验证：dense index 持久化缓存的一致性。

ProductChunk.embedding 作为冷启动加速的持久化缓存：
- build_dense_index 直接从内存矩阵构造
- load_dense_index_from_db 从 SQLite 反序列化重建
- 两条路径在同一份数据下应得到完全一致的检索结果
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models import Product as ProductOrm, ProductChunk
from backend.app.models import HardConstraints, Product
from backend.app.rag.vector_search import (
    build_dense_index,
    load_dense_index_from_db,
)


def _make_product(pid: str, category: str = "美妆护肤", sub: str = "防晒") -> Product:
    return Product(
        product_id=pid,
        title=pid,
        brand="BrandA",
        category=category,
        sub_category=sub,
        price=99.0,
        image_path="",
        chunk=f"{pid} 防晒",
        search_text=f"{pid} 防晒",
    )


def _seed_db(session: Session, products: list[Product], embeddings: np.ndarray) -> None:
    for product in products:
        session.add(
            ProductOrm(
                product_id=product.product_id,
                title=product.title,
                brand=product.brand,
                category=product.category,
                sub_category=product.sub_category,
                price=product.price,
                image_path="",
                chunk=product.chunk,
                search_text=product.search_text,
            )
        )
    for idx, product in enumerate(products):
        session.add(
            ProductChunk(
                chunk_id=f"c_{product.product_id}",
                product_id=product.product_id,
                category_id=product.category,
                sub_category=product.sub_category,
                chunk_type="description",
                source_type="fixture",
                trust_level="official",
                document_version=1,
                content=product.chunk,
                embedding=embeddings[idx].tolist(),
                is_active=True,
            )
        )
    session.commit()


def test_build_dense_index_basic():
    products = [_make_product("p1"), _make_product("p2")]
    embeddings = np.asarray([[1.0, 0.0], [0.0, 1.0]])
    index = build_dense_index(products, embeddings)

    assert index.product_ids == ["p1", "p2"]
    assert index.matrix.shape == (2, 2)
    assert not index.is_empty


def test_build_dense_index_returns_empty_on_mismatch():
    products = [_make_product("p1"), _make_product("p2")]
    # 维度 / 行数不匹配 → 返回空 index 而非崩溃
    bad_embeddings = np.asarray([[1.0, 0.0]])  # 只有 1 行
    index = build_dense_index(products, bad_embeddings)
    assert index.is_empty


def test_build_dense_index_returns_empty_on_none():
    products = [_make_product("p1")]
    index = build_dense_index(products, None)
    assert index.is_empty
    # 空 index 上的 search 应返回空 list 而非异常
    results = index.search(np.asarray([1.0, 0.0]), HardConstraints(), top_k=5)
    assert results == []


def test_load_dense_index_from_db_matches_build():
    """从 DB 反序列化的 index 与内存构造的 index 检索结果一致。"""
    products = [_make_product("p1"), _make_product("p2"), _make_product("p3")]
    embeddings = np.asarray([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]])

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        _seed_db(session, products, embeddings)
        loaded = load_dense_index_from_db(session, products, expected_dim=2)

    memory_index = build_dense_index(products, embeddings)

    assert loaded is not None
    assert loaded.product_ids == memory_index.product_ids

    query = np.asarray([0.9, 0.1])
    loaded_results = loaded.search(query, HardConstraints(), top_k=5)
    memory_results = memory_index.search(query, HardConstraints(), top_k=5)

    assert [pid for pid, _ in loaded_results] == [pid for pid, _ in memory_results]


def test_load_dense_index_from_db_returns_none_on_dim_mismatch():
    """期望维度与 DB 中向量不匹配时返回 None，触发上层重新编码。"""
    products = [_make_product("p1"), _make_product("p2")]
    embeddings = np.asarray([[1.0, 0.0], [0.0, 1.0]])  # 维度=2

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        _seed_db(session, products, embeddings)
        # 期望维度 384，与 DB 中 2 维向量不匹配
        loaded = load_dense_index_from_db(session, products, expected_dim=384)

    assert loaded is None


def test_load_dense_index_returns_none_when_missing_products():
    """部分商品在 DB 中没有嵌入时返回 None，避免拼出残缺 index。"""
    products = [_make_product("p1"), _make_product("p2")]
    embeddings_for_one = np.asarray([[1.0, 0.0]])

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        # 只 seed p1
        _seed_db(session, products[:1], embeddings_for_one)
        loaded = load_dense_index_from_db(session, products, expected_dim=2)

    assert loaded is None
