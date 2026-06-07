from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from .constraint_filter import extract_excluded_brands, extract_included_brands
from .models import CartOperation, ChatRequest, ConstraintEdits, HardConstraints, ProductReference, RetrievalPlan, SemanticFrame, SessionContext


class SemanticParser:
    def __init__(self, llm_client: Any | None = None):
        self.llm_client = llm_client

    async def parse(self, request: ChatRequest, context: SessionContext | None = None) -> SemanticFrame:
        if self.llm_client and hasattr(self.llm_client, "parse_semantic_frame"):
            try:
                raw = await self.llm_client.parse_semantic_frame(
                    request.message,
                    semantic_context_payload(context),
                    request_type=request.type,
                )
                frame = _parse_frame(raw)
                guarded = _merge_rule_guards(frame, request)
                if guarded.intent == "unclear_input":
                    recovered = await self._try_contextual_followup_judge(request, semantic_context_payload(context))
                    if recovered is not None:
                        return recovered
                    recovered_by_rule = _contextual_rule_followup(request, semantic_context_payload(context))
                    if recovered_by_rule is not None:
                        return recovered_by_rule
                recovered_by_rule = _contextual_rule_followup(request, semantic_context_payload(context))
                if recovered_by_rule is not None and guarded.intent == "recommend_product":
                    return recovered_by_rule
                return guarded
            except Exception:
                pass
        return rule_semantic_frame(request)

    async def _try_contextual_followup_judge(
        self, request: ChatRequest, context_payload: dict[str, Any]
    ) -> SemanticFrame | None:
        if request.type != "user_message" or not context_payload.get("has_focus_product"):
            return None
        if not self.llm_client or not hasattr(self.llm_client, "classify_contextual_followup"):
            return None
        try:
            raw = await self.llm_client.classify_contextual_followup(request.message, context_payload)
            frame = _parse_frame(raw)
            if frame.intent != "product_followup":
                return None
            return _merge_rule_guards(frame, request)
        except Exception:
            return None


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
    if request.type == "user_message" and _is_compare_request(text):
        return SemanticFrame(intent="compare_products")
    if request.type == "user_message" and _is_small_talk(text):
        return SemanticFrame(intent="small_talk")
    if request.type == "user_message" and not _has_shopping_signal(text):
        return SemanticFrame(intent="unclear_input")
    edits = ConstraintEdits()
    price_min = _detect_price_min(text)
    if price_min is not None:
        edits.add.price_min = price_min
    price_max = _detect_price_max(text)
    if price_max is not None:
        edits.add.price_max = price_max
    if re.search(r"可以接受|不用排除|不介意|接受", text):
        if "酒精" in text or "乙醇" in text:
            edits.remove.exclude_terms.append("酒精")
        if "日系" in text or "日本" in text:
            edits.remove.exclude_brand_regions.append("日本")
    included_brands = extract_included_brands(text)
    if included_brands:
        edits.add.include_brands.extend(included_brands)
    if re.search(r"不要|不含|排除|除了", text):
        if "酒精" in text or "乙醇" in text:
            edits.add.exclude_terms.append("酒精")
        if "日系" in text or "日本" in text:
            edits.add.exclude_brand_regions.append("日本")
        edits.add.exclude_brands.extend(extract_excluded_brands(text))
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
    if "礼物" in text or "送人" in text or "送给" in text or "送" in text:
        soft["occasion"] = "送礼"
    if request.type == "product_followup":
        intent = "product_followup"
    return SemanticFrame(intent=intent, constraint_edits=edits)


def _contextual_rule_followup(request: ChatRequest, context_payload: dict[str, Any]) -> SemanticFrame | None:
    if request.type != "user_message" or not context_payload.get("has_focus_product"):
        return None
    text = request.message or ""
    edits = ConstraintEdits()
    response_goal = None
    if any(word in text for word in ["再便宜", "便宜点", "更便宜", "价格低", "低价"]):
        edits.add.soft_preferences["price_preference"] = "更便宜"
        response_goal = "recommend_cheaper_alternative"
    if any(word in text for word in ["更贵", "贵一点", "高端", "高价位", "价位高"]):
        edits.add.soft_preferences["price_preference"] = "更贵"
        response_goal = "recommend_more_expensive_alternative"
    excluded = extract_excluded_brands(text)
    if excluded:
        edits.add.exclude_brands.extend(excluded)
        response_goal = "exclude_current_brand"
    if any(word in text for word in ["不要这个品牌", "不要这个牌子", "换个品牌", "别的品牌"]):
        response_goal = "exclude_current_brand"
    if any(word in text for word in ["刚刚那个", "为什么推荐", "是什么", "介绍一下"]):
        response_goal = "explain_focus_product"
    if not response_goal and any(word in text for word in ["还有别的", "还有别", "换一个", "换一款", "这个不适合", "不适合"]):
        response_goal = "recommend_alternative"
    if response_goal is None:
        return None
    return SemanticFrame(
        intent="product_followup",
        constraint_edits=edits,
        target=ProductReference(reference="focus_product", selection_strategy="primary"),
        response_goal=response_goal,
    )


