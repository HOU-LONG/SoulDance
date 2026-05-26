from __future__ import annotations

from .models import HardConstraints, Product


TERM_SYNONYMS = {
    "酒精": ["酒精", "乙醇", "alcohol"],
    "乙醇": ["酒精", "乙醇", "alcohol"],
    "日系": ["日本"],
    "日本": ["日本"],
}


def hard_filter(product: Product, constraints: HardConstraints) -> bool:
    if constraints.category and constraints.category not in {product.category, product.sub_category}:
        return False
    if constraints.sub_category and constraints.sub_category != product.sub_category:
        return False
    if constraints.price_max is not None and product.price > constraints.price_max:
        return False
    if constraints.exclude_brand_regions and product.brand_region in constraints.exclude_brand_regions:
        return False
    for brand in constraints.exclude_brands:
        if brand and brand.lower() in product.brand.lower():
            return False
    haystack = product.search_text
    for term in constraints.exclude_terms:
        for synonym in TERM_SYNONYMS.get(term, [term]):
            if _contains_forbidden_term(haystack, synonym):
                return False
    return True


def explain_filter(product: Product, constraints: HardConstraints) -> str | None:
    if constraints.price_max is not None and product.price > constraints.price_max:
        return f"价格 {product.price:.0f} 元超过预算 {constraints.price_max:.0f} 元"
    if constraints.exclude_brand_regions and product.brand_region in constraints.exclude_brand_regions:
        return f"品牌地区为{product.brand_region}，不符合排除条件"
    for term in constraints.exclude_terms:
        for synonym in TERM_SYNONYMS.get(term, [term]):
            if _contains_forbidden_term(product.search_text, synonym):
                return f"商品信息中包含被排除的「{term}」相关内容"
    return None


def _contains_forbidden_term(text: str, term: str) -> bool:
    lowered = text.lower()
    term = term.lower()
    start = 0
    while True:
        index = lowered.find(term, start)
        if index < 0:
            return False
        prefix = lowered[max(0, index - 4) : index]
        if any(marker in prefix for marker in ["不含", "无", "没有", "不添加", "未添加"]):
            start = index + len(term)
            continue
        return True
