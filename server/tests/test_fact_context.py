# server/tests/test_fact_context.py
from __future__ import annotations
from server.backend.app.models import Product, RankedProduct, FactContext
from server.backend.app.fact_context import FactContextBuilder


def _mk_product(pid: str, title: str, brand: str, price: float,
                cat: str = "手机", sub: str = "智能机", desc: str = "") -> Product:
    return Product(
        product_id=pid, title=title, brand=brand, price=price,
        category=cat, sub_category=sub, image_path="",
        marketing_description=desc or f"{title} 优质产品",
        search_text=title,
    )


def _mk_ranked(p: Product, score: float = 0.9) -> RankedProduct:
    return RankedProduct(product=p, score=score, tier=1, reason="匹配")


def test_build_empty():
    ctx = FactContextBuilder().build([])
    assert ctx.prompt_block == ""
    assert ctx.product_index == {}
    assert ctx.brand_index == {}
    assert ctx.denied_queries == []


def test_build_with_products():
    p1 = _mk_product("P1", "小米 14 Ultra", "小米", 5999.0)
    p2 = _mk_product("P2", "华为 Mate 70 Pro", "华为", 6999.0)
    ranked = [_mk_ranked(p1), _mk_ranked(p2)]
    ctx = FactContextBuilder().build(ranked, denied_queries=["小米 17 Max"])

    assert "P1" in ctx.product_index
    assert ctx.product_index["P1"].brand == "小米"
    assert ctx.product_index["P1"].price == 5999.0
    assert "P1" in ctx.brand_index["小米"]
    assert "P2" in ctx.brand_index["华为"]

    # prompt_block 格式
    assert "[[P1]]" in ctx.prompt_block
    assert "[[P2]]" in ctx.prompt_block
    assert "小米 14 Ultra" in ctx.prompt_block
    assert "¥5999" in ctx.prompt_block

    # denied_queries 透传
    assert "小米 17 Max" in ctx.denied_queries


def test_prompt_block_contains_rules():
    p = _mk_product("P1", "测试", "牌子", 100.0)
    ctx = FactContextBuilder().build([_mk_ranked(p)])
    assert "你唯一可以引用的商品信息" in ctx.prompt_block
    assert "[[product_id]]" in ctx.prompt_block
    assert "不要编造任何商品名称" in ctx.prompt_block


def test_key_specs_extraction():
    p = _mk_product("P1", "商品", "品牌", 100.0,
                    desc="徕卡镜头, 骁龙8Gen3, 1英寸大底")
    ctx = FactContextBuilder().build([_mk_ranked(p)])
    assert "徕卡镜头" in ctx.prompt_block
    assert "骁龙8Gen3" in ctx.prompt_block


def test_denied_queries_default():
    ctx = FactContextBuilder().build([])
    assert ctx.denied_queries == []
