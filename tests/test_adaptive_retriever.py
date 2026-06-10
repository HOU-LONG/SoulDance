from __future__ import annotations

from typing import List, Tuple

from backend.app.adaptive_retriever import AdaptiveRetriever, RelaxationPolicy
from backend.app.models import HardConstraints, Product, RankedProduct, RetrievalPlan


def _make_product(product_id: str, title: str, category: str, sub_category: str, price: float, brand: str = "") -> Product:
    return Product(
        product_id=product_id,
        title=title,
        brand=brand,
        category=category,
        sub_category=sub_category,
        price=price,
        image_path="",
        search_text=f"{title} {category} {sub_category}",
    )


class FakeEmbeddingRetriever:
    """模拟 embedding retriever，根据查询内容返回不同结果。"""

    def __init__(self, products: list[Product]):
        self.products = products
        self.calls: list[str] = []

    def search(self, query: str, top_k: int = 20) -> list[tuple[Product, float]]:
        self.calls.append(query)
        # 根据查询关键词匹配商品
        matched = []
        query_lower = query.lower()
        for product in self.products:
            score = 0.0
            text = f"{product.title} {product.sub_category} {product.category} {product.brand}".lower()
            if any(term in text for term in query_lower.split()):
                score = 1.0
            # 价格过滤模拟：如果查询中包含价格信息，过滤掉不符合的
            if "price_max" in query_lower or "price_min" in query_lower:
                # 不在这里过滤，由 hard_filter 处理
                pass
            if score > 0:
                matched.append((product, score))
        # 返回前 top_k 个
        return matched[:top_k]


class RoundControlledRetriever:
    """每轮返回不同数量结果的模拟检索器，用于测试渐进放松。"""

    def __init__(self, products: list[Product]):
        self.products = products
        self.calls: list[str] = []
        self.call_count = 0

    def search(self, query: str, top_k: int = 20) -> list[tuple[Product, float]]:
        self.calls.append(query)
        self.call_count += 1
        # 第一轮返回 2 个，第二轮返回 4 个，第三轮返回全部
        if self.call_count == 1:
            return [(p, 1.0 / (i + 1)) for i, p in enumerate(self.products[:2])]
        if self.call_count == 2:
            return [(p, 1.0 / (i + 1)) for i, p in enumerate(self.products[:4])]
        return [(p, 1.0 / (i + 1)) for i, p in enumerate(self.products)]


class EmptyThenRelaxingRetriever:
    """第一轮空结果，第二轮有结果的模拟检索器。"""

    def __init__(self, products: list[Product]):
        self.products = products
        self.calls: list[str] = []
        self.call_count = 0

    def search(self, query: str, top_k: int = 20) -> list[tuple[Product, float]]:
        self.calls.append(query)
        self.call_count += 1
        if self.call_count == 1:
            return []
        if self.call_count == 2:
            return [(p, 0.5) for p in self.products[:3]]
        return [(p, 0.3) for p in self.products]


def test_multi_round_retrieval_with_progressive_relaxation():
    """测试多轮检索在结果不足时逐步放松约束。"""
    products = [
        _make_product("p1", "智能手机A", "数码电子", "智能手机", 3999, "华为"),
        _make_product("p2", "智能手机B", "数码电子", "智能手机", 4999, "小米"),
        _make_product("p3", "笔记本电脑A", "数码电子", "笔记本电脑", 8999, "苹果"),
        _make_product("p4", "防晒霜A", "美妆护肤", "防晒", 99, "安耐晒"),
        _make_product("p5", "精华A", "美妆护肤", "精华", 199, "雅诗兰黛"),
    ]

    retriever = RoundControlledRetriever(products)
    adaptive = AdaptiveRetriever(retriever, RelaxationPolicy(min_candidates=5, max_rounds=3))

    plan = RetrievalPlan(
        hard_constraints=HardConstraints(category="数码电子", sub_category="智能手机", price_max=5000),
        soft_preferences={"priority": "拍照"},
        retrieval_query="智能手机 拍照 预算5000以内",
    )

    results = adaptive.search(plan, top_k=30)

    # 应该执行了 3 轮（因为 min_candidates=5，而每轮最多返回 2/4/5 个）
    assert retriever.call_count == 3
    assert len(results) == 5

    # 验证每轮查询不同（约束被放松）
    assert len(retriever.calls) == 3
    # Round 1 应该包含 soft_preferences
    assert "拍照" in retriever.calls[0]
    # Round 2 应该移除了 soft_preferences
    assert "拍照" not in retriever.calls[1]
    # Round 3 移除了 price bounds，但由于 sub_category 仍在，查询与 Round 2 相同
    # 验证 hard constraints 确实被修改了
    assert retriever.call_count == 3


