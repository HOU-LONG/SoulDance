from __future__ import annotations

from .response_contract import no_result_contract_text


def unknown_category_text() -> str:
    return no_result_contract_text(
        understanding="我先确认当前商品库是否有稳定匹配的类目。",
        conclusion="当前商品库里还没有能稳定匹配这个需求的类目。",
        next_step="你可以换成现有商品类目再试。",
    )


def insufficient_comparison_products_text() -> str:
    return no_result_contract_text(
        understanding="你想比较最近推荐过的商品。",
        conclusion="我还没有足够的最近推荐商品可以对比。",
        next_step="你可以先让我推荐几款，再说第一款和第二款怎么选。",
    )
