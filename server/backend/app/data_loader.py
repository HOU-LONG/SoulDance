from __future__ import annotations

import json
import re
from pathlib import Path

from .models import Product, SKU


REGION_KEYWORDS = {
    "日本": ["SK-II", "资生堂", "安热沙", "优衣库", "无印良品", "索尼", "任天堂"],
    "美国": ["Apple", "苹果", "Nike", "耐克", "可口可乐", "星巴克", "戴尔"],
    "中国": ["华为", "小米", "荣耀", "李宁", "安踏", "三顿半", "农夫山泉", "完美日记", "珀莱雅", "百雀羚"],
    "韩国": ["兰芝", "雪花秀", "三星"],
    "法国": ["兰蔻", "欧莱雅"],
}

INTEREST_TERMS = [
    "酒精",
    "乙醇",
    "敏感肌",
    "油皮",
    "混油皮",
    "干皮",
    "清爽",
    "防晒",
    "洁面",
    "洗面奶",
    "跑步",
    "通勤",
    "海边",
    "三亚",
    "防水",
    "保湿",
    "修护",
    "低糖",
    "无糖",
    "速干",
    "轻便",
]


def load_products(dataset_dir: str | Path) -> list[Product]:
    root = Path(dataset_dir)
    products: list[Product] = []
    for path in sorted(root.glob("*/data/*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        knowledge = raw.get("rag_knowledge", {})
        faqs = knowledge.get("official_faq", []) or []
        reviews = knowledge.get("user_reviews", []) or []
        skus = [SKU(**sku) for sku in raw.get("skus", [])]
        text_parts = [
            raw.get("title", ""),
            raw.get("brand", ""),
            raw.get("category", ""),
            raw.get("sub_category", ""),
            knowledge.get("marketing_description", ""),
        ]
        for faq in faqs:
            text_parts.append(faq.get("question", ""))
            text_parts.append(faq.get("answer", ""))
        for review in reviews[:5]:
            text_parts.append(str(review.get("content", "")))
        for sku in skus:
            text_parts.extend(sku.properties.values())
        chunk = "\n".join(part for part in text_parts if part)
        product = Product(
            product_id=raw["product_id"],
            title=raw.get("title", ""),
            brand=raw.get("brand", ""),
            category=raw.get("category", ""),
            sub_category=raw.get("sub_category", ""),
            price=float(raw.get("base_price", 0.0)),
            image_path=raw.get("image_path", ""),
            skus=skus,
            marketing_description=knowledge.get("marketing_description", ""),
            faqs=faqs,
            reviews=reviews,
            chunk=chunk,
            search_text=_normalize_text(chunk),
            brand_region=_infer_brand_region(raw.get("brand", ""), raw.get("title", "")),
            extracted_terms=_extract_terms(chunk),
            review_rating=_avg_rating(reviews),
        )
        products.append(product)
    return products


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def _infer_brand_region(brand: str, title: str) -> str:
    haystack = f"{brand} {title}"
    for region, keywords in REGION_KEYWORDS.items():
        if any(keyword.lower() in haystack.lower() for keyword in keywords):
            return region
    return "未知"


def _extract_terms(text: str) -> list[str]:
    normalized = _normalize_text(text)
    terms: list[str] = []
    for term in INTEREST_TERMS:
        if term.lower() not in normalized:
            continue
        if term in {"酒精", "乙醇"} and not _contains_positive_term(normalized, term):
            continue
        terms.append(term)
    return terms


def _contains_positive_term(text: str, term: str) -> bool:
    term = term.lower()
    start = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            return False
        prefix = text[max(0, index - 4) : index]
        if any(marker in prefix for marker in ["不含", "无", "没有", "不添加", "未添加"]):
            start = index + len(term)
            continue
        return True


def _avg_rating(reviews: list[dict[str, object]]) -> float:
    ratings = [float(review.get("rating", 0) or 0) for review in reviews]
    ratings = [rating for rating in ratings if rating > 0]
    if not ratings:
        return 0.0
    return sum(ratings) / len(ratings)
