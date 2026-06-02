from __future__ import annotations

from .models import ConstraintEdits, HardConstraints, RetrievalPlan, SessionContext, ShoppingIntentIR
from .semantic_layer import _add_constraints, _dedupe, _relax_constraints, _remove_constraints


class StateReducer:
    """Applies semantic edits to the deterministic session state."""

    def apply(self, context: SessionContext, ir: ShoppingIntentIR, user_message: str) -> None:
        state = context.state
        state.dialog_state.turn_index += 1
        state.dialog_state.last_intent = ir.intent
        state.dialog_state.last_user_message = user_message
        _apply_constraint_edits(state.constraint_state.hard, state.constraint_state.soft, ir.constraint_edits)
        _apply_query_intent_defaults(state.constraint_state.hard, state.constraint_state.soft, ir)
        state.constraint_state.source_turns.append(
            {
                "turn_index": state.dialog_state.turn_index,
                "intent": ir.intent,
                "message": user_message,
                "constraint_edits": ir.constraint_edits.model_dump(mode="json"),
            }
        )
        _sync_legacy_context(context)


def seed_constraint_state_from_plan(context: SessionContext, plan: RetrievalPlan | None) -> None:
    if plan is None:
        return
    state = context.state
    if state.constraint_state.hard == HardConstraints() and not state.constraint_state.soft:
        state.constraint_state.hard = plan.hard_constraints.model_copy(deep=True)
        state.constraint_state.soft = dict(plan.soft_preferences)
        _sync_legacy_context(context)


def _apply_constraint_edits(hard: HardConstraints, soft: dict[str, str], edits: ConstraintEdits) -> None:
    _remove_constraints(hard, edits.remove)
    _relax_constraints(hard, edits.relax)
    _add_constraints(hard, edits.add)
    for key, value in edits.add.soft_preferences.items():
        if value:
            soft[key] = value
    for key, value in edits.remove.soft_preferences.items():
        if soft.get(key) == value:
            soft.pop(key, None)


def _apply_query_intent_defaults(hard: HardConstraints, soft: dict[str, str], ir: ShoppingIntentIR) -> None:
    query_intent = ir.query_intent
    if query_intent.category:
        hard.category = query_intent.category
    if query_intent.sub_category:
        hard.sub_category = query_intent.sub_category
    for key, value in query_intent.soft_preferences.items():
        if value:
            soft[key] = value


def _sync_legacy_context(context: SessionContext) -> None:
    hard = context.state.constraint_state.hard
    soft = context.state.constraint_state.soft
    if context.last_plan is not None:
        context.last_plan.hard_constraints = hard.model_copy(deep=True)
        context.last_plan.soft_preferences = dict(soft)
        context.last_plan.category = hard.sub_category or hard.category or context.last_plan.category
    context.global_profile.update({key: value for key, value in soft.items() if value})
    if hard.price_max is not None:
        context.global_profile["budget_max"] = hard.price_max
    if hard.exclude_terms:
        context.global_profile["exclude_terms"] = _dedupe(hard.exclude_terms)
    if hard.exclude_brand_regions:
        context.global_profile["exclude_brand_regions"] = _dedupe(hard.exclude_brand_regions)
