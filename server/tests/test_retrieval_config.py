"""Phase 1 验证：四种融合策略切换正确。

确保 RetrievalConfig 是检索层超参的唯一来源，HybridRetriever 按策略
返回的 product_id 集合符合预期。
"""

from __future__ import annotations

import numpy as np

from backend.app.config import RetrievalConfig
from backend.app.models import HardConstraints, Product, RetrievalPlan
from backend.app.rag.fusion import HybridRetriever, rrf_fuse, weighted_fuse
from backend.app.rag.vector_search import DenseIndex


def _make_product(pid: str, brand: str = "BrandA", category: str = "美妆护肤", sub: str = "防晒") -> Product:
    return Product(
        product_id=pid,
        title=pid,
        brand=brand,
        category=category,
        sub_category=sub,
        price=99.0,
        image_path="",
        chunk=f"{pid} 防晒 清爽",
        search_text=f"{pid} 防晒 清爽",
    )


def _make_dense_index(products: list[Product]) -> DenseIndex:
    """每个 product 一个 one-hot 向量，便于精确控制 dense 分数。"""
    dim = len(products)
    matrix = np.eye(dim, dtype=float)
    return DenseIndex(
        product_ids=[p.product_id for p in products],
        matrix=matrix,
        product_meta={p.product_id: (p.category, p.sub_category) for p in products},
    )


class _FakeBaseRetriever:
    """模拟 EmbeddingRetriever：暴露 products 列表 + 可控的 model.encode。"""

    def __init__(self, products: list[Product], query_vec: np.ndarray | None):
        self.products = products
        self._query_vec = query_vec
        self.model = self if query_vec is not None else None

    def encode(self, queries, normalize_embeddings=True, convert_to_numpy=True):
        return np.asarray([self._query_vec])


def _session_factory_factory(rows):
    """构造一个返回固定 lexical chunks 的 session factory，避免依赖真实 DB。"""

    class _StubSession:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *args):
            return False

    return lambda: _StubSession()


def test_rrf_fuse_pure_logic():
    lexical = [("p1", 10.0), ("p2", 8.0), ("p3", 1.0)]
    vector = [("p2", 0.9), ("p4", 0.8), ("p1", 0.1)]
    fused = rrf_fuse(lexical, vector, top_k=4, k=60)
    assert [pid for pid, _ in fused][:2] == ["p2", "p1"]


def test_weighted_fuse_respects_dense_weight():
    lexical = [("p1", 1.0), ("p2", 0.0)]
    vector = [("p2", 1.0), ("p1", 0.0)]
    # dense_weight=0.8 → p2 应排在前面（0.8 vs 0.2）
    fused = weighted_fuse(lexical, vector, dense_weight=0.8, top_k=2)
    assert fused[0][0] == "p2"
    # dense_weight=0.2 → p1 排前面
    fused = weighted_fuse(lexical, vector, dense_weight=0.2, top_k=2)
    assert fused[0][0] == "p1"


def test_retrieval_config_bm25_weight_complement():
    config = RetrievalConfig(dense_weight=0.7)
    assert abs(config.bm25_weight - 0.3) < 1e-9


def test_dense_index_filters_by_category():
    p1 = _make_product("p1", category="美妆护肤", sub="防晒")
    p2 = _make_product("p2", category="数码电子", sub="手机")
    index = _make_dense_index([p1, p2])
    # 查询向量倾向 p1
    query = np.asarray([1.0, 0.0])
    results = index.search(query, HardConstraints(category="美妆护肤"), top_k=5)
    assert [pid for pid, _ in results] == ["p1"]


def test_hybrid_retriever_dense_only_skips_lexical(monkeypatch):
    """dense_only 策略下不应调用 lexical_search_chunks。"""
    products = [_make_product("p1"), _make_product("p2")]
    dense_index = _make_dense_index(products)
    base = _FakeBaseRetriever(products, query_vec=np.asarray([1.0, 0.0]))

    called = {"lexical": 0}

    def _spy_lexical(*args, **kwargs):
        called["lexical"] += 1
        return [("p2", 1.0)]

    monkeypatch.setattr("backend.app.rag.fusion.lexical_search_chunks", _spy_lexical)

    retriever = HybridRetriever(
        base,
        session_factory=_session_factory_factory([]),
        config=RetrievalConfig(fusion_strategy="dense_only"),
        dense_index=dense_index,
    )
    results = retriever.search(RetrievalPlan(retrieval_query="any"), top_k=2)

    assert called["lexical"] == 0
    assert results[0][0].product_id == "p1"


