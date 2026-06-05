from __future__ import annotations

from .image_assets import product_image_url
from .models import Product


class CartService:
    def __init__(self, products: list[Product]):
        self.products = {product.product_id: product for product in products}
        self._carts: dict[str, dict[str, int]] = {}

    def add(self, session_id: str, product_id: str, quantity: int = 1) -> dict:
        if product_id not in self.products:
            raise KeyError(f"unknown product_id: {product_id}")
        cart = self._carts.setdefault(session_id, {})
        cart[product_id] = cart.get(product_id, 0) + max(quantity, 1)
        return self.get(session_id)

    def update_quantity(self, session_id: str, product_id: str, quantity: int) -> dict:
        if product_id not in self.products:
            raise KeyError(f"unknown product_id: {product_id}")
        cart = self._carts.setdefault(session_id, {})
        if quantity <= 0:
            cart.pop(product_id, None)
        else:
            cart[product_id] = quantity
        return self.get(session_id)

    def remove(self, session_id: str, product_id: str) -> dict:
        self._carts.setdefault(session_id, {}).pop(product_id, None)
        return self.get(session_id)

    def clear(self, session_id: str) -> dict:
        self._carts[session_id] = {}
        return self.get(session_id)

    def get(self, session_id: str) -> dict:
        cart = self._carts.setdefault(session_id, {})
        items = []
        total = 0.0
        for product_id, quantity in cart.items():
            product = self.products[product_id]
            amount = product.price * quantity
            total += amount
            items.append(
                {
                    "product_id": product.product_id,
                    "name": product.title,
                    "brand": product.brand,
                    "price": product.price,
                    "quantity": quantity,
                    "amount": amount,
                    "main_image_url": product_image_url(product.image_path),
                }
            )
        return {"session_id": session_id, "items": items, "total_amount": total}

    def checkout(self, session_id: str) -> dict:
        snapshot = self.get(session_id)
        self.clear(session_id)
        return {
            "status": "ok",
            "session_id": session_id,
            "order_id": f"demo_order_{session_id}",
            "paid_amount": snapshot["total_amount"],
            "items": snapshot["items"],
        }
