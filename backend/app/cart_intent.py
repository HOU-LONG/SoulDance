"""购物车意图解析辅助函数。

从 agent.py 抽离的纯函数集合：识别购物车动作、归一化动作来源、解析数量，
以及生成购物车商品展示名与操作提示文案。均不含对话编排逻辑与副作用。
"""
import re

from .cart import CartService


def _detect_cart_action(text: str) -> str:
    if any(word in text for word in ["不要这个品牌", "不要这个牌子"]):
        return "get_cart"
    if any(word in text for word in ["下单", "结算"]):
        return "checkout"
    if any(word in text for word in ["删掉", "删除", "移除"]):
        return "remove"
    if any(word in text for word in ["数量", "改成", "改为"]):
        return "update_quantity"
    if any(word in text for word in ["购物车", "加购", "加入", "加到"]):
        return "add_to_cart"
    return "get_cart"


def _normalize_cart_action(action: str) -> str:
    if action in {"add", "add_to_cart"}:
        return "add_to_cart"
    if action in {"update", "set_quantity", "update_quantity"}:
        return "update_quantity"
    if action in {"delete", "remove"}:
        return "remove"
    if action in {"checkout", "order"}:
        return "checkout"
    return "get_cart"


def _detect_quantity(text: str) -> int | None:
    match = re.search(r"(?:数量)?(?:改成|改为|设为)?\s*(\d+)", text)
    if match:
        return max(int(match.group(1)), 0)
    chinese_digits = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}
    for word, value in chinese_digits.items():
        if f"{word}件" in text or f"{word}个" in text:
            return value
    return None


def _cart_product_display_name(cart: CartService, product_id: str) -> str:
    product = cart.products.get(product_id)
    if not product:
        return product_id
    brand = (product.brand or "").strip()
    sub_category = (product.sub_category or "").strip()
    if brand and brand != "未知" and sub_category and brand not in sub_category:
        return f"{brand}{sub_category}"
    return product.title or product_id


def _cart_message(action: str, product_name: str) -> str:
    if action == "update_quantity":
        return f"已更新 {product_name} 的数量。"
    if action == "remove":
        return f"已从购物车移除 {product_name}。"
    return f"已把 {product_name} 加入购物车。"
