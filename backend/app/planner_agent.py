from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from .models import ChatRequest, HardConstraints, RetrievalPlan, SessionContext


CATEGORY_ALIASES = {
    "防晒霜": "防晒",
    "防晒": "防晒",
    "洗面奶": "洁面",
    "洁面": "洁面",
    "精华液": "精华",
    "精华": "精华",
    "护肤品": "美妆护肤",
    "手机": "智能手机",
    "智能手机": "智能手机",
    "笔记本电脑": "笔记本电脑",
    "笔记本": "笔记本电脑",
    "轻薄本": "笔记本电脑",
    "电脑本": "笔记本电脑",
    "耳机": "真无线耳机",
    "跑鞋": "跑步鞋",
    "跑步鞋": "跑步鞋",
    "咖啡": "咖啡",
}


class PlannerAgent:
    def __init__(self, llm_client: Any | None = None):
        self.llm_client = llm_client

    async def create_plan(self, request: ChatRequest, context: SessionContext | None = None) -> RetrievalPlan:
        if self.llm_client:
            try:
                raw = await self.llm_client.plan(request.message, context)
                plan = self._parse_llm_plan(raw)
                return self._merge_rule_guards(plan, request, context)
            except Exception:
                pass
        return self.rule_plan(request, context)

    def rule_plan(self, request: ChatRequest, context: SessionContext | None = None) -> RetrievalPlan:
        text = request.message or ""
        constraints = HardConstraints()
        soft: dict[str, str] = {}
        intent = _detect_intent(text, request)
        category = _detect_category(text)
        if category:
            if category in {"美妆护肤", "数码电子", "服饰运动", "食品饮料"}:
                constraints.category = category
            else:
                constraints.sub_category = category
                constraints.category = _parent_category(category)

        price_max = _detect_price_max(text)
        if price_max is not None:
            constraints.price_max = price_max
        elif request.type == "product_followup" and context and context.last_plan:
            constraints = context.last_plan.hard_constraints.model_copy(deep=True)
            followup_price = _detect_price_max(text)
            if followup_price is not None:
                constraints.price_max = followup_price

        if request.type == "product_followup" and context and context.last_plan:
            inherited = context.last_plan.hard_constraints.model_copy(deep=True)
            if constraints.category is None:
                constraints.category = inherited.category
            if constraints.sub_category is None:
                constraints.sub_category = inherited.sub_category
            constraints.exclude_terms = _dedupe(inherited.exclude_terms + constraints.exclude_terms)
            constraints.exclude_brands = _dedupe(inherited.exclude_brands + constraints.exclude_brands)
            constraints.exclude_brand_regions = _dedupe(
                inherited.exclude_brand_regions + constraints.exclude_brand_regions
            )
            if constraints.price_max is None:
                constraints.price_max = inherited.price_max

        if re.search(r"不要|不含|排除|除了", text):
            if "酒精" in text or "乙醇" in text:
                constraints.exclude_terms = _dedupe(constraints.exclude_terms + ["酒精"])
            if "日系" in text or "日本" in text:
                constraints.exclude_brand_regions = _dedupe(constraints.exclude_brand_regions + ["日本"])
            if "苹果" in text or "Apple" in text or "apple" in text:
                constraints.exclude_brands = _dedupe(constraints.exclude_brands + ["苹果"])
        if "油皮" in text or "混油" in text:
            soft["skin_type"] = "油皮"
        if "敏感肌" in text:
            soft["skin_type"] = "敏感肌"
        if "清爽" in text:
            soft["texture"] = "清爽"
        if "三亚" in text or "海边" in text:
            soft["scene"] = "海边度假"
        if "通勤" in text:
            soft["scene"] = "日常通勤"
        if "便宜" in text or "贵" in text:
            soft["price_preference"] = "更便宜"
        if "拍照" in text:
            soft["priority"] = "拍照"
        if "续航" in text:
            soft["priority"] = "续航"
        if "性价比" in text:
            soft["priority"] = "性价比"

        need_clarification, clarification_question = _clarification_policy(text, category, constraints, soft, intent)
        if need_clarification:
            intent = "clarification"

        retrieval_query = " ".join(
            part
            for part in [
                text,
                constraints.category or "",
                constraints.sub_category or "",
                *soft.values(),
            ]
            if part
        )
        retrieval_mode = {
            "product_followup": "product_focus_retrieval",
            "compare_products": "state_then_detail",
            "scenario_bundle": "decompose_parallel",
            "cart_action": "state_then_action",
            "clarification": "clarification",
            "small_talk": "no_retrieval",
            "unclear_input": "no_retrieval",
        }.get(intent, "single")
        return RetrievalPlan(
            intent=intent,
            retrieval_mode=retrieval_mode,
            category=constraints.sub_category or constraints.category,
            hard_constraints=constraints,
            soft_preferences=soft,
            retrieval_query=retrieval_query or text or "商品推荐",
            need_clarification=need_clarification,
            clarification_question=clarification_question,
        )

    def _parse_llm_plan(self, raw: str) -> RetrievalPlan:
        data = _extract_json(raw)
        return RetrievalPlan.model_validate(data)

    def _merge_rule_guards(
        self, plan: RetrievalPlan, request: ChatRequest, context: SessionContext | None = None
    ) -> RetrievalPlan:
        guarded = self.rule_plan(request, context)
        constraints = plan.hard_constraints
        rule_constraints = guarded.hard_constraints
        if rule_constraints.price_max is not None:
            constraints.price_max = rule_constraints.price_max
        constraints.exclude_terms = _dedupe(constraints.exclude_terms + rule_constraints.exclude_terms)
        constraints.exclude_brands = _dedupe(constraints.exclude_brands + rule_constraints.exclude_brands)
        constraints.exclude_brand_regions = _dedupe(
            constraints.exclude_brand_regions + rule_constraints.exclude_brand_regions
        )
        if not constraints.category:
            constraints.category = rule_constraints.category
        if not constraints.sub_category:
            constraints.sub_category = rule_constraints.sub_category
        if not plan.retrieval_query:
            plan.retrieval_query = guarded.retrieval_query
        plan.hard_constraints = constraints
        plan.category = plan.category or guarded.category
        if guarded.intent in {"clarification", "compare_products", "scenario_bundle", "cart_action", "product_followup"}:
            plan.intent = guarded.intent
            plan.retrieval_mode = guarded.retrieval_mode
        if guarded.need_clarification:
            plan.intent = "clarification"
            plan.retrieval_mode = "clarification"
            plan.need_clarification = True
            plan.clarification_question = guarded.clarification_question
        return plan


