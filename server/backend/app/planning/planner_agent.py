"""Standalone helper functions used by QueryBuilder and StateReducer.

The PlannerAgent class was removed in v2.0 cleanup. Tool planning is now
handled by ToolPlanner (tool_planner.py) which outputs UnifiedPlan directly.
"""
from __future__ import annotations

from ..models import HardConstraints

CATEGORY_ALIASES = {
    "美妆礼物": "美妆护肤", "化妆品": "美妆护肤", "化妆的": "美妆护肤",
    "化妆": "美妆护肤", "彩妆类": "美妆护肤", "彩妆": "美妆护肤",
    "防晒霜": "防晒", "防晒": "防晒", "洗面奶": "洁面", "洁面": "洁面",
    "精华液": "精华", "精华": "精华", "护肤品": "美妆护肤",
    "手机": "智能手机", "智能手机": "智能手机",
    "笔记本电脑": "笔记本电脑", "笔记本": "笔记本电脑",
    "轻薄本": "笔记本电脑", "电脑本": "笔记本电脑", "电脑": "笔记本电脑",
    "耳机": "真无线耳机", "跑鞋": "跑步鞋", "跑步鞋": "跑步鞋",
    "咖啡": "咖啡", "coffee": "咖啡", "cafe": "咖啡",
    "功能饮料": "功能饮料", "能量饮料": "功能饮料",
    "特饮": "功能饮料", "东鹏特饮": "功能饮料",
}


def _detect_category(text: str) -> str | None:
    for alias, category in CATEGORY_ALIASES.items():
        if alias in text:
            return category
    return None


def _parent_category(sub_category: str | None) -> str | None:
    if sub_category is None:
        return None
    mapping = {
        "智能手机": "数码电子", "笔记本电脑": "数码电子", "真无线耳机": "数码电子",
        "防晒": "美妆护肤", "洁面": "美妆护肤", "精华": "美妆护肤",
        "跑步鞋": "服饰运动", "咖啡": "食品饮料", "功能饮料": "食品饮料",
    }
    return mapping.get(sub_category)


def _clarification_policy(
    user_message: str,
    category_or_subcategory: str | None,
    hard: HardConstraints,
    soft: dict[str, str],
    intent: str,
) -> tuple[bool, str | None]:
    """Returns (need_clarification, question)."""
    if intent == "product_followup":
        return False, None
    text = user_message or ""
    if category_or_subcategory is None and not hard.include_brands:
        if "推荐" in text and ("手机" in text or "精华" in text or "防晒" in text):
            return False, None
        if not any(w in text for w in ["推荐", "帮我找", "找一款", "买", "有没有"]):
            return True, "请问你想看什么品类的商品？比如手机、精华液、运动鞋等。"
    if hard.price_min is not None and hard.price_max is not None and hard.price_max < hard.price_min:
        return True, "检测到预算范围似乎颠倒了，请确认一下价格区间？"
    return False, None
