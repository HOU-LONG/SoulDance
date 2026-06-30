"""
Rule-based semantic frame extraction and constraint helpers.

rule_semantic_frame() — fast regex-based fallback for tool routing when LLM is unavailable.
Constraint helpers (_add_constraints, _relax_constraints, _remove_constraints) used by
StateReducer for editing constraint state.

The LLM-based SemanticParser was removed in v2.0 cleanup; tool routing is now handled
by ToolPlanner (tool_planner.py).
"""
from __future__ import annotations

import re

from .cart_intent import _detect_cart_action, _detect_quantity as _detect_cart_quantity, _normalize_cart_action
from .constraint_filter import dedupe, extract_excluded_brands, extract_included_brands
from .models import ChatRequest, HardConstraints


def rule_semantic_frame(request: ChatRequest):
    """纯规则引擎 — 直接返回 UnifiedPlan（Stage 2 扁平字段）。"""
    from .models import UnifiedPlan
    text = request.message or ""
    tool = "product_followup" if request.type == "product_followup" else "recommend_product"

    cart_action = _detect_cart_action(text)
    if cart_action != "get_cart" or any(word in text for word in ["购物车", "下单", "结算"]):
        return UnifiedPlan(
            tool="cart_operation",
            cart_action=cart_action,
            cart_quantity=_detect_quantity(text) or request.quantity,
        )
    if request.type == "user_message" and _is_compare_request(text):
        return UnifiedPlan(tool="compare_products")
    if request.type == "user_message" and _is_small_talk(text):
        return UnifiedPlan(tool="small_talk")
    if request.type == "user_message" and not _has_shopping_signal(text):
        return UnifiedPlan(tool="unclear_input")

    frame = UnifiedPlan(tool=tool)
    price_min = _detect_price_min(text)
    if price_min is not None:
        frame.price_min = price_min
    price_max = _detect_price_max(text)
    if price_max is not None:
        frame.price_max = price_max
    included_brands = extract_included_brands(text)
    if included_brands:
        frame.include_brands = dedupe(list(frame.include_brands) + included_brands)
    if re.search(r"不要|不含|排除|除了", text):
        frame.exclude_brands = dedupe(list(frame.exclude_brands) + extract_excluded_brands(text))
    # soft preferences
    soft: dict[str, str] = {}
    if "拍照" in text: soft["priority"] = "拍照"
    if "续航" in text: soft["priority"] = "续航"
    if "性价比" in text: soft["priority"] = "性价比"
    if "轻薄" in text or "便携" in text: soft["priority"] = "轻薄便携"
    if "性能" in text or "游戏" in text: soft["priority"] = "性能优先"
    if "油皮" in text or "混油" in text: soft["skin_type"] = "油皮"
    if "敏感肌" in text: soft["skin_type"] = "敏感肌"
    if "干性皮肤" in text or "干皮" in text or "干性" in text: soft["skin_type"] = "干性"
    if "秋冬" in text: soft["season"] = "秋冬"
    if "春天" in text or "春季" in text: soft["season"] = "春季"
    if "夏天" in text or "夏季" in text: soft["season"] = "夏季"
    if "冬天" in text or "冬季" in text: soft["season"] = "冬季"
    if "保湿" in text or "修护" in text: soft["effect"] = "保湿修护"
    if "女朋友" in text or "女生" in text: soft["recipient"] = "女朋友"
    if "男朋友" in text or "男生" in text: soft["recipient"] = "男朋友"
    if "爸" in text or "妈" in text or "父母" in text or "长辈" in text: soft["recipient"] = "长辈"
    if "礼物" in text or "送人" in text or "送给" in text or "送" in text: soft["occasion"] = "送礼"
    if "惊喜" in text: soft["gift_style"] = "惊喜感"
    if "稳妥" in text or "不踩雷" in text: soft["gift_style"] = "稳妥不踩雷"
    if "实用" in text: soft["gift_style"] = "实用"
    if any(phrase in text for phrase in ["回到第一轮", "最开始那个", "第一轮那个", "回到最开始"]):
        soft["anchor_reference"] = "first_turn"
    if request.type == "product_followup":
        tool = "product_followup"
    frame.tool = tool
    frame.soft_preferences = soft
    return frame


def _is_compare_request(text: str) -> bool:
    return bool(re.search(r"对比|比较一下|比较下|哪个更|哪款更|怎么选|第一款|第二款|第三款", text or ""))


