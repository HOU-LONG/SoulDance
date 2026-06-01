from __future__ import annotations

from dataclasses import dataclass

from .models import Product


@dataclass(frozen=True)
class EvidenceChunk:
    text: str
    source_type: str
    rating: int | None = None
    query_overlap: float = 0.0
    field_consistency: float = 1.0
    noise_score: float = 0.0


def product_evidence(product: Product, query_terms: list[str] | None = None, limit: int = 3) -> list[str]:
    chunks = evidence_chunks(product, query_terms)
    return [_trim(chunk.text, query_terms or []) for chunk in chunks[:limit] if chunk.text]


def evidence_chunks(product: Product, query_terms: list[str] | None = None) -> list[EvidenceChunk]:
    query_terms = query_terms or []
    chunks: list[EvidenceChunk] = []
    if product.marketing_description:
        chunks.append(_chunk(product, product.marketing_description, "marketing", query_terms))
    for faq in product.faqs:
        answer = faq.get("answer", "")
        if answer:
            chunks.append(_chunk(product, answer, "faq", query_terms))
    review_chunks = []
    for review in product.reviews:
        text = str(review.get("content", ""))
        if not text:
            continue
        rating = int(review.get("rating", 0) or 0)
        chunk = _chunk(product, text, "review", query_terms, rating)
        if chunk.noise_score >= 0.6 and chunk.query_overlap < 0.5:
            continue
        review_chunks.append(chunk)
    chunks.extend(_select_review_chunks(review_chunks, query_terms))
    return sorted(chunks, key=_chunk_sort_key, reverse=True)


def _select_review_chunks(chunks: list[EvidenceChunk], query_terms: list[str]) -> list[EvidenceChunk]:
    query_text = " ".join(query_terms)
    risk_reviews = [
        chunk
        for chunk in chunks
        if chunk.rating is not None
        and chunk.rating <= 2
        and _mentions_sensitive_risk(chunk.text)
        and any(term in query_text for term in ["敏感肌", "敏感", "屏障"])
    ]
    positive_reviews = [chunk for chunk in chunks if chunk.rating is not None and chunk.rating >= 4 and chunk.noise_score < 0.6]
    selected = risk_reviews[:1]
    if positive_reviews:
        selected.append(max(positive_reviews, key=lambda chunk: (chunk.query_overlap, chunk.field_consistency, chunk.rating or 0)))
    return selected


def _chunk(
    product: Product,
    text: str,
    source_type: str,
    query_terms: list[str],
    rating: int | None = None,
) -> EvidenceChunk:
    query_overlap = _query_overlap(text, query_terms)
    field_consistency = _field_consistency(product, text)
    noise_score = _noise_score(product, text, query_overlap, field_consistency)
    return EvidenceChunk(
        text=text,
        source_type=source_type,
        rating=rating,
        query_overlap=query_overlap,
        field_consistency=field_consistency,
        noise_score=noise_score,
    )


def _chunk_sort_key(chunk: EvidenceChunk) -> tuple[float, float, float, float]:
    source_priority = {"marketing": 0.8, "faq": 0.7, "review": 0.5}.get(chunk.source_type, 0.0)
    risk_bonus = 0.4 if chunk.rating is not None and chunk.rating <= 2 and _mentions_sensitive_risk(chunk.text) else 0.0
    return (
        chunk.query_overlap + source_priority + risk_bonus - chunk.noise_score,
        chunk.field_consistency,
        float(chunk.rating or 0),
        -chunk.noise_score,
    )


def _query_overlap(text: str, query_terms: list[str]) -> float:
    terms = [term for term in query_terms if term]
    if not terms:
        return 0.0
    matched = sum(1 for term in terms if term in text)
    return matched / max(len(terms), 1)


def _field_consistency(product: Product, text: str) -> float:
    fields = [product.title, product.brand, product.category, product.sub_category, *product.extracted_terms]
    if any(field and field in text for field in fields):
        return 1.0
    if _has_food_terms(text) and _product_is_food_like(product):
        return 0.8
    if _has_beauty_terms(text) and product.category == "美妆护肤":
        return 0.8
    if _has_wear_terms(text) and product.category == "服饰运动":
        return 0.8
    return 0.3


def _noise_score(product: Product, text: str, query_overlap: float, field_consistency: float) -> float:
    score = 0.0
    if _cross_category_action_risk(product, text):
        score += 0.4
    if field_consistency < 0.5:
        score += 0.3
    if query_overlap == 0:
        score += 0.2
    if _constraint_conflict_text(text):
        score += 0.1
    return min(score, 1.0)


def _cross_category_action_risk(product: Product, text: str) -> bool:
    if _has_food_terms(text) and not _product_is_food_like(product):
        return True
    if _has_beauty_terms(text) and product.category == "食品饮料":
        return True
    return False


def _product_is_food_like(product: Product) -> bool:
    haystack = f"{product.title} {product.category} {product.sub_category}"
    if any(term in haystack for term in ["毛巾", "鞋", "护肤", "美妆", "电脑", "手机", "平板", "背包", "衣服"]):
        return False
    return product.category == "食品饮料"


def _has_food_terms(text: str) -> bool:
    return any(term in text for term in ["吃", "好吃", "入口", "味道", "香甜", "喝", "口感"])


def _has_beauty_terms(text: str) -> bool:
    return any(term in text for term in ["上脸", "不卡粉", "不闷痘", "肤感", "补水", "泛红", "刺痛"])


def _has_wear_terms(text: str) -> bool:
    return any(term in text for term in ["穿", "尺码", "脚感", "鞋底", "透气"])


def _mentions_sensitive_risk(text: str) -> bool:
    return any(term in text for term in ["敏感肌", "泛红", "刺痛", "过敏", "不适", "起疹"])


def _constraint_conflict_text(text: str) -> bool:
    return any(term in text for term in ["含酒精", "乙醇"]) and not any(marker in text for marker in ["不含酒精", "无酒精", "没有酒精"])


def _trim(text: str, query_terms: list[str], size: int = 120) -> str:
    text = " ".join(text.split())
    for term in query_terms:
        pos = text.find(term)
        if pos >= 0:
            start = max(pos - 40, 0)
            return text[start : start + size]
    return text[:size]