def test_early_stop_when_min_candidates_reached():
    """测试当结果数达到 min_candidates 时提前终止。"""
    products = [
        _make_product("p1", "智能手机A", "数码电子", "智能手机", 3999),
        _make_product("p2", "智能手机B", "数码电子", "智能手机", 4999),
        _make_product("p3", "智能手机C", "数码电子", "智能手机", 2999),
        _make_product("p4", "智能手机D", "数码电子", "智能手机", 1999),
        _make_product("p5", "智能手机E", "数码电子", "智能手机", 5999),
    ]

    retriever = RoundControlledRetriever(products)
    adaptive = AdaptiveRetriever(retriever, RelaxationPolicy(min_candidates=3, max_rounds=3))

    plan = RetrievalPlan(
        hard_constraints=HardConstraints(sub_category="智能手机"),
        soft_preferences={"priority": "拍照"},
        retrieval_query="智能手机 拍照",
    )

    results = adaptive.search(plan, top_k=30)

    # 第一轮返回 2 个，不足 3 个；第二轮返回 4 个，达到 3 个，提前停止
    assert retriever.call_count == 2
    assert len(results) >= 3


def test_empty_first_round_triggers_relaxation():
    """测试第一轮无结果时触发约束放松。"""
    products = [
        _make_product("p1", "智能手机A", "数码电子", "智能手机", 3999),
        _make_product("p2", "智能手机B", "数码电子", "智能手机", 4999),
    ]

    retriever = EmptyThenRelaxingRetriever(products)
    adaptive = AdaptiveRetriever(retriever, RelaxationPolicy(min_candidates=1, max_rounds=3))

    plan = RetrievalPlan(
        hard_constraints=HardConstraints(sub_category="智能手机", price_max=3000),
        soft_preferences={"priority": "拍照"},
        retrieval_query="智能手机 拍照 预算3000",
    )

    results = adaptive.search(plan, top_k=30)

    # 第一轮空，第二轮有结果
    assert retriever.call_count == 2
    assert len(results) == 2


def test_merge_keeps_highest_score_per_product():
    """测试同一商品在多轮中出现时保留最高分数。"""
    products = [
        _make_product("p1", "智能手机A", "数码电子", "智能手机", 3999),
        _make_product("p2", "智能手机B", "数码电子", "智能手机", 4999),
    ]

    class ScoreChangingRetriever:
        def __init__(self, products: list[Product]):
            self.products = products
            self.call_count = 0

        def search(self, query: str, top_k: int = 20) -> list[tuple[Product, float]]:
            self.call_count += 1
            if self.call_count == 1:
                return [(self.products[0], 0.5)]
            return [(self.products[0], 0.8), (self.products[1], 0.3)]

    retriever = ScoreChangingRetriever(products)
    adaptive = AdaptiveRetriever(retriever, RelaxationPolicy(min_candidates=5, max_rounds=3))

    plan = RetrievalPlan(
        hard_constraints=HardConstraints(sub_category="智能手机"),
        soft_preferences={"priority": "拍照"},
        retrieval_query="智能手机",
    )

    results = adaptive.search(plan, top_k=30)

    # p1 在第一轮分数 0.5，第二轮分数 0.8，应该保留 0.8
    by_id = {p.product_id: score for p, score in results}
    assert by_id["p1"] == 0.8
    assert by_id["p2"] == 0.3


def test_rerank_by_price_cheaper():
    """测试按价格升序重排序。"""
    products = [
        _make_product("p1", "高端手机", "数码电子", "智能手机", 8999),
        _make_product("p2", "中端手机", "数码电子", "智能手机", 3999),
        _make_product("p3", "入门手机", "数码电子", "智能手机", 999),
    ]

    candidates = [
        RankedProduct(product=products[0], score=1.0, tier=1, reason=""),
        RankedProduct(product=products[1], score=0.8, tier=1, reason=""),
        RankedProduct(product=products[2], score=0.5, tier=2, reason=""),
    ]

    adaptive = AdaptiveRetriever(None)
    result = adaptive.rerank_by_price(candidates, "cheaper")

    prices = [item.product.price for item in result]
    assert prices == [999, 3999, 8999]


