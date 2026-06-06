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


@dataclass(frozen=True)
class EvidenceBundle:
    support_chunks: list[EvidenceChunk]
    risk_chunks: list[EvidenceChunk]
    ignored_chunks: list[EvidenceChunk]
    positive_summary: str
    negative_summary: str
    evidence_score: float


def product_evidence(product: Product, query_terms: list[str] | None = None, limit: int = 3) -> list[str]:
    bundle = build_evidence_bundle(product, query_terms)
    chunks = [*bundle.support_chunks, *bundle.risk_chunks]
    chunks = sorted(chunks, key=_chunk_sort_key, reverse=True)
    return [_trim(chunk.text, query_terms or []) for chunk in chunks[:limit] if chunk.text]


def evidence_chunks(product: Product, query_terms: list[str] | None = None) -> list[EvidenceChunk]:
    bundle = build_evidence_bundle(product, query_terms)
    return sorted([*bundle.support_chunks, *bundle.risk_chunks], key=_chunk_sort_key, reverse=True)


def build_evidence_bundle(product: Product, query_terms: list[str] | None = None) -> EvidenceBundle:
    query_terms = query_terms or []
    support_chunks: list[EvidenceChunk] = []
    risk_chunks: list[EvidenceChunk] = []
    ignored_chunks: list[EvidenceChunk] = []
    for chunk in _raw_evidence_chunks(product, query_terms):
        if _is_risk_chunk(chunk, query_terms):
            risk_chunks.append(chunk)
        elif _is_support_chunk(chunk):
            support_chunks.append(chunk)
        else:
            ignored_chunks.append(chunk)
    support_chunks = sorted(support_chunks, key=_chunk_sort_key, reverse=True)
    risk_chunks = sorted(risk_chunks, key=_chunk_sort_key, reverse=True)
    ignored_chunks = sorted(ignored_chunks, key=_chunk_sort_key, reverse=True)
    positive_reviews = [
        chunk
        for chunk in support_chunks
        if chunk.source_type == "review" and (chunk.rating is None or chunk.rating >= 4)
    ]
    negative_reviews = [chunk for chunk in risk_chunks if chunk.source_type == "review"]
    return EvidenceBundle(
        support_chunks=support_chunks,
        risk_chunks=risk_chunks,
        ignored_chunks=ignored_chunks,
        positive_summary=_summarize_review_chunks(positive_reviews, "相关评论提到"),
        negative_summary=_summarize_review_chunks(negative_reviews, "需要注意"),
        evidence_score=_evidence_score(support_chunks, risk_chunks),
    )


def _raw_evidence_chunks(product: Product, query_terms: list[str]) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    if product.marketing_description:
        chunks.append(_chunk(product, product.marketing_description, "marketing", query_terms))
    for faq in product.faqs:
        answer = faq.get("answer", "")
        if answer:
            chunks.append(_chunk(product, answer, "faq", query_terms))
    for review in product.reviews:
        text = str(review.get("content", ""))
        if not text:
            continue
        rating = int(review.get("rating", 0) or 0)
        chunks.append(_chunk(product, text, "review", query_terms, rating))
    return chunks


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
    if _has_digital_terms(text) and product.category == "数码电子":
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


def _has_digital_terms(text: str) -> bool:
    return any(
        term in text
        for term in [
            "拍",
            "夜景",
            "夜拍",
            "抓拍",
            "成片",
            "影像",
            "镜头",
            "续航",
            "充电",
            "屏幕",
            "刷新率",
            "内存",
            "后台",
            "手游",
            "高刷",
            "发热",
            "信号",
        ]
    )


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



def evidence_review_summary(product: Product, query_terms: list[str] | None = None) -> dict[str, str]:
    bundle = build_evidence_bundle(product, query_terms)
    has_reviews = any(chunk.source_type == "review" for chunk in [*bundle.support_chunks, *bundle.risk_chunks])
    return {
        "positive_summary": bundle.positive_summary,
        "negative_summary": bundle.negative_summary,
        "review_relevance": "high" if has_reviews else "none",
    }


def _is_support_chunk(chunk: EvidenceChunk) -> bool:
    if chunk.noise_score >= 0.6:
        return False
    if chunk.query_overlap > 0:
        return True
    if chunk.field_consistency >= 0.8 and not _is_generic_service_review(chunk):
        return True
    return False


def _is_risk_chunk(chunk: EvidenceChunk, query_terms: list[str]) -> bool:
    query_text = " ".join(query_terms)
    return (
        chunk.source_type == "review"
        and chunk.rating is not None
        and chunk.rating <= 2
        and _mentions_sensitive_risk(chunk.text)
        and any(term in query_text for term in ["敏感肌", "敏感", "屏障"])
        and chunk.noise_score < 0.6
    )


def _is_generic_service_review(chunk: EvidenceChunk) -> bool:
    if chunk.source_type != "review":
        return False
    return any(term in chunk.text for term in ["物流", "快递", "包装", "客服", "发货"]) and chunk.query_overlap == 0


def _evidence_score(support_chunks: list[EvidenceChunk], risk_chunks: list[EvidenceChunk]) -> float:
    score = 0.0
    for chunk in support_chunks[:3]:
        source_weight = {"marketing": 0.35, "faq": 0.45, "review": 0.75}.get(chunk.source_type, 0.3)
        score += source_weight + chunk.query_overlap + max(chunk.field_consistency - 0.5, 0) - chunk.noise_score
    for chunk in risk_chunks[:1]:
        score += 0.15 + chunk.query_overlap
    return max(score, 0.0)


def _summarize_review_chunks(chunks: list[EvidenceChunk], prefix: str) -> str:
    if not chunks:
        return "暂无足够相关评论"
    snippets = [_short_review_phrase(chunk.text) for chunk in chunks[:2] if chunk.text]
    snippets = [snippet for snippet in snippets if snippet]
    if not snippets:
        return "暂无足够相关评论"
    return prefix + "：" + "；".join(snippets)


def _short_review_phrase(text: str) -> str:
    text = " ".join(str(text).split())
    for separator in ["。", "；", ";", "，", ","]:
        if separator in text:
            text = text.split(separator)[0]
            break
    return _trim(text, [])[:48]
