from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from .models import CartOperation, ChatRequest, ConstraintEdits, HardConstraints, ProductReference, RetrievalPlan, SemanticFrame, SessionContext


class SemanticParser:
    def __init__(self, llm_client: Any | None = None):
        self.llm_client = llm_client

    async def parse(self, request: ChatRequest, context: SessionContext | None = None) -> SemanticFrame:
        if self.llm_client and hasattr(self.llm_client, "parse_semantic_frame"):
            try:
                raw = await self.llm_client.parse_semantic_frame(
                    request.message,
                    context,
                    request_type=request.type,
                )
                frame = _parse_frame(raw)
                return _merge_rule_guards(frame, request)
            except Exception:
                pass
        return rule_semantic_frame(request)


def apply_constraint_edits(base_plan: RetrievalPlan, edits: ConstraintEdits, message: str = "") -> RetrievalPlan:
    plan = base_plan.model_copy(deep=True)
    constraints = plan.hard_constraints
    _remove_constraints(constraints, edits.remove)
    _relax_constraints(constraints, edits.relax)
    _add_constraints(constraints, edits.add)
    if edits.add.soft_preferences:
        plan.soft_preferences.update(edits.add.soft_preferences)
    if edits.remove.soft_preferences:
        for key, value in edits.remove.soft_preferences.items():
            if plan.soft_preferences.get(key) == value:
                plan.soft_preferences.pop(key, None)
    plan.category = constraints.sub_category or constraints.category or plan.category
    plan.retrieval_query = _build_retrieval_query(message, constraints, plan.soft_preferences)
    return plan


def resolve_cart_operation(operation: CartOperation, context: SessionContext, product_map: dict[str, Any], cart_snapshot: dict) -> tuple[str, int, str | None]:
    action = _normalize_cart_action(operation.action)
    product_id = _resolve_reference(operation.target, context, product_map, cart_snapshot)
    quantity = max(operation.quantity, 0)
    return action, quantity, product_id


def rule_semantic_frame(request: ChatRequest) -> SemanticFrame:
    text = request.message or ""
    intent = "product_followup" if request.type == "product_followup" else "recommend_product"
    cart_action = _detect_cart_action(text)
    if cart_action != "get_cart" or any(word in text for word in ["购物车", "下单", "结算"]):
        return SemanticFrame(
            intent="cart_operation",
            cart_operation=CartOperation(
                action=cart_action,
                quantity=_detect_quantity(text) or request.quantity,
                target=_rule_product_reference(text),
            ),
        )
    edits = ConstraintEdits()
    price_max = _detect_price_max(text)
    if price_max is not None:
        edits.add.price_max = price_max
    if re.search(r"可以接受|不用排除|不介意|接受", text):
        if "酒精" in text or "乙醇" in text:
            edits.remove.exclude_terms.append("酒精")
        if "日系" in text or "日本" in text:
            edits.remove.exclude_brand_regions.append("日本")
    if re.search(r"不要|不含|排除|除了", text):
        if "酒精" in text or "乙醇" in text:
            edits.add.exclude_terms.append("酒精")
        if "日系" in text or "日本" in text:
            edits.add.exclude_brand_regions.append("日本")
        if "苹果" in text or "Apple" in text or "apple" in text:
            edits.add.exclude_brands.append("苹果")
    soft = edits.add.soft_preferences
    if "拍照" in text:
        soft["priority"] = "拍照"
    if "续航" in text:
        soft["priority"] = "续航"
    if "性价比" in text:
        soft["priority"] = "性价比"
    if "轻薄" in text or "便携" in text:
        soft["priority"] = "轻薄便携"
    if "性能" in text or "游戏" in text:
        soft["priority"] = "性能优先"
    if "油皮" in text or "混油" in text:
        soft["skin_type"] = "油皮"
    if "敏感肌" in text:
        soft["skin_type"] = "敏感肌"
    if "保湿" in text or "修护" in text:
        soft["effect"] = "保湿修护"
    if "女朋友" in text or "女生" in text:
        soft["recipient"] = "女朋友"
    if "男朋友" in text or "男生" in text:
        soft["recipient"] = "男朋友"
    if "爸" in text or "妈" in text or "父母" in text or "长辈" in text:
        soft["recipient"] = "长辈"
    if "礼物" in text or "送人" in text or "送给" in text:
        soft["occasion"] = "送礼"
    if request.type == "product_followup":
        intent = "product_followup"
    return SemanticFrame(intent=intent, constraint_edits=edits)


def _parse_frame(raw: str) -> SemanticFrame:
    data = _extract_json(raw)
    return SemanticFrame.model_validate(data)


