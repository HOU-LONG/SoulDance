from __future__ import annotations

from .models import HardConstraints, RetrievalPlan, SessionContext, ShoppingIntentIR
from .planner_agent import _clarification_policy, _detect_category, _parent_category


class QueryBuilder:
    """Deterministically compiles ShoppingIntentIR + SessionState into a RetrievalPlan."""

    def build(self, ir: ShoppingIntentIR, context: SessionContext, user_message: str) -> RetrievalPlan:
        hard = context.state.constraint_state.hard.model_copy(deep=True)
        soft = dict(context.state.constraint_state.soft)
        _fill_category_from_text(hard, user_message)
        for key, value in ir.query_intent.soft_preferences.items():
            if value:
                soft.setdefault(key, value)
        query_terms = _dedupe(
            [
                *ir.query_intent.query_terms,
                user_message,
                hard.category or "",
                hard.sub_category or "",
                *soft.values(),
            ]
        )
        intent = ir.intent
        need_clarification, clarification_question = _clarification_policy(
            user_message,
            hard.sub_category or hard.category,
            hard,
            soft,
            intent,
        )
        if ir.clarification_question:
            need_clarification = True
            clarification_question = ir.clarification_question
        if need_clarification:
            intent = "clarification"
        retrieval_mode = {
            "product_followup": "product_focus_retrieval",
            "compare_products": "state_then_detail",
            "scenario_bundle": "decompose_parallel",
            "cart_operation": "state_then_action",
            "clarification": "clarification",
            "small_talk": "no_retrieval",
        }.get(intent, "single")
        return RetrievalPlan(
            intent=intent,
            retrieval_mode=retrieval_mode,
            category=hard.sub_category or hard.category,
            hard_constraints=hard,
            soft_preferences=soft,
            retrieval_query=" ".join(query_terms) or user_message or "商品推荐",
            need_clarification=need_clarification,
            clarification_question=clarification_question,
        )


def _fill_category_from_text(hard: HardConstraints, text: str) -> None:
    if hard.category and hard.sub_category:
        return
    category = _detect_category(text or "")
    if not category:
        return
    if category in {"美妆护肤", "数码电子", "服饰运动", "食品饮料"}:
        hard.category = hard.category or category
    else:
        hard.sub_category = hard.sub_category or category
        hard.category = hard.category or _parent_category(category)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
