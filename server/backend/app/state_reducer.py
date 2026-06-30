"""
会话状态归约器 — 将语义解析结果（ShoppingIntentIR）的约束编辑应用到对话状态上。

===== 领域概念扫盲 =====

"状态归约"（State Reduction）：在对话系统中，每轮用户输入都可能修改当前的状态
（约束条件、偏好、意图等）。StateReducer 的职责是把这些修改"归约"到 SessionContext
中——即把新信息合并到已有状态，保证多轮对话中上下文的一致性。

"HardConstraints vs SoftPreferences"：
- HardConstraints（硬约束）：必须满足的条件，比如"价格不超过 500 元"、"排除酒精成分"。
  不满足硬约束的商品会被直接过滤掉，用户看不到。
- SoftPreferences（软偏好）：加分项但不强制，比如"想要轻薄便携的"、"最好是送女朋友的"。
  满足偏好的商品排更前面，不满足的仍然可以看到。

"RetrievalPlan"：检索计划是 PlannerAgent（LLM）产出的结构化指令，包含硬约束、
软偏好、检索关键词等，用于指导后续的混合检索引擎。

"ConstraintEdits"：约束编辑是 IntentCompiler（混合 LLM+规则）从用户消息中抽取的
约束变更——add（新增约束）、remove（移除约束）、relax（放宽约束）。

===== 与其它模块协作 =====

- semantic_layer.py：_add_constraints / _relax_constraints / _remove_constraints
- constraint_filter.py：dedupe 去重
- models.py：SessionContext, ShoppingIntentIR, ConstraintEdits, HardConstraints
- agent.py：ShopGuideAgent.stream_message 在每轮 LLM 调用前调用 StateReducer.apply
"""

from __future__ import annotations

from .constraint_filter import dedupe
from .models import ConstraintEdits, HardConstraints, RetrievalPlan, SessionContext, ShoppingIntentIR, UnifiedPlan
from .semantic_layer import _add_constraints, _relax_constraints, _remove_constraints


class StateReducer:
    """将语义编辑应用到确定性的会话状态中。

    每轮对话调用一次 apply()，执行顺序：
    1. 更新对话元数据（轮次、最后意图、最后用户消息）
    2. 应用约束编辑到 hard/soft 约束
    3. 合并 intent 级别的默认值（query_intent）
    4. 记录本轮编辑到 source_turns 审计日志
    5. 同步到 global_profile（旧版兼容字段，用于 LLM 上下文注入）
    """

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

    def apply_unified(self, context: SessionContext, plan: UnifiedPlan, user_message: str) -> None:
        """消费 UnifiedPlan 的状态归约（Stage 2 新增）。"""
        state = context.state
        state.dialog_state.turn_index += 1
        state.dialog_state.last_intent = plan.tool
        state.dialog_state.last_user_message = user_message

        hc = state.constraint_state.hard
        if plan.category:
            hc.category = plan.category
        if plan.sub_category:
            hc.sub_category = plan.sub_category
        if plan.price_min is not None:
            hc.price_min = plan.price_min
        if plan.price_max is not None:
            hc.price_max = plan.price_max
        if plan.include_brands:
            hc.include_brands = dedupe(list(hc.include_brands) + list(plan.include_brands))
        if plan.exclude_brands:
            hc.exclude_brands = dedupe(list(hc.exclude_brands) + list(plan.exclude_brands))
        for key, value in plan.soft_preferences.items():
            if value:
                state.constraint_state.soft[key] = value

        state.constraint_state.source_turns.append({
            "turn_index": state.dialog_state.turn_index,
            "intent": plan.tool,
            "message": user_message,
            "plan": plan.model_dump(mode="json"),
        })
        _sync_legacy_context(context)


def seed_constraint_state_from_plan(context: SessionContext, plan: RetrievalPlan | None) -> None:
    """首次对话时，用 PlannerAgent 产出的 RetrievalPlan 初始化约束状态。

    只在 hard 约束为空（默认值 HardConstraints()）且 soft 约束也为空时执行。
    这样做的好处：LLM 规划出的初始约束会写入状态机，后续每轮用户的微调
    （如"再便宜一点"）可以在此基础上叠加/修改，而不是每次从头规划。
    """
    if plan is None:
        return
    state = context.state
    if state.constraint_state.hard == HardConstraints() and not state.constraint_state.soft:
        state.constraint_state.hard = plan.hard_constraints.model_copy(deep=True)
        state.constraint_state.soft = dict(plan.soft_preferences)
        _sync_legacy_context(context)


def _apply_constraint_edits(hard: HardConstraints, soft: dict[str, str], edits: ConstraintEdits) -> None:
    """按顺序应用约束编辑：先移除 → 再放宽 → 最后新增。

    顺序很重要：如果先加再移除，可能导致刚加的就被删了；
    先移除再放宽再新增，保证编辑的操作语义正确。

    soft 偏好直接合并（字典级别），同 key 的新值覆盖旧值。
    """
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
    """将 IntentCompiler 产出的 query_intent 字段合并到约束状态。

    query_intent 是 LLM 从用户原始消息中提取的"直接意图"（品类、子品类、偏好），
    与 constraint_edits（显式增/删/改操作）不同，query_intent 是"默认赋值"——
    只有字段非空时才写入，不会覆盖已有值。
    """
    query_intent = ir.query_intent
    if query_intent.category:
        hard.category = query_intent.category
    if query_intent.sub_category:
        hard.sub_category = query_intent.sub_category
    for key, value in query_intent.soft_preferences.items():
        if value:
            soft[key] = value


def _sync_legacy_context(context: SessionContext) -> None:
    """将 hard/soft 约束同步到 global_profile 和 last_plan。

    global_profile 是旧版上下文字典，用于拼接到 LLM 的 system prompt 中。
    这里的同步逻辑确保 LLM 能看到最新的约束条件（预算范围、排除品牌等），
    从而做出更符合用户当前意图的推荐。

    注意：global_profile 会被完全覆盖（update + 逐字段赋值），
    不会保留之前设置但本轮未涉及的值。这是设计选择——约束状态是全局唯一的，
    LLM 应看到完整的当前约束快照而非增量 diff。
    """
    hard = context.state.constraint_state.hard
    soft = context.state.constraint_state.soft
    if context.last_plan is not None:
        context.last_plan.hard_constraints = hard.model_copy(deep=True)
        context.last_plan.soft_preferences = dict(soft)
        context.last_plan.category = hard.sub_category or hard.category or context.last_plan.category
    context.global_profile.update({key: value for key, value in soft.items() if value})
    if hard.price_min is not None:
        context.global_profile["budget_min"] = hard.price_min
    if hard.price_max is not None:
        context.global_profile["budget_max"] = hard.price_max
    if hard.include_brands:
        context.global_profile["include_brands"] = dedupe(hard.include_brands)
    if hard.exclude_terms:
        context.global_profile["exclude_terms"] = dedupe(hard.exclude_terms)
    if hard.exclude_brand_regions:
        context.global_profile["exclude_brand_regions"] = dedupe(hard.exclude_brand_regions)