def _extract_json(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _merge_rule_guards(frame: SemanticFrame, request: ChatRequest) -> SemanticFrame:
    guarded = rule_semantic_frame(request)
    if guarded.intent == "cart_operation" and frame.cart_operation is None:
        frame.intent = guarded.intent
        frame.cart_operation = guarded.cart_operation
    frame.constraint_edits.add.exclude_terms = _dedupe(
        frame.constraint_edits.add.exclude_terms + guarded.constraint_edits.add.exclude_terms
    )
    frame.constraint_edits.add.exclude_brand_regions = _dedupe(
        frame.constraint_edits.add.exclude_brand_regions + guarded.constraint_edits.add.exclude_brand_regions
    )
    frame.constraint_edits.add.exclude_brands = _dedupe(
        frame.constraint_edits.add.exclude_brands + guarded.constraint_edits.add.exclude_brands
    )
    if guarded.constraint_edits.add.price_max is not None:
        frame.constraint_edits.add.price_max = guarded.constraint_edits.add.price_max
    frame.constraint_edits.add.soft_preferences.update(guarded.constraint_edits.add.soft_preferences)
    frame.constraint_edits.remove.exclude_terms = _dedupe(
        frame.constraint_edits.remove.exclude_terms + guarded.constraint_edits.remove.exclude_terms
    )
    frame.constraint_edits.remove.exclude_brand_regions = _dedupe(
        frame.constraint_edits.remove.exclude_brand_regions + guarded.constraint_edits.remove.exclude_brand_regions
    )
    frame.constraint_edits.remove.exclude_brands = _dedupe(
        frame.constraint_edits.remove.exclude_brands + guarded.constraint_edits.remove.exclude_brands
    )
    return frame


def _remove_constraints(constraints: HardConstraints, patch) -> None:
    if patch.category and constraints.category == patch.category:
        constraints.category = None
    if patch.sub_category and constraints.sub_category == patch.sub_category:
        constraints.sub_category = None
    if patch.price_max is not None and constraints.price_max == patch.price_max:
        constraints.price_max = None
    for term in patch.exclude_terms:
        constraints.exclude_terms = [value for value in constraints.exclude_terms if value != term]
    for brand in patch.exclude_brands:
        constraints.exclude_brands = [value for value in constraints.exclude_brands if value != brand]
    for region in patch.exclude_brand_regions:
        constraints.exclude_brand_regions = [value for value in constraints.exclude_brand_regions if value != region]


def _relax_constraints(constraints: HardConstraints, fields: list[str]) -> None:
    for field in fields:
        if field == "price_max":
            constraints.price_max = None
        if field == "category":
            constraints.category = None
        if field == "sub_category":
            constraints.sub_category = None
        if field == "exclude_terms":
            constraints.exclude_terms = []
        if field == "exclude_brands":
            constraints.exclude_brands = []
        if field == "exclude_brand_regions":
            constraints.exclude_brand_regions = []


def _add_constraints(constraints: HardConstraints, patch) -> None:
    if patch.category:
        constraints.category = patch.category
    if patch.sub_category:
        constraints.sub_category = patch.sub_category
    if patch.price_max is not None:
        constraints.price_max = patch.price_max
    constraints.exclude_terms = _dedupe(constraints.exclude_terms + patch.exclude_terms)
    constraints.exclude_brands = _dedupe(constraints.exclude_brands + patch.exclude_brands)
    constraints.exclude_brand_regions = _dedupe(constraints.exclude_brand_regions + patch.exclude_brand_regions)


def _build_retrieval_query(message: str, constraints: HardConstraints, soft_preferences: dict[str, str]) -> str:
    return " ".join(
        part
        for part in [
            message,
            constraints.category or "",
            constraints.sub_category or "",
            *soft_preferences.values(),
        ]
        if part
    ) or "商品推荐"


def _resolve_reference(reference: ProductReference, context: SessionContext, product_map: dict[str, Any], cart_snapshot: dict) -> str | None:
    if reference.product_id:
        return reference.product_id
    if reference.reference in {"focus_product", "current_product"}:
        return context.focus_product_id or (context.last_product_ids[0] if context.last_product_ids else None)
    if reference.reference in {"last_recommendation", "last_recommendations", "recommendations"}:
        candidates = [product_map[product_id] for product_id in context.last_product_ids if product_id in product_map]
        if not candidates:
            return None
        if reference.index is not None and 0 <= reference.index < len(candidates):
            return candidates[reference.index].product_id
        if reference.selection_strategy == "cheapest":
            return min(candidates, key=lambda product: product.price).product_id
        if reference.selection_strategy == "most_expensive":
            return max(candidates, key=lambda product: product.price).product_id
        return candidates[0].product_id
    if reference.reference in {"recent_cart_item", "cart_item"}:
        if context.recent_cart_product_id:
            return context.recent_cart_product_id
        items = cart_snapshot.get("items", [])
        if reference.index is not None and 0 <= reference.index < len(items):
            return items[reference.index].get("product_id")
        if items:
            return items[0].get("product_id")
    return context.focus_product_id or (context.last_product_ids[0] if context.last_product_ids else None)


def _rule_product_reference(text: str) -> ProductReference:
    if "最便宜" in text:
        return ProductReference(reference="last_recommendations", selection_strategy="cheapest")
    index = _detect_index(text)
    if index is not None:
        return ProductReference(reference="last_recommendations", selection_strategy="index", index=index)
    if any(word in text for word in ["刚才", "这款", "这个", "主推"]):
        return ProductReference(reference="focus_product", selection_strategy="primary")
    return ProductReference(reference="focus_product", selection_strategy="primary")


def _detect_index(text: str) -> int | None:
    index_map = {"第一": 0, "第1": 0, "第二": 1, "第2": 1, "第三": 2, "第3": 2}
    for marker, index in index_map.items():
        if marker in text:
            return index
    return None


def _detect_cart_action(text: str) -> str:
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


def _detect_price_max(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)?\s*(?:以内|以下|内)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"预算\s*(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))
    return None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