def _extract_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
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


def _detect_category(text: str) -> str | None:
    for key, category in CATEGORY_ALIASES.items():
        if key in text:
            return category
    if any(word in text for word in ["护肤", "美妆", "面霜", "精华"]):
        return "美妆护肤"
    if any(word in text for word in ["电脑", "平板", "数码"]):
        return "数码电子"
    if any(word in text for word in ["运动", "衣服", "背包"]):
        return "服饰运动"
    if any(word in text for word in ["饮料", "食品", "零食"]):
        return "食品饮料"
    return None


def _detect_intent(text: str, request: ChatRequest) -> str:
    if request.type == "product_followup":
        return "product_followup"
    if re.search(r"购物车|加购|加入|下单|结算|删掉|删除|移除|数量|改成", text):
        return "cart_action"
    if _is_small_talk_intent(text):
        return "small_talk"
    if re.search(r"对比|比较一下|比较下|哪个更|哪款更|第一款|第二款|第三款", text):
        return "compare_products"
    if ("三亚" in text or "海边" in text or "度假" in text) and re.search(r"搭配|一套|方案|从.+到", text):
        return "scenario_bundle"
    if _has_shopping_admission_signal(text) or _detect_category(text):
        return "recommend_product"
    return "unclear_input"


def _is_small_talk_intent(text: str) -> bool:
    normalized = re.sub(r"[\s?？!！。,.，、]+", "", (text or "").lower())
    if not normalized:
        return True
    if re.search(
        r"推荐|找|买|想要|有没有|预算|以内|以下|不要|不含|排除|对比|比较|哪个更|购物车|加购|加入|下单|结算|"
        r"防晒|精华|护肤|手机|笔记本|电脑|耳机|跑鞋|鞋|衣服|背包|咖啡|饮料|食品|零食|礼物|送人|送给",
        text or "",
        flags=re.I,
    ):
        return False
    return bool(
        re.fullmatch(
            r"(你好|您好|h[ae]l+o+|hello|hi|hey|yo|在吗|在不在|谢谢|谢了|感谢|辛苦了|你是谁|你是干嘛的|你能做什么)",
            normalized,
        )
    )


def _has_shopping_admission_signal(text: str) -> bool:
    return bool(
        re.search(
            r"推荐|找|买|想要|想买|看看|有没有|预算|以内|以下|不要|不含|排除|对比|比较|哪个更|购物车|加购|加入|下单|结算|"
            r"防晒|精华|护肤|手机|笔记本|电脑|耳机|跑鞋|鞋|衣服|背包|咖啡|饮料|食品|零食|礼物|送人|送给",
            text or "",
            flags=re.I,
        )
    )


def _clarification_policy(
    text: str,
    category: str | None,
    constraints: HardConstraints,
    soft: dict[str, str],
    intent: str,
) -> tuple[bool, str | None]:
    if intent != "recommend_product":
        return False, None
    if category == "智能手机" and constraints.price_max is None and "priority" not in soft:
        return True, "选手机我需要先知道你更看重拍照、续航还是性价比？也可以直接告诉我预算。"
    if category == "笔记本电脑" and constraints.price_max is None and "priority" not in soft:
        return True, "选笔记本我需要先知道你更看重轻薄便携、性能，还是性价比？也可以直接告诉我预算。"
    if _is_generic_gift_request(text) and (constraints.price_max is None or "recipient" not in soft):
        return True, "送礼我需要先确认预算和对象：更偏实用、惊喜感，还是稳妥不踩雷？"
    if category == "美妆护肤" and constraints.sub_category is None and constraints.price_max is None:
        if "skin_type" not in soft and "effect" not in soft:
            return True, "护肤品我需要先确认肤质或功效：油皮清爽、敏感肌温和，还是保湿修护？"
    return False, None


def _is_generic_gift_request(text: str) -> bool:
    return bool(re.search(r"送人|送给|礼物|生日|女朋友|男朋友|父母|长辈", text or ""))


def _parent_category(sub_category: str | None) -> str | None:
    if sub_category in {"防晒", "洁面", "精华", "面霜"}:
        return "美妆护肤"
    if sub_category in {"智能手机", "真无线耳机", "平板电脑", "笔记本电脑"}:
        return "数码电子"
    if sub_category in {"跑步鞋", "篮球鞋", "短袖T恤", "背包"}:
        return "服饰运动"
    if sub_category in {"咖啡", "茶饮", "方便食品"}:
        return "食品饮料"
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
