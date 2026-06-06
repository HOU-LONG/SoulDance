from __future__ import annotations

from .constraint_filter import hard_filter
from .knowledge_base import build_evidence_bundle
from .models import Product, RankedProduct, RetrievalPlan


def rank_products(
    products: list[Product],
    plan: RetrievalPlan,
    retrieval_scores: dict[str, float] | None = None,
    limit: int = 3,
) -> list[RankedProduct]:
    retrieval_scores = retrieval_scores or {}
    filtered = [product for product in products if hard_filter(product, plan.hard_constraints)]
    ranked: list[RankedProduct] = []
    query_terms = list(plan.soft_preferences.values()) + [
        value
        for value in [
            plan.hard_constraints.category,
            plan.hard_constraints.sub_category,
            *plan.hard_constraints.include_brands,
            *plan.hard_constraints.exclude_terms,
        ]
        if value
    ]
    for product in filtered:
        bundle = build_evidence_bundle(product, query_terms)
        tier, score, reason = _score_product(product, plan, retrieval_scores.get(product.product_id, 0.0))
        score += min(bundle.evidence_score, 2.0)
        evidence_chunks = sorted([*bundle.support_chunks, *bundle.risk_chunks], key=lambda chunk: chunk.query_overlap + chunk.field_consistency - chunk.noise_score, reverse=True)
        ranked.append(
            RankedProduct(
                product=product,
                score=score,
                tier=tier,
                reason=reason,
                evidence=[chunk.text[:120] for chunk in evidence_chunks[:3] if chunk.text],
            )
        )
    ranked.sort(key=lambda item: (item.tier == 1, item.tier == 2, item.score), reverse=True)
    return ranked[:limit]


def _score_product(product: Product, plan: RetrievalPlan, retrieval_score: float) -> tuple[int, float, str]:
    score = retrieval_score * 5
    hits: list[str] = []
    constraints = plan.hard_constraints
    if constraints.sub_category and product.sub_category == constraints.sub_category:
        score += 5
        hits.append(f"类目精确匹配{product.sub_category}")
    elif constraints.category and product.category == constraints.category:
        score += 3
        hits.append(f"大类匹配{product.category}")
    if constraints.include_brands:
        score += 4
        hits.append("品牌匹配" + "、".join(constraints.include_brands))
    for pref in plan.soft_preferences.values():
        if pref and pref in product.search_text:
            score += 2
            hits.append(f"匹配{pref}")
    if constraints.price_min is not None:
        score += min(product.price / max(constraints.price_min, 1), 1.5)
        hits.append(f"价格满足下限")
    if constraints.price_max is not None:
        score += max(0, (constraints.price_max - product.price) / max(constraints.price_max, 1))
        hits.append(f"价格在预算内")
    if product.review_rating:
        score += product.review_rating / 5
    tier = 1 if len(hits) >= 2 else 2 if hits else 3
    reason = "，".join(hits[:3]) or "在商品知识库中与需求语义相关"
    return tier, score, reason