def _is_small_talk(text: str) -> bool:
    normalized = re.sub(r"[\s?？!！。,.，、]+", "", (text or "").lower())
    if not normalized:
        return True
    if _has_shopping_signal(text):
        return False
    capability_patterns = [
        "你能做什么", "你能帮我做什么", "你能帮我做些什么", "你能做啥",
        "你有什么功能", "你有什么用", "你可以做什么", "你可以帮我做什么",
        "你是干嘛的", "你是做什么的",
    ]
    for pattern in capability_patterns:
        if pattern in normalized:
            return True
    greeting_patterns = ["你好", "嗨", "在吗", "hello", "hi"]
    for pattern in greeting_patterns:
        if normalized.startswith(pattern):
            return True
    return False


def _has_shopping_signal(text: str) -> bool:
    signal_words = [
        "买", "买什么", "帮我找", "推荐", "找一款", "有没有", "想要", "想买个",
        "帮我看看", "帮我选", "挑一款", "换一款", "换一个", "不要这个", "加入购物车",
        "加购", "购物车", "下单", "结算", "对比", "比较", "预算", "价位",
        "多少钱", "价格", "便宜", "贵", "性价比",
    ]
    return any(word in (text or "") for word in signal_words)


# ---- 约束编辑辅助函数 ----

def _remove_constraints(constraints: HardConstraints, patch) -> None:
    if hasattr(patch, 'exclude_terms') and patch.exclude_terms:
        constraints.exclude_terms = [t for t in constraints.exclude_terms if t not in patch.exclude_terms]
    if hasattr(patch, 'include_brands') and patch.include_brands:
        constraints.include_brands = [b for b in constraints.include_brands if b not in patch.include_brands]
    if hasattr(patch, 'exclude_brands') and patch.exclude_brands:
        constraints.exclude_brands = [b for b in constraints.exclude_brands if b not in patch.exclude_brands]
    if hasattr(patch, 'exclude_brand_regions') and patch.exclude_brand_regions:
        constraints.exclude_brand_regions = [r for r in constraints.exclude_brand_regions if r not in patch.exclude_brand_regions]


def _relax_constraints(constraints: HardConstraints, fields: list[str]) -> None:
    for field in fields:
        if field == "price_min":
            constraints.price_min = None
        elif field == "price_max":
            constraints.price_max = None
        elif field == "exclude_terms":
            constraints.exclude_terms = []
        elif field == "exclude_brand_regions":
            constraints.exclude_brand_regions = []
        elif field == "exclude_brands":
            constraints.exclude_brands = []


def _add_constraints(constraints: HardConstraints, patch) -> None:
    if hasattr(patch, 'category') and patch.category:
        constraints.category = patch.category
    if hasattr(patch, 'sub_category') and patch.sub_category:
        constraints.sub_category = patch.sub_category
    if hasattr(patch, 'price_min') and patch.price_min is not None:
        constraints.price_min = patch.price_min
    if hasattr(patch, 'price_max') and patch.price_max is not None:
        constraints.price_max = patch.price_max
    if hasattr(patch, 'include_brands') and patch.include_brands:
        constraints.include_brands = dedupe(constraints.include_brands + patch.include_brands)
    if hasattr(patch, 'exclude_brands') and patch.exclude_brands:
        constraints.exclude_brands = dedupe(constraints.exclude_brands + patch.exclude_brands)
    if hasattr(patch, 'exclude_terms') and patch.exclude_terms:
        constraints.exclude_terms = dedupe(constraints.exclude_terms + patch.exclude_terms)
    if hasattr(patch, 'exclude_brand_regions') and patch.exclude_brand_regions:
        constraints.exclude_brand_regions = dedupe(constraints.exclude_brand_regions + patch.exclude_brand_regions)


def _detect_quantity(text: str) -> int | None:
    import re as _re
    m = _re.search(r"(\d+)\s*(个|件|瓶|盒|支|包|杯|罐|袋|箱|台|部|双|条|套)", text)
    if m:
        return int(m.group(1))
    return None


def _detect_price_min(text: str) -> float | None:
    import re as _re
    m = _re.search(r"(?:不低于|大于|高于|超过|≥|>=|>)\s*(\d+(?:\.\d+)?)\s*(?:元|块)?", text)
    if m:
        return float(m.group(1))
    m = _re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)?\s*(?:以上|及以上)", text)
    if m:
        return float(m.group(1))
    return None


def _detect_price_max(text: str) -> float | None:
    import re as _re
    m = _re.search(r"(?:不超过|低于|小于|≤|<=|<|预算)\s*(\d+(?:\.\d+)?)\s*(?:元|块)?", text)
    if m:
        return float(m.group(1))
    m = _re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)?\s*(?:以下|以内|以内预算|预算)", text)
    if m:
        return float(m.group(1))
    m = _re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)", text)
    if m:
        return float(m.group(1))
    return None