def _parse_frame(raw: str) -> SemanticFrame:
    data = _extract_json(raw)
    _normalize_semantic_frame_data(data)
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


def _normalize_semantic_frame_data(data: dict[str, Any]) -> None:
    edits = data.get("constraint_edits")
    if not isinstance(edits, dict):
        return
    for key in ("add", "remove"):
        if edits.get(key) == []:
            edits[key] = {}
    if edits.get("relax") in ({}, None):
        edits["relax"] = []


def _merge_rule_guards(frame: SemanticFrame, request: ChatRequest) -> SemanticFrame:
    guarded = rule_semantic_frame(request)
    if guarded.intent == "small_talk":
        frame.intent = "small_talk"
        return frame
    if guarded.intent == "unclear_input" and frame.intent == "recommend_product":
        frame.intent = "unclear_input"
        return frame
    if guarded.intent == "cart_operation" and frame.intent not in {"product_followup", "compare_products"} and frame.cart_operation is None:
        frame.intent = guarded.intent
        frame.cart_operation = guarded.cart_operation
    frame.constraint_edits.add.exclude_terms = _dedupe(
        frame.constraint_edits.add.exclude_terms + guarded.constraint_edits.add.exclude_terms
    )
    frame.constraint_edits.add.exclude_brand_regions = _dedupe(
        frame.constraint_edits.add.exclude_brand_regions + guarded.constraint_edits.add.exclude_brand_regions
    )
    frame.constraint_edits.add.include_brands = _dedupe(
        frame.constraint_edits.add.include_brands + guarded.constraint_edits.add.include_brands
    )
    frame.constraint_edits.add.exclude_brands = _dedupe(
        frame.constraint_edits.add.exclude_brands + guarded.constraint_edits.add.exclude_brands
    )
    if guarded.constraint_edits.add.price_min is not None:
        frame.constraint_edits.add.price_min = guarded.constraint_edits.add.price_min
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


def _is_compare_request(text: str) -> bool:
    return bool(re.search(r"对比|比较一下|比较下|哪个更|哪款更|怎么选|第一款|第二款|第三款", text or ""))


def _is_small_talk(text: str) -> bool:
    normalized = re.sub(r"[\s?？!！。,.，、]+", "", (text or "").lower())
    if not normalized:
        return True
    if _has_shopping_signal(text):
        return False
    if ("你好" in normalized or "您好" in normalized or re.search(r"h[ae]l+o+|hello|hi|hey", normalized)) and (
        "你是谁" in normalized or "你能做什么" in normalized or "你是干嘛的" in normalized
    ):
        return True
    return bool(
        re.fullmatch(
            r"(你好|您好|h[ae]l+o+|hello|hi|hey|yo|在吗|在不在|谢谢|谢了|感谢|辛苦了|你是谁呀?|你是干嘛的|你能做什么)",
            normalized,
        )
    )


def _has_shopping_signal(text: str) -> bool:
    return bool(
        re.search(
            r"推荐|找|买|想要|有没有|预算|以内|以下|以上|不低于|不要|不含|排除|对比|比较|哪个更|怎么选|购物车|加购|加入|下单|结算|"
            r"防晒|精华|护肤|手机|笔记本|电脑|耳机|跑鞋|鞋|衣服|背包|咖啡|饮料|食品|零食|礼物|送人|送给",
            text or "",
            flags=re.I,
        )
    )


def semantic_context_payload(context: SessionContext | None) -> dict[str, Any]:
    if context is None:
        return {}
    focus_product = _focus_product_summary(context)
    return {
        "last_plan": context.last_plan.model_dump(mode="json") if context.last_plan else None,
        "last_intent": context.state.dialog_state.last_intent,
        "focus_product_id": context.focus_product_id,
        "has_focus_product": focus_product is not None,
        "focus_product": focus_product,
        "last_product_ids": list(context.last_product_ids),
        "last_recommendations": list(context.last_recommendations),
        "recent_cart_product_id": context.recent_cart_product_id,
        "global_profile": dict(context.global_profile),
        "current_task": context.state.current_task.model_dump(mode="json"),
        "pending_clarification": (
            context.state.pending_clarification.model_dump(mode="json")
            if context.state.pending_clarification
            else None
        ),
        "pending_recovery": (
            context.state.pending_recovery.model_dump(mode="json")
            if context.state.pending_recovery
            else None
        ),
        "recent_context": _recent_context_summary(context),
    }


