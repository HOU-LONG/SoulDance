from backend.app.keywords import (
    CHEAPER_ALTERNATIVE_MARKERS,
    DIFFERENT_BRAND_MARKERS,
    EXPLAIN_FOCUS_MARKERS,
    MORE_EXPENSIVE_ALTERNATIVE_MARKERS,
    PRODUCT_REQUEST_MARKERS,
)
from backend.app.messages import insufficient_comparison_products_text, unknown_category_text


def test_product_and_followup_keyword_markers_keep_existing_literals():
    assert PRODUCT_REQUEST_MARKERS == ("推荐", "找", "买", "想要", "想买", "我要", "要一", "要个", "来一", "有没有")
    assert EXPLAIN_FOCUS_MARKERS == ("刚刚那个是什么", "刚才那个是什么", "为什么推荐", "介绍一下", "这个是什么")
    assert CHEAPER_ALTERNATIVE_MARKERS == ("更便宜", "便宜点", "便宜的", "价格低")
    assert MORE_EXPENSIVE_ALTERNATIVE_MARKERS == ("更贵", "贵一点", "高端", "高价位", "价位高")
    assert DIFFERENT_BRAND_MARKERS == ("不要这个品牌", "换个品牌", "别的品牌", "不要这个牌子")


def test_stable_user_messages_keep_existing_text():
    assert unknown_category_text() == "当前商品库里还没有能稳定匹配这个需求的类目。为了不跨类目乱推荐，我先不返回商品卡。你可以换成现有商品类目再试。"
    assert insufficient_comparison_products_text() == "我还没有足够的最近推荐商品可以对比。你可以先让我推荐几款，再说第一款和第二款怎么选。"
