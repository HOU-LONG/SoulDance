from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Product, ProductReference, SessionContext


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
