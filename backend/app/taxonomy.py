from __future__ import annotations

import re
from dataclasses import dataclass

from .models import HardConstraints, Product


ROOT_CATEGORIES = {"美妆护肤", "数码电子", "服饰运动", "食品饮料"}

DEFAULT_ALIASES = {
    "防晒霜": "防晒",
    "防晒乳": "防晒",
    "防晒": "防晒",
    "洗面奶": "洁面",
    "洁面乳": "洁面",
    "洁面": "洁面",
    "精华液": "精华",
    "抗老精华": "精华",
    "淡纹精华": "精华",
    "精华": "精华",
    "爽肤水": "化妆水",
    "柔肤水": "化妆水",
    "化妆水": "化妆水",
    "卸妆油": "卸妆",
    "卸妆液": "卸妆",
    "卸妆": "卸妆",
    "底妆": "粉底液",
    "粉底": "粉底液",
    "粉底液": "粉底液",
    "散粉": "蜜粉",
    "粉饼": "蜜粉",
    "蜜粉": "蜜粉",
    "眼霜": "眼霜",
    "眉笔": "眉笔",
    "唇釉": "唇釉",
    "面膜": "面膜",
    "面霜": "面霜",
    "手机": "智能手机",
    "智能手机": "智能手机",
    "折叠屏": "智能手机",
    "平板": "平板电脑",
    "平板电脑": "平板电脑",
    "笔记本电脑": "笔记本电脑",
    "笔记本": "笔记本电脑",
    "轻薄笔记本": "笔记本电脑",
    "轻薄本": "笔记本电脑",
    "电脑本": "笔记本电脑",
    "电脑": "笔记本电脑",
    "耳机": "真无线耳机",
    "蓝牙耳机": "真无线耳机",
    "真无线耳机": "真无线耳机",
    "跑鞋": "跑步鞋",
    "跑步鞋": "跑步鞋",
    "篮球鞋": "篮球鞋",
    "徒步鞋": "徒步鞋",
    "登山鞋": "徒步鞋",
    "短袖": "短袖T恤",
    "短袖t恤": "短袖T恤",
    "t恤": "短袖T恤",
    "速干衣": "速干T恤",
    "速干t恤": "速干T恤",
    "速干T恤": "速干T恤",
    "卫衣": "卫衣",
    "背包": "背包",
    "双肩包": "背包",
    "帽子": "帽子",
    "鸭舌帽": "帽子",
    "运动长裤": "运动长裤",
    "长裤": "运动长裤",
    "运动短裤": "运动短裤",
    "短裤": "运动短裤",
    "户外裤": "户外裤",
    "瑜伽裤": "瑜伽裤",
    "咖啡": "咖啡",
    "茶": "茶饮",
    "茶饮": "茶饮",
    "方便面": "方便食品",
    "泡面": "方便食品",
    "方便食品": "方便食品",
    "坚果": "坚果/零食",
    "零食": "坚果/零食",
    "坚果零食": "坚果/零食",
    "功能饮料": "功能饮料",
    "能量饮料": "功能饮料",
    "碳酸饮料": "碳酸饮料",
    "气泡水": "碳酸饮料",
    "牛奶": "牛奶",
    "酸奶": "酸奶",
    "调味品": "调味品",
    "酱油": "调味品",
}


@dataclass(frozen=True)
class TaxonomyMatch:
    category: str
    sub_category: str | None = None
    matched_text: str = ""


class TaxonomyResolver:
    def __init__(self, categories: dict[str, set[str]], aliases: dict[str, str] | None = None):
        self.categories = categories
        self.aliases = {**DEFAULT_ALIASES, **(aliases or {})}
        self.sub_to_category = {
            sub_category: category
            for category, sub_categories in categories.items()
            for sub_category in sub_categories
        }

    @classmethod
    def from_products(cls, products: list[Product]) -> "TaxonomyResolver":
        categories: dict[str, set[str]] = {}
        for product in products:
            categories.setdefault(product.category, set()).add(product.sub_category)
        return cls(categories)

    def resolve(self, text: str | None) -> TaxonomyMatch | None:
        text = _normalize(text or "")
        if not text:
            return None
        candidates: list[tuple[int, str, str | None, str]] = []
        for category in self.categories:
            key = _normalize(category)
            if key and key in text:
                candidates.append((len(key), category, None, category))
        for sub_category, category in self.sub_to_category.items():
            key = _normalize(sub_category)
            if key and key in text:
                candidates.append((len(key), category, sub_category, sub_category))
        for alias, target in self.aliases.items():
            key = _normalize(alias)
            if not key or key not in text:
                continue
            if target in self.sub_to_category:
                candidates.append((len(key), self.sub_to_category[target], target, alias))
            elif target in self.categories:
                candidates.append((len(key), target, None, alias))
        if not candidates:
            return None
        _, category, sub_category, matched_text = sorted(candidates, key=lambda item: (item[2] is not None, item[0]), reverse=True)[0]
        return TaxonomyMatch(category=category, sub_category=sub_category, matched_text=matched_text)

    def apply_to_constraints(self, constraints: HardConstraints, text: str | None = None) -> bool:
        changed = False
        if constraints.sub_category:
            match = self.resolve(constraints.sub_category)
            if match and match.sub_category:
                changed |= constraints.sub_category != match.sub_category or constraints.category != match.category
                constraints.sub_category = match.sub_category
                constraints.category = match.category
            else:
                constraints.sub_category = None
                changed = True
        if constraints.category:
            match = self.resolve(constraints.category)
            if match:
                changed |= constraints.category != match.category or constraints.sub_category != match.sub_category
                constraints.category = match.category
                if match.sub_category:
                    constraints.sub_category = match.sub_category
        if text and not constraints.sub_category:
            match = self.resolve(text)
            if match:
                changed |= constraints.category != match.category or constraints.sub_category != match.sub_category
                constraints.category = match.category
                constraints.sub_category = match.sub_category
        return changed

    def is_known_request(self, text: str | None) -> bool:
        return self.resolve(text) is not None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())