def test_hybrid_retriever_bm25_only_skips_dense(monkeypatch):
    """bm25_only 策略下不应调用 dense encode。"""
    products = [_make_product("p1"), _make_product("p2")]
    dense_index = _make_dense_index(products)
    base = _FakeBaseRetriever(products, query_vec=np.asarray([1.0, 0.0]))

    def _spy_lexical(*args, **kwargs):
        return [("p2", 1.0), ("p1", 0.5)]

    monkeypatch.setattr("backend.app.rag.fusion.lexical_search_chunks", _spy_lexical)

    encode_calls = {"count": 0}
    original_encode = base.encode

    def _counting_encode(*args, **kwargs):
        encode_calls["count"] += 1
        return original_encode(*args, **kwargs)

    base.encode = _counting_encode

    retriever = HybridRetriever(
        base,
        session_factory=_session_factory_factory([]),
        config=RetrievalConfig(fusion_strategy="bm25_only"),
        dense_index=dense_index,
    )
    results = retriever.search(RetrievalPlan(retrieval_query="any"), top_k=2)

    assert encode_calls["count"] == 0
    assert results[0][0].product_id == "p2"


def test_hybrid_retriever_weighted_uses_config_weight(monkeypatch):
    """weighted 策略下 dense_weight 切换会改变排序结果。"""
    products = [_make_product("p1"), _make_product("p2")]
    dense_index = _make_dense_index(products)
    base = _FakeBaseRetriever(products, query_vec=np.asarray([1.0, 0.0]))  # dense 偏向 p1

    def _spy_lexical(*args, **kwargs):
        # BM25 偏向 p2
        return [("p2", 1.0), ("p1", 0.0)]

    monkeypatch.setattr("backend.app.rag.fusion.lexical_search_chunks", _spy_lexical)

    # dense_weight=0.9 → p1 在前
    retriever = HybridRetriever(
        base,
        session_factory=_session_factory_factory([]),
        config=RetrievalConfig(fusion_strategy="weighted", dense_weight=0.9),
        dense_index=dense_index,
    )
    results = retriever.search(RetrievalPlan(retrieval_query="any"), top_k=2)
    assert results[0][0].product_id == "p1"

    # dense_weight=0.1 → p2 在前
    retriever = HybridRetriever(
        base,
        session_factory=_session_factory_factory([]),
        config=RetrievalConfig(fusion_strategy="weighted", dense_weight=0.1),
        dense_index=dense_index,
    )
    results = retriever.search(RetrievalPlan(retrieval_query="any"), top_k=2)
    assert results[0][0].product_id == "p2"


def test_hybrid_retriever_rrf_strategy(monkeypatch):
    """rrf 策略下输出符合 RRF 公式。"""
    products = [_make_product("p1"), _make_product("p2"), _make_product("p3")]
    dense_index = _make_dense_index(products)
    base = _FakeBaseRetriever(products, query_vec=np.asarray([1.0, 0.0, 0.0]))  # dense: p1 > p2 > p3

    def _spy_lexical(*args, **kwargs):
        return [("p2", 1.0), ("p3", 0.8), ("p1", 0.1)]  # BM25: p2 > p3 > p1

    monkeypatch.setattr("backend.app.rag.fusion.lexical_search_chunks", _spy_lexical)

    retriever = HybridRetriever(
        base,
        session_factory=_session_factory_factory([]),
        config=RetrievalConfig(fusion_strategy="rrf", rrf_k=60),
        dense_index=dense_index,
    )
    results = retriever.search(RetrievalPlan(retrieval_query="any"), top_k=3)
    # p2 在 dense 第二、lexical 第一 → 综合最高
    # p1 在 dense 第一、lexical 第三 → 次之
    ids = [r[0].product_id for r in results]
    assert ids[0] == "p2"
    assert set(ids) == {"p1", "p2", "p3"}
