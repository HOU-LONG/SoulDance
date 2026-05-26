from __future__ import annotations

from .models import Product


def product_evidence(product: Product, query_terms: list[str] | None = None, limit: int = 3) -> list[str]:
    evidence: list[str] = []
    query_terms = query_terms or []
    if product.marketing_description:
        evidence.append(_trim(product.marketing_description, query_terms))
    for faq in product.faqs:
        answer = faq.get("answer", "")
        if answer:
            evidence.append(_trim(answer, query_terms))
            break
    positive_reviews = [r for r in product.reviews if int(r.get("rating", 0) or 0) >= 4]
    if positive_reviews:
        evidence.append(_trim(str(positive_reviews[0].get("content", "")), query_terms))
    return [item for item in evidence if item][:limit]


def _trim(text: str, query_terms: list[str], size: int = 120) -> str:
    text = " ".join(text.split())
    for term in query_terms:
        pos = text.find(term)
        if pos >= 0:
            start = max(pos - 40, 0)
            return text[start : start + size]
    return text[:size]
