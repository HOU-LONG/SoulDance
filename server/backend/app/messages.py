from __future__ import annotations


def unknown_category_text() -> str:
    return "当前商品库里还没有能稳定匹配这个需求的类目。为了不跨类目乱推荐，我先不返回商品卡。你可以换成现有商品类目再试。"


def insufficient_comparison_products_text() -> str:
    return "我还没有足够的最近推荐商品可以对比。你可以先让我推荐几款，再说第一款和第二款怎么选。"
