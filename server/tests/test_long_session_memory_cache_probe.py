from __future__ import annotations

from backend.app.memory_cache import RecommendationMemoryCache, StructuredMemoryCache
from backend.app.models import HardConstraints, Product, RankedProduct, RetrievalPlan


def _make_product(pid: str = "p1") -> Product:
    return Product(
        product_id=pid,
        title="测试商品",
        brand="测试",
        category="美妆护肤",
        sub_category="防晒",
        price=199.0,
        image_path="",
        marketing_description="",
        faqs=[],
        reviews=[],
        extracted_terms=[],
    )


def _make_plan() -> RetrievalPlan:
    return RetrievalPlan(
        intent="recommend_product",
        retrieval_mode="vector",
        retrieval_query="防晒霜",
        category="美妆护肤",
        hard_constraints=HardConstraints(category="美妆护肤"),
    )


def test_structured_cache_disable_get_returns_none():
    cache = StructuredMemoryCache()
    plan = _make_plan()
    product = _make_product()
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="", evidence=[])]
    cache.put(plan, ranked)
    # 默认 get 命中
    assert cache.get(plan, {product.product_id: product}) is not None
    # disable_get 时返回 None
    assert cache.get(plan, {product.product_id: product}, disable_get=True) is None


def test_structured_cache_probe_does_not_mutate_stats():
    cache = StructuredMemoryCache()
    plan = _make_plan()
    product = _make_product()
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="", evidence=[])]
    cache.put(plan, ranked)
    stats_before = dict(cache.stats())
    for _ in range(100):
        cache.probe(plan, {product.product_id: product})
    stats_after = dict(cache.stats())
    assert stats_before == stats_after


def test_structured_cache_probe_returns_hit_status():
    cache = StructuredMemoryCache()
    plan = _make_plan()
    product = _make_product()
    # 空 cache → probe False
    assert cache.probe(plan, {product.product_id: product}) is False
    # put 后 probe True
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="", evidence=[])]
    cache.put(plan, ranked)
    assert cache.probe(plan, {product.product_id: product}) is True


def test_recommendation_cache_disable_get_returns_none():
    cache = RecommendationMemoryCache()
    plan = _make_plan()
    product = _make_product()
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="主推", evidence=[])]
    cache.put(plan, "我要防晒霜", ranked)
    assert cache.get(plan, "我要防晒霜", {product.product_id: product}) is not None
    assert cache.get(plan, "我要防晒霜", {product.product_id: product}, disable_get=True) is None


def test_recommendation_cache_probe_does_not_mutate_stats():
    cache = RecommendationMemoryCache()
    plan = _make_plan()
    product = _make_product()
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="主推", evidence=[])]
    cache.put(plan, "我要防晒霜", ranked)
    stats_before = dict(cache.stats())
    for _ in range(100):
        cache.probe(plan, "我要防晒霜", {product.product_id: product})
    stats_after = dict(cache.stats())
    assert stats_before == stats_after


def test_recommendation_cache_probe_returns_hit_status():
    cache = RecommendationMemoryCache()
    plan = _make_plan()
    product = _make_product()
    assert cache.probe(plan, "我要防晒霜", {product.product_id: product}) is False
    ranked = [RankedProduct(product=product, score=1.0, tier=1, reason="主推", evidence=[])]
    cache.put(plan, "我要防晒霜", ranked)
    assert cache.probe(plan, "我要防晒霜", {product.product_id: product}) is True
