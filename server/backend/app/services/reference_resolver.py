from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import Product, ProductReference, SessionContext


@dataclass(frozen=True)
class ReferenceResolution:
    product_id: str | None
    reason: str | None = None
    needs_clarification: bool = False


class ReferenceResolver:
    """Only deterministic product-id binding boundary."""

    def __init__(self, product_map: dict[str, Product]):
        self.product_map = product_map

    def resolve(
        self,
        reference: ProductReference,
        context: SessionContext,
        cart_snapshot: dict[str, Any] | None = None,
    ) -> ReferenceResolution:
        cart_snapshot = cart_snapshot or {}
        explicit = self._resolve_explicit_product(reference, context)
        if explicit is not None:
            return explicit
        if reference.reference in {"focus_product", "current_product"}:
            return self._resolve_focus(context)
        if reference.reference in {"last_recommendation", "last_recommendations", "recommendations"}:
            return self._resolve_recommendation(reference, context)
        if reference.reference in {"recent_cart_item", "cart_item", "cart"}:
            return self._resolve_cart_item(reference, context, cart_snapshot)
        return self._fallback(context)

    def _resolve_explicit_product(
        self, reference: ProductReference, context: SessionContext
    ) -> ReferenceResolution | None:
        if not reference.product_id:
            return None
        if reference.product_id not in self.product_map:
            return ReferenceResolution(None, "llm_product_id_not_in_catalog", True)
        known_ids = {
            item.product_id for item in context.state.recommendation_memory.items
        } | set(context.last_product_ids)
        focus_id = context.state.active_focus.product_id or context.focus_product_id
        recent_cart_id = context.state.cart_memory.recent_product_id or context.recent_cart_product_id
        if reference.product_id in known_ids or reference.product_id in {focus_id, recent_cart_id}:
            return ReferenceResolution(reference.product_id, "explicit_known_product_id")
        return ReferenceResolution(None, "explicit_product_id_not_in_session_scope", True)

    def _resolve_focus(self, context: SessionContext) -> ReferenceResolution:
        product_id = context.state.active_focus.product_id or context.focus_product_id
        if product_id in self.product_map:
            return ReferenceResolution(product_id, "active_focus")
        return self._resolve_recommendation(
            ProductReference(reference="last_recommendations", selection_strategy="primary"),
            context,
        )

    def _resolve_recommendation(
        self, reference: ProductReference, context: SessionContext
    ) -> ReferenceResolution:
        product_ids = [item.product_id for item in context.state.recommendation_memory.items]
        if not product_ids:
            product_ids = list(context.last_product_ids)
        products = [self.product_map[product_id] for product_id in product_ids if product_id in self.product_map]
        if not products:
            return ReferenceResolution(None, "no_recommendation_memory", True)
        index = reference.index
        if reference.selection_strategy in {"rank_index", "index"} and index is not None:
            if 0 <= index < len(products):
                return ReferenceResolution(products[index].product_id, "recommendation_index")
            return ReferenceResolution(None, "recommendation_index_out_of_range", True)
        if reference.selection_strategy == "cheapest":
            return ReferenceResolution(min(products, key=lambda product: product.price).product_id, "cheapest")
        if reference.selection_strategy == "most_expensive":
            return ReferenceResolution(max(products, key=lambda product: product.price).product_id, "most_expensive")
        primary = next(
            (
                item.product_id
                for item in context.state.recommendation_memory.items
                if item.role == "primary" and item.product_id in self.product_map
            ),
            None,
        )
        return ReferenceResolution(primary or products[0].product_id, "primary_recommendation")

    def _resolve_cart_item(
        self,
        reference: ProductReference,
        context: SessionContext,
        cart_snapshot: dict[str, Any],
    ) -> ReferenceResolution:
        recent = context.state.cart_memory.recent_product_id or context.recent_cart_product_id
        if recent in self.product_map:
            return ReferenceResolution(recent, "recent_cart_item")
        items = cart_snapshot.get("items", [])
        index = reference.index
        if index is not None and 0 <= index < len(items):
            product_id = items[index].get("product_id")
            if product_id in self.product_map:
                return ReferenceResolution(product_id, "cart_index")
        if items:
            product_id = items[0].get("product_id")
            if product_id in self.product_map:
                return ReferenceResolution(product_id, "first_cart_item")
        return ReferenceResolution(None, "no_cart_item", True)

    def _fallback(self, context: SessionContext) -> ReferenceResolution:
        return self._resolve_focus(context)


def resolve_named_product(message: str, product_map: dict[str, Product], context: SessionContext) -> Product | None:
    """从用户消息中解析提到的产品名称，返回匹配的商品或 None。

    匹配策略：
    - 优先从上下文获取焦点商品（当消息是模糊的"这个/刚才"等）
    - 否则在 product_map 中查找最佳匹配，要求匹配度足够高
    - 避免将虚构产品名（如"小米17max"）错误匹配到相似的真实产品
    """
    if not message:
        return None
    import re
    text = message.lower()
    # 移除常见的分析/询问词汇
    text = re.sub(r"(性价比|怎么样|如何|分析一下|值得买吗|好不好|的|了|呢|吗|你|我|看|觉得|认为|说说|评价|推荐|建议|一下|这款|这个|那个)", "", text)
    text = text.strip()
    if not text:
        # 如果清理后为空，尝试从上下文获取焦点商品
        focus_id = context.state.active_focus.product_id or context.focus_product_id
        if focus_id and focus_id in product_map:
            return product_map[focus_id]
        if context.last_product_ids:
            for pid in reversed(context.last_product_ids):
                if pid in product_map:
                    return product_map[pid]
        return None

    # 在 product_map 中查找最佳匹配
    best_product = None
    best_score = 0
    for product in product_map.values():
        score = 0
        title_lower = product.title.lower()
        brand_lower = (product.brand or "").lower()
        sub_cat_lower = (product.sub_category or "").lower()

        # 品牌匹配（必须完全包含或相等）
        if brand_lower and brand_lower in text:
            score += 30
        if text in brand_lower:
            score += 20

        # 标题完全包含查询文本（强信号）
        if text in title_lower:
            score += 60
        # 标题中的词包含在查询文本中（弱信号，可能误匹配）
        elif title_lower in text:
            score += 40
        else:
            # 逐字匹配，只给少量分数
            for word in text:
                if len(word) >= 2 and word in title_lower:
                    score += 3

        # 子类目匹配
        if sub_cat_lower and sub_cat_lower in text:
            score += 10

        if score > best_score:
            best_score = score
            best_product = product

    # 阈值：要求至少品牌+部分标题匹配，或完整标题包含
    # 对于"小米17max"，如果只有"小米"匹配到品牌，分数是30，不够
    # 对于"小米 17 Ultra"，如果"小米17"在标题中，分数会更高
    if best_score >= 50:
        return best_product
    return None