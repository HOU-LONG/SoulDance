from __future__ import annotations

from .constraint_filter import explain_filter
from .models import Product, RetrievalPlan


def comparison_item(product: Product, text: str, dimensions: list[str], plan: RetrievalPlan | None = None) -> dict:
    points = []
    if "油皮" in text and "油皮" in product.search_text:
        points.append("明确提到适合油皮")
    if "清爽" in product.search_text:
        points.append("质地或反馈偏清爽")
    if product.review_rating:
        points.append(f"评价均分 {product.review_rating:.1f}")
    if not points:
        points.append("与当前需求语义相关")
    return {
        "product_id": product.product_id,
        "name": product.title,
        "brand": product.brand,
        "price": product.price,
        "key_points": points[:3],
        "dimension_values": comparison_dimension_values(product, text, dimensions),
        "risk_flags": comparison_risk_flags(product, plan),
    }


def comparison_dimension_values(product: Product, text: str, dimensions: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for dimension in dimensions:
        if dimension == "价格":
            values[dimension] = f"{product.price:.0f} 元"
        elif dimension == "品牌":
            values[dimension] = product.brand
        elif dimension == "类目":
            values[dimension] = product.sub_category or product.category
        elif dimension == "用户关心点":
            values[dimension] = comparison_need_value(product, text)
        elif dimension == "适合油皮":
            values[dimension] = "明确覆盖" if "油皮" in product.search_text else "未明确提及"
        elif dimension == "清爽度":
            values[dimension] = "偏清爽" if "清爽" in product.search_text else "未明确提及"
        elif dimension == "口碑":
            values[dimension] = f"{product.review_rating:.1f}" if product.review_rating else "暂无评分"
        else:
            values[dimension] = "可参考商品详情"
    return values


def comparison_need_value(product: Product, text: str) -> str:
    if "油皮" in text:
        return "匹配油皮需求" if "油皮" in product.search_text else "油皮信息不足"
    if "便宜" in text or "价格" in text:
        return "价格更低优先"
    if "清爽" in text:
        return "清爽相关" if "清爽" in product.search_text else "清爽信息不足"
    return "与当前对比需求相关"


def comparison_risk_flags(product: Product, plan: RetrievalPlan | None) -> list[str]:
    if not plan:
        return []
    reason = explain_filter(product, plan.hard_constraints)
    return [reason] if reason else []


def comparison_reason(product: Product, text: str) -> str:
    if "油皮" in text and "油皮" in product.search_text:
        return "它的商品信息里更明确覆盖油皮需求"
    if "清爽" in product.search_text:
        return "它更贴近日常清爽使用场景"
    if product.review_rating:
        return "它的评价表现更稳"
    return "它和当前需求的商品信息更贴近"