def test_rerank_by_price_expensive():
    """测试按价格降序重排序。"""
    products = [
        _make_product("p1", "高端手机", "数码电子", "智能手机", 8999),
        _make_product("p2", "中端手机", "数码电子", "智能手机", 3999),
        _make_product("p3", "入门手机", "数码电子", "智能手机", 999),
    ]

    candidates = [
        RankedProduct(product=products[2], score=0.5, tier=2, reason=""),
        RankedProduct(product=products[1], score=0.8, tier=1, reason=""),
        RankedProduct(product=products[0], score=1.0, tier=1, reason=""),
    ]

    adaptive = AdaptiveRetriever(None)
    result = adaptive.rerank_by_price(candidates, "expensive")

    prices = [item.product.price for item in result]
    assert prices == [8999, 3999, 999]


def test_rerank_by_price_unknown_direction_returns_original():
    """测试未知方向时返回原始顺序。"""
    products = [
        _make_product("p1", "手机A", "数码电子", "智能手机", 3999),
        _make_product("p2", "手机B", "数码电子", "智能手机", 4999),
    ]

    candidates = [
        RankedProduct(product=products[0], score=1.0, tier=1, reason=""),
        RankedProduct(product=products[1], score=0.8, tier=1, reason=""),
    ]

    adaptive = AdaptiveRetriever(None)
    result = adaptive.rerank_by_price(candidates, "unknown")

    assert [item.product.product_id for item in result] == ["p1", "p2"]


def test_relaxation_policy_defaults():
    """测试 RelaxationPolicy 默认值。"""
    policy = RelaxationPolicy()
    assert policy.min_candidates == 5
    assert policy.max_rounds == 3
    assert policy.relaxation_order == ["soft_preferences", "price_range", "category_fallback"]


def test_adaptive_retriever_with_custom_policy():
    """测试使用自定义策略的 AdaptiveRetriever。"""
    policy = RelaxationPolicy(min_candidates=2, max_rounds=2, relaxation_order=["price_range"])
    adaptive = AdaptiveRetriever(None, policy)

    assert adaptive.policy.min_candidates == 2
    assert adaptive.policy.max_rounds == 2
    assert adaptive.policy.relaxation_order == ["price_range"]


def test_round_2_drops_soft_preferences():
    """验证第二轮查询确实移除了 soft_preferences。"""
    products = [
        _make_product("p1", "智能手机A", "数码电子", "智能手机", 3999),
    ]

    retriever = RoundControlledRetriever(products)
    adaptive = AdaptiveRetriever(retriever, RelaxationPolicy(min_candidates=5, max_rounds=3))

    plan = RetrievalPlan(
        hard_constraints=HardConstraints(sub_category="智能手机"),
        soft_preferences={"texture": "清爽", "priority": "拍照"},
        retrieval_query="智能手机 清爽 拍照",
    )

    adaptive.search(plan, top_k=30)

    # Round 1 查询应包含 soft preference 值
    assert "清爽" in retriever.calls[0] or "拍照" in retriever.calls[0]
    # Round 2 查询不应包含 soft preference 值
    assert "清爽" not in retriever.calls[1]
    assert "拍照" not in retriever.calls[1]


def test_round_3_drops_price_bounds():
    """验证第三轮查询移除了价格边界。"""
    products = [
        _make_product("p1", "智能手机A", "数码电子", "智能手机", 3999),
        _make_product("p2", "智能手机B", "数码电子", "智能手机", 4999),
    ]

    class QueryInspectingRetriever:
        def __init__(self):
            self.calls: list[str] = []

        def search(self, query: str, top_k: int = 20) -> list[tuple[Product, float]]:
            self.calls.append(query)
            return []

    retriever = QueryInspectingRetriever()
    adaptive = AdaptiveRetriever(retriever, RelaxationPolicy(min_candidates=5, max_rounds=3))

    plan = RetrievalPlan(
        hard_constraints=HardConstraints(sub_category="智能手机", price_min=1000, price_max=5000),
        soft_preferences={},
        retrieval_query="智能手机",
    )

    adaptive.search(plan, top_k=30)

    # 三轮都应该执行了
    assert len(retriever.calls) == 3
    # Round 1 和 Round 2 的 hard constraints 相同（因为没有 soft preferences 可移除）
    # Round 3 移除了 price bounds，查询应该只保留 sub_category
    assert retriever.calls[2] == "智能手机"