def _focus_product_summary(context: SessionContext) -> dict[str, Any] | None:
    focus_id = context.focus_product_id
    if not focus_id:
        return None
    for item in context.last_recommendations:
        if item.get("product_id") == focus_id:
            return dict(item)
    return {"product_id": focus_id}


def _recent_context_summary(context: SessionContext) -> dict[str, Any]:
    recommendation_sets = [
        event.model_dump(mode="json")
        for event in context.state.context_events
        if event.result_type == "recommendation_set"
    ][-3:]
    user_turns = [
        {
            "turn_index": event.turn_index,
            "user_message": event.user_message,
            "assistant_intent": event.assistant_intent,
            "result_type": event.result_type,
        }
        for event in context.state.context_events[-6:]
    ][-3:]
    return {
        "recent_user_turns": user_turns,
        "recent_recommendation_sets": recommendation_sets,
        "last_events": [event.model_dump(mode="json") for event in context.state.context_events[-3:]],
    }


def _remove_constraints(constraints: HardConstraints, patch) -> None:
    if patch.category and constraints.category == patch.category:
        constraints.category = None
    if patch.sub_category and constraints.sub_category == patch.sub_category:
        constraints.sub_category = None
    if patch.price_min is not None and constraints.price_min == patch.price_min:
        constraints.price_min = None
    if patch.price_max is not None and constraints.price_max == patch.price_max:
        constraints.price_max = None
    for term in patch.exclude_terms:
        constraints.exclude_terms = [value for value in constraints.exclude_terms if value != term]
    for brand in patch.include_brands:
        constraints.include_brands = [value for value in constraints.include_brands if value != brand]
    for brand in patch.exclude_brands:
        constraints.exclude_brands = [value for value in constraints.exclude_brands if value != brand]
    for region in patch.exclude_brand_regions:
        constraints.exclude_brand_regions = [value for value in constraints.exclude_brand_regions if value != region]


def _relax_constraints(constraints: HardConstraints, fields: list[str]) -> None:
    for field in fields:
        if field == "price_min":
            constraints.price_min = None
        if field == "price_max":
            constraints.price_max = None
        if field == "category":
            constraints.category = None
        if field == "sub_category":
            constraints.sub_category = None
        if field == "exclude_terms":
            constraints.exclude_terms = []
        if field == "include_brands":
            constraints.include_brands = []
        if field == "exclude_brands":
            constraints.exclude_brands = []
        if field == "exclude_brand_regions":
            constraints.exclude_brand_regions = []


def _add_constraints(constraints: HardConstraints, patch) -> None:
    if patch.category:
        constraints.category = patch.category
    if patch.sub_category:
        constraints.sub_category = patch.sub_category
    if patch.price_min is not None:
        constraints.price_min = patch.price_min
    if patch.price_max is not None:
        constraints.price_max = patch.price_max
    constraints.exclude_terms = _dedupe(constraints.exclude_terms + patch.exclude_terms)
    constraints.include_brands = _dedupe(constraints.include_brands + patch.include_brands)
    constraints.exclude_brands = _dedupe(constraints.exclude_brands + patch.exclude_brands)
    constraints.exclude_brand_regions = _dedupe(constraints.exclude_brand_regions + patch.exclude_brand_regions)


def _build_retrieval_query(message: str, constraints: HardConstraints, soft_preferences: dict[str, str]) -> str:
    return " ".join(
        part
        for part in [
            message,
            constraints.category or "",
            constraints.sub_category or "",
            *constraints.include_brands,
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
    if re.search(
        r"就这个|要这个|这个要|这款要|要这款|就它了|就这款|刚才.*(?:要|来|买)|(?:来|买)[一两二三四五\\d]+[件个](?:这个|这款|它)?$",
        text or "",
    ):
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


def _detect_price_min(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)?\s*(?:以上|起|往上)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"(?:不低于|至少|高于)\s*(\d+(?:\.\d+)?)\s*(?:元|块)?", text)
    if match:
        return float(match.group(1))
    match = re.search(r"预算\s*(\d+(?:\.\d+)?)\s*(?:元|块)?\s*(?:以上|起|往上)", text)
    if match:
        return float(match.group(1))
    return None


def _detect_price_max(text: str) -> float | None:
    if _detect_price_min(text) is not None:
        return None
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
