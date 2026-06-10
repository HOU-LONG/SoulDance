from backend.app.comparison_presenter import (
    comparison_dimension_values,
    comparison_item,
    comparison_reason,
    comparison_risk_flags,
)
from backend.app.models import HardConstraints, Product, RetrievalPlan


def _product(
    *,
    product_id: str = "p1",
    title: str = "清爽油皮精华",
    brand: str = "测试品牌",
    category: str = "美妆护肤",
    sub_category: str = "精华",
    price: float = 199,
    search_text: str = "清爽 油皮 精华 评价稳定",
    review_rating: float = 4.7,
) -> Product:
    return Product(
        product_id=product_id,
        title=title,
        brand=brand,
        category=category,
        sub_category=sub_category,
        price=price,
        image_path="",
        search_text=search_text,
        review_rating=review_rating,
    )


def test_comparison_dimension_values_formats_supported_dimensions():
    product = _product()

    values = comparison_dimension_values(
        product,
        "油皮想要清爽一点，价格也要合适",
        ["价格", "品牌", "类目", "用户关心点", "适合油皮", "清爽度", "口碑", "其他"],
    )

    assert values == {
        "价格": "199 元",
        "品牌": "测试品牌",
        "类目": "精华",
        "用户关心点": "匹配油皮需求",
        "适合油皮": "明确覆盖",
        "清爽度": "偏清爽",
        "口碑": "4.7",
        "其他": "可参考商品详情",
    }


def test_comparison_item_builds_frontend_payload_fields():
    product = _product()

    item = comparison_item(product, "油皮要清爽", ["价格", "用户关心点"], plan=None)

    assert item["product_id"] == "p1"
    assert item["name"] == "清爽油皮精华"
    assert item["brand"] == "测试品牌"
    assert item["price"] == 199
    assert item["key_points"] == ["明确提到适合油皮", "质地或反馈偏清爽", "评价均分 4.7"]
    assert item["dimension_values"] == {"价格": "199 元", "用户关心点": "匹配油皮需求"}
    assert item["risk_flags"] == []


def test_comparison_risk_flags_are_empty_without_plan():
    assert comparison_risk_flags(_product(), None) == []


def test_comparison_risk_flags_explain_hard_constraint_mismatch():
    product = _product(brand="测试品牌", search_text="清爽 油皮")
    plan = RetrievalPlan(
        retrieval_query="不要测试品牌",
        hard_constraints=HardConstraints(exclude_brands=["测试品牌"]),
    )

    flags = comparison_risk_flags(product, plan)

    assert flags
    assert "测试品牌" in flags[0]


def test_comparison_reason_prefers_oily_skin_then_freshness_then_rating_then_default():
    assert comparison_reason(_product(search_text="油皮 精华", review_rating=0), "油皮怎么选") == "它的商品信息里更明确覆盖油皮需求"
    assert comparison_reason(_product(search_text="清爽 精华", review_rating=0), "日常怎么选") == "它更贴近日常清爽使用场景"
    assert comparison_reason(_product(search_text="精华", review_rating=4.5), "日常怎么选") == "它的评价表现更稳"
    assert comparison_reason(_product(search_text="精华", review_rating=0), "日常怎么选") == "它和当前需求的商品信息更贴近"
