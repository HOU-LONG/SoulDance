from __future__ import annotations

from .models import HardConstraints, Product


TERM_SYNONYMS = {
    "酒精": ["酒精", "乙醇", "alcohol"],
    "乙醇": ["酒精", "乙醇", "alcohol"],
    "日系": ["日本"],
    "日本": ["日本"],
}


BRAND_ALIASES = {
    "华为": ["华为", "huawei"],
    "苹果": ["苹果", "apple"],
    "小米": ["小米", "xiaomi"],
    "荣耀": ["荣耀", "honor"],
    "耐克": ["耐克", "nike"],
    "阿迪达斯": ["阿迪达斯", "adidas"],
    "oppo": ["oppo"],
    "vivo": ["vivo"],
    "雀巢": ["雀巢", "nestle", "nescafe"],
    "三顿半": ["三顿半", "saturnbird"],
    "农夫山泉": ["农夫山泉"],
    "东方树叶": ["东方树叶"],
    "红牛": ["红牛", "red bull"],
}


def hard_filter(product: Product, constraints: HardConstraints) -> bool:
    if constraints.category and constraints.category not in {product.category, product.sub_category}:
        return False
    if constraints.sub_category and constraints.sub_category != product.sub_category:
        return False
    if constraints.price_min is not None and product.price < constraints.price_min:
        return False
    if constraints.price_max is not None and product.price > constraints.price_max:
        return False
    if constraints.include_brands and not any(_brand_matches(product, brand) for brand in constraints.include_brands):
        return False
    if constraints.exclude_brand_regions and product.brand_region in constraints.exclude_brand_regions:
        return False
    for brand in constraints.exclude_brands:
        if _brand_matches(product, brand):
            return False
    haystack = product.search_text
    for term in constraints.exclude_terms:
        for synonym in TERM_SYNONYMS.get(term, [term]):
            if _contains_forbidden_term(haystack, synonym):
                return False
    return True


def explain_filter(product: Product, constraints: HardConstraints) -> str | None:
    if constraints.price_min is not None and product.price < constraints.price_min:
        return f"价格 {product.price:.0f} 元低于最低预算 {constraints.price_min:.0f} 元"
    if constraints.price_max is not None and product.price > constraints.price_max:
        return f"价格 {product.price:.0f} 元超过预算 {constraints.price_max:.0f} 元"
    if constraints.include_brands and not any(_brand_matches(product, brand) for brand in constraints.include_brands):
        return "品牌不在指定品牌「" + "、".join(constraints.include_brands) + "」中"
    if constraints.exclude_brand_regions and product.brand_region in constraints.exclude_brand_regions:
        return f"品牌地区为{product.brand_region}，不符合排除条件"
    for brand in constraints.exclude_brands:
        if _brand_matches(product, brand):
            return f"品牌 {product.brand} 命中排除品牌「{brand}」"
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


def canonical_brand(value: str) -> str:
    lowered = value.strip().lower()
    for canonical, aliases in BRAND_ALIASES.items():
        if lowered == canonical.lower() or lowered in aliases:
            return canonical
    return value.strip()


def extract_included_brands(text: str) -> list[str]:
    if any(marker in text for marker in ["不要", "不考虑", "排除", "避开", "除了", "别", "非"]):
        return []
    lowered = (text or "").lower()
    brands: list[str] = []
    for canonical, aliases in BRAND_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            brands.append(canonical)
    return dedupe(brands)


def extract_excluded_brands(text: str) -> list[str]:
    if not any(marker in text for marker in ["不要", "不考虑", "排除", "避开", "除了", "别", "非"]):
        return []
    brands: list[str] = []
    lowered = text.lower()
    for canonical, aliases in BRAND_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            brands.append(canonical)
    return dedupe(brands)


def _brand_matches(product: Product, excluded_brand: str) -> bool:
    excluded_brand = excluded_brand.strip()
    if not excluded_brand:
        return False
    aliases = BRAND_ALIASES.get(canonical_brand(excluded_brand), [excluded_brand])
    haystack = f"{product.brand} {product.title} {product.search_text}".lower()
    return any(alias.lower() in haystack for alias in aliases)


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
